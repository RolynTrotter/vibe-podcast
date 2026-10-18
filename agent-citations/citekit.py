#!/usr/bin/env python3
"""Source material -> timestamped transcripts -> citable quotes -> cues for Motion/FCP and the edit.

Layout for one source batch (e.g. active_edits/vermeule/sources/):

  audio/<id>.m4a, <id>.info.json, <id>.en.json3   from yt-dlp (see SKILL.md for the command)
  transcripts/<id>.json, <id>.md                  `transcribe` or `captions`
  quotes.json                                     written by the agent while mining (see SKILL.md)
  citations/                                      `cues`: titles cue JSON, clip list, clip script

Transcript JSON:
  {"source": {"id", "title", "channel", "upload_date", "url", "duration"},
   "engine": "mlx-whisper:<model>" | "youtube-auto",
   "segments": [{"start", "end", "text", "words": [{"w", "start", "end"}]}]}

Nothing here writes over its inputs. Outputs that already exist are refused unless --force.
"""
import argparse
import difflib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
PAD_BEFORE, PAD_AFTER = 5.0, 5.0
CITATION_TEMPLATE = "Citation v2"
# Citation v2's text layers (see agent-motion/motionkit.py inspect)
SLOTS = {"author": "~Author Lastname", "title": "Person Writes Silly Headline to",
         "date": "20 Apr, 1969", "publication": "Publication"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ---------- helpers ----------

def hms(t):
    t = int(round(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def guard(path, force):
    if Path(path).exists() and not force:
        sys.exit(f"{path} exists; pass --force to replace it (or pick another --out)")


def load_info(audio):
    p = Path(audio)
    info = p.with_name(p.name.split(".")[0] + ".info.json")
    if not info.exists():
        return {"id": p.name.split(".")[0], "title": p.stem, "channel": None, "upload_date": None,
                "url": None, "duration": None, "description": ""}
    d = json.loads(info.read_text())
    return {"id": d["id"], "title": d.get("title"), "channel": d.get("channel"),
            "upload_date": d.get("upload_date"), "url": d.get("webpage_url") or f"https://youtu.be/{d['id']}",
            "duration": d.get("duration"), "description": d.get("description") or ""}


def link(src, t):
    if not src.get("url"):
        return ""
    sep = "&" if "?" in src["url"] else "?"
    return f"{src['url']}{sep}t={int(t)}"


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def write_outputs(tr, out_dir, force):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = tr["source"]["id"]
    js, md = out_dir / f"{sid}.json", out_dir / f"{sid}.md"
    guard(js, force), guard(md, force)
    js.write_text(json.dumps(tr, ensure_ascii=False, indent=1))
    src = tr["source"]
    lines = [f"# {src['title']}", "", f"- source: {src.get('url')}", f"- channel: {src.get('channel')}",
             f"- uploaded: {src.get('upload_date')}", f"- engine: {tr['engine']}", ""]
    lines += [f"[{hms(s['start'])}] {s['text'].strip()}" for s in tr["segments"]]
    md.write_text("\n".join(lines) + "\n")
    print(f"wrote {js}\nwrote {md}  ({len(tr['segments'])} segments)")


def transcripts(paths):
    for p in paths:
        p = Path(p)
        for f in sorted(p.glob("*.json")) if p.is_dir() else [p]:
            yield json.loads(f.read_text())


# ---------- transcribe / captions ----------

def cmd_transcribe(a):
    for audio in a.audio:
        src = load_info(audio)
        out_dir = Path(a.out or Path(audio).resolve().parent.parent / "transcripts")
        guard(out_dir / f"{src['id']}.json", a.force)
        # Names and terms from the title/description steer Whisper's spelling (Vermeule, Publius...).
        prompt = a.prompt or f"{src['title']}. {src['description'][:400]}"
        with tempfile.TemporaryDirectory() as tmp:
            # Decode once ourselves so a broken file can't silently shorten the transcript
            # (a yt-dlp resume across formats once spliced LC + HE-AAC; ffmpeg drops the 2nd half quietly).
            wav = Path(tmp) / "in.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(audio), "-vn", "-ac", "1",
                            "-ar", "16000", str(wav)], check=True, stderr=subprocess.DEVNULL)
            decoded = (wav.stat().st_size - 44) / 32000
            expected = src.get("duration") or decoded
            if decoded < 0.97 * expected and not a.allow_short:
                sys.exit(f"{audio}: decodes to {hms(decoded)} but the video is {hms(expected)}. The file is "
                         f"probably damaged (e.g. a resumed download); re-download it with --no-continue. "
                         f"--allow-short transcribes what's there.")
            cmd = ["mlx_whisper", str(wav), "--model", a.model, "--language", "en",
                   "--word-timestamps", "True", "--output-format", "json", "--output-dir", tmp,
                   "--output-name", "out", "--initial-prompt", prompt, "--verbose", "False",
                   "--condition-on-previous-text", "False"]
            print("$", shlex.join(cmd[:6]), "...", flush=True)
            subprocess.run(cmd, check=True)
            raw = json.loads((Path(tmp) / "out.json").read_text())
        segs = [{"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip(),
                 "words": [{"w": w["word"].strip(), "start": round(w["start"], 2), "end": round(w["end"], 2)}
                           for w in s.get("words", [])]}
                for s in raw["segments"] if s["text"].strip()]
        src.pop("description", None)
        write_outputs({"source": src, "engine": f"mlx-whisper:{a.model.split('/')[-1]}", "segments": segs},
                      out_dir, a.force)


def cmd_captions(a):
    """YouTube auto-captions (json3) -> transcript. Fast, word-timed, unpunctuated."""
    for f in a.json3:
        f = Path(f)
        src = load_info(f)
        src.pop("description", None)
        d = json.loads(f.read_text())
        segs = []
        for ev in d.get("events", []):
            if "segs" not in ev:
                continue
            t0 = ev["tStartMs"] / 1000
            words = [{"w": s["utf8"].strip(), "start": round(t0 + s.get("tOffsetMs", 0) / 1000, 2)}
                     for s in ev["segs"] if s.get("utf8", "").strip()]
            if not words:
                continue
            end = t0 + ev.get("dDurationMs", 0) / 1000
            for w, nxt in zip(words, words[1:] + [None]):
                w["end"] = nxt["start"] if nxt else round(end, 2)
            segs.append({"start": round(t0, 2), "end": round(end, 2),
                         "text": " ".join(w["w"] for w in words), "words": words})
        out_dir = Path(a.out or f.resolve().parent.parent / "transcripts")
        write_outputs({"source": src, "engine": "youtube-auto", "segments": segs}, out_dir, a.force)


def smpte(tc, fps):
    h, m, s, f = (int(x) for x in tc.split(":"))
    return h * 3600 + m * 60 + s + f / fps


def cmd_itt(a):
    """FCP-exported iTT captions (e.g. our own episode) -> transcript. Segment timing only.
    --fix 'wrong=>Right' corrects known mis-hearings (regex, case-insensitive)."""
    import xml.etree.ElementTree as ET
    ns = {"tt": "http://www.w3.org/ns/ttml"}
    fixes = [(re.compile(w, re.I), r) for w, r in (f.split("=>", 1) for f in a.fix)]
    root = ET.parse(a.itt).getroot()
    fps = float(root.get("{http://www.w3.org/ns/ttml#parameter}frameRate", 30))
    segs = []
    for p in root.iterfind(".//tt:p", ns):
        text = " ".join("".join(p.itertext()).split())
        for rx, rep in fixes:
            text = rx.sub(rep, text)
        if text:
            segs.append({"start": round(smpte(p.get("begin"), fps), 2), "end": round(smpte(p.get("end"), fps), 2),
                         "text": text, "words": []})
    for s in segs:  # spread words evenly so `locate` still gets usable (rough) times
        toks = s["text"].split()
        step = (s["end"] - s["start"]) / max(len(toks), 1)
        s["words"] = [{"w": t, "start": round(s["start"] + k * step, 2), "end": round(s["start"] + (k + 1) * step, 2)}
                      for k, t in enumerate(toks)]
    src = {"id": a.id, "title": a.title or Path(a.itt).stem, "channel": "Tiresias Foundation Podcast",
           "upload_date": None, "url": None, "duration": segs[-1]["end"] if segs else None, "media": a.media}
    write_outputs({"source": src, "engine": "fcp-captions", "segments": segs}, a.out, a.force)


# ---------- search / locate ----------

def cmd_search(a):
    rx = re.compile(a.pattern, re.I)
    for tr in transcripts(a.transcripts):
        segs, src = tr["segments"], tr["source"]
        for i, s in enumerate(segs):
            if rx.search(s["text"]):
                ctx = segs[max(0, i - a.context): i + a.context + 1]
                print(f"{src['id']} [{hms(s['start'])}] {link(src, s['start'])}")
                print("   " + " ".join(c["text"] for c in ctx))
                print()


def locate(tr, quote, near=None, window=120):
    """Best-matching word span for `quote`. Returns (start, end, score, matched_text)."""
    words = [w for s in tr["segments"] for w in s["words"]]
    toks = [norm(w["w"]) for w in words]
    q = [t for t in (norm(x) for x in quote.split()) if t]
    if not q or not words:
        return None
    n, best = len(q), (0.0, 0, 0)
    for i in range(len(toks)):
        if near is not None and abs(words[i]["start"] - near) > window:
            continue
        if q[0] not in toks[i:i + 4] and q[-1] not in toks[i + n - 4:i + n + 4]:
            continue  # cheap prefilter: an anchor word must be near the window's ends
        for m in (n - 2, n, n + 2):
            if m <= 0:
                continue
            r = difflib.SequenceMatcher(None, q, toks[i:i + m], autojunk=False).ratio()
            if r > best[0]:
                best = (r, i, i + m)
    score, i, j = best
    if score == 0:
        return None
    j = min(j, len(words))
    return words[i]["start"], words[j - 1]["end"], round(score, 3), " ".join(w["w"] for w in words[i:j])


def cmd_locate(a):
    tr = json.loads(Path(a.transcript).read_text())
    hit = locate(tr, a.quote, a.near)
    if not hit:
        sys.exit("no match")
    s, e, score, text = hit
    print(json.dumps({"start": s, "end": e, "in": hms(s), "out": hms(e), "score": score,
                      "matched": text, "link": link(tr["source"], s)}, indent=1))


# ---------- cues ----------

def default_citation(src):
    d = src.get("upload_date") or ""
    date = f"{int(d[6:8])} {MONTHS[int(d[4:6]) - 1]}, {d[:4]}" if len(d) == 8 else ""
    return {"title": src.get("title") or "", "date": date, "publication": src.get("channel") or ""}


def cmd_cues(a):
    """quotes.json -> Citation v2 cue JSON (for agent-motion/titles_fcpxml.py), clip list, clip script."""
    qfile = Path(a.quotes)
    spec = json.loads(qfile.read_text())
    tdir = Path(a.transcripts or qfile.parent / "transcripts")
    out = Path(a.out or qfile.parent / "citations")
    out.mkdir(parents=True, exist_ok=True)
    files = {k: out / v for k, v in (("cues", "citation_cues.json"), ("clips", "clips.json"),
                                      ("sh", "download_clips.sh"), ("md", "citations.md"))}
    for f in files.values():
        guard(f, a.force)

    cache, cues, clips, sh, md = {}, [], [], ["#!/bin/sh", "# Full-quality video for each quote, padded.",
                                                 "# Run from the batch folder; writes into clips/.", "set -e",
                                                 "mkdir -p clips"], ["# Citations", ""]
    at = 0.0
    for q in spec["quotes"]:
        sid = q["source"]
        if sid not in cache:
            cache[sid] = json.loads((tdir / f"{sid}.json").read_text())
        tr = cache[sid]
        src = tr["source"]
        hit = locate(tr, q["text"], q.get("approx"))
        if not hit:
            print(f"!! {q['id']}: could not locate quote in {sid}", file=sys.stderr)
            continue
        start, end, score, matched = hit
        if score < 0.8:
            print(f"!! {q['id']}: weak match ({score}); check by ear: {matched!r}", file=sys.stderr)
        pb, pa = q.get("pad_before", a.pad_before), q.get("pad_after", a.pad_after)
        pin, pout = max(0.0, start - pb), end + pa
        if src.get("duration"):
            pout = min(pout, src["duration"])
        cit = {**default_citation(src), **spec.get("sources", {}).get(sid, {}).get("citation", {}), **q.get("citation", {})}
        texts = {SLOTS[k]: v for k, v in cit.items() if k in SLOTS and v}
        dur = q.get("card_duration", max(5.0, min(end - start, 10.0)))
        # Episode time if the miner tied the quote to a moment in our episode; else lay drafts end to end.
        cue_at = q.get("episode_at", at)
        cues.append({"template": q.get("template", CITATION_TEMPLATE), "at": round(cue_at, 2), "duration": dur,
                     "name": q["id"], "texts": texts, "episode_at_set": "episode_at" in q,
                     "source": {"id": sid, "url": src.get("url"), "in": start, "out": end}})
        at = max(at, cue_at) + dur + 2
        clips.append({"id": q["id"], "source_id": sid, "source_url": src.get("url"), "title": src.get("title"),
                      "quote": q["text"], "matched": matched, "score": score,
                      "in": start, "out": end, "padded_in": round(pin, 2), "padded_out": round(pout, 2),
                      "in_tc": hms(start), "out_tc": hms(end), "link": link(src, start),
                      "local_audio": str((qfile.parent / "audio" / f"{sid}.m4a").resolve()),
                      "episode_at": q.get("episode_at"), "episode_context": q.get("episode_context", ""),
                      "why": q.get("why", ""), "tags": q.get("tags", []), "citation": cit})
        sh.append(f"yt-dlp --cookies-from-browser firefox --extractor-args 'youtube:player_client=tv,web_safari,mweb' "
                  f"-f 'bv*[height<=1080]+ba/b' --download-sections '*{pin:.2f}-{pout:.2f}' --force-keyframes-at-cuts "
                  f"--no-overwrites -o 'clips/{q['id']}.%(ext)s' {shlex.quote(src.get('url') or sid)}")
        md += [f"## {q['id']}  ({hms(start)}–{hms(end)}, match {score})", "",
               f"> {q['text']}", "", f"- {cit.get('author', '')} · *{cit['title'].replace(chr(10), ' ')}* · {cit['date']} · {cit['publication']}",
               f"- {link(src, start)}", f"- why: {q.get('why', '')}"]
        if "episode_at" in q:
            md.append(f"- episode {hms(q['episode_at'])}: {q.get('episode_context', '')}")
        md.append("")

    files["cues"].write_text(json.dumps({"project": spec.get("project", f"{qfile.parent.name} citations"),
                                         "fps": spec.get("fps", 29.97), "cues": cues}, ensure_ascii=False, indent=1))
    files["clips"].write_text(json.dumps({"pad_before": a.pad_before, "pad_after": a.pad_after, "clips": clips},
                                         ensure_ascii=False, indent=1))
    files["sh"].write_text("\n".join(sh) + "\n")
    files["sh"].chmod(0o755)
    files["md"].write_text("\n".join(md))
    for f in files.values():
        print("wrote", f)


def cmd_audio_clips(a):
    """Cut padded audio previews from local audio (new files under citations/audio_clips)."""
    clips = json.loads(Path(a.clips).read_text())["clips"]
    out = Path(a.out or Path(a.clips).parent / "audio_clips")
    out.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    for c in clips:
        dst = out / f"{c['id']}.m4a"
        guard(dst, a.force)
        subprocess.run(["ffmpeg", "-v", "error", "-n" if not a.force else "-y", "-ss", str(c["padded_in"]),
                        "-to", str(c["padded_out"]), "-i", c["local_audio"], "-ac", "1", "-c:a", "aac",
                        "-b:a", "96k", str(dst)], check=True)
        print("wrote", dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("transcribe", help="audio -> transcripts/<id>.json/.md with word timestamps (mlx-whisper)")
    p.add_argument("audio", nargs="+")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--prompt", help="initial prompt (default: title + description)")
    p.add_argument("--allow-short", action="store_true", help="transcribe even if audio decodes shorter than the video")
    p.add_argument("--out"), p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_transcribe)

    p = sub.add_parser("captions", help="YouTube .json3 auto-captions -> transcript (fast fallback)")
    p.add_argument("json3", nargs="+")
    p.add_argument("--out"), p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_captions)

    p = sub.add_parser("itt", help="FCP iTT captions -> transcript (our own episodes)")
    p.add_argument("itt")
    p.add_argument("--id", required=True), p.add_argument("--title"), p.add_argument("--media")
    p.add_argument("--fix", action="append", default=[], metavar="REGEX=>TEXT")
    p.add_argument("--out", required=True), p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_itt)

    p = sub.add_parser("search",help="regex over transcripts, with timestamps and links")
    p.add_argument("pattern")
    p.add_argument("transcripts", nargs="+", help="transcript .json files or a transcripts/ dir")
    p.add_argument("-C", "--context", type=int, default=1)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("locate", help="snap quote text to exact word timestamps")
    p.add_argument("transcript"), p.add_argument("quote")
    p.add_argument("--near", type=float, help="approximate seconds, to disambiguate")
    p.set_defaults(fn=cmd_locate)

    p = sub.add_parser("cues", help="quotes.json -> citation cues, clip list, clip download script")
    p.add_argument("quotes")
    p.add_argument("--transcripts"), p.add_argument("--out")
    p.add_argument("--pad-before", type=float, default=PAD_BEFORE)
    p.add_argument("--pad-after", type=float, default=PAD_AFTER)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_cues)

    p = sub.add_parser("audio-clips", help="cut padded audio previews from local audio")
    p.add_argument("clips", help="citations/clips.json")
    p.add_argument("--out"), p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_audio_clips)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
