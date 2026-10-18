---
name: citations
description: Mine source material (YouTube lectures, talks, our own past episodes) for citable quotes and turn them into timestamped clips and Citation lower-third cues for the podcast. Use when asked to transcribe a source video, find what someone said about X, pull quotes or clips for an episode, or make citations / lower thirds from a talk or lecture.
---

# Citations: sources → transcripts → quotes → cues and clips

Tool: `agent-citations/citekit.py` (stdlib Python plus `mlx_whisper` and ffmpeg). It never writes over
inputs, and refuses to replace its own outputs without `--force`.

## Batch layout

One folder per subject under `active_edits/<subject>/`:

```
sources/video_sources.txt          the user's list of URLs
sources/audio/<id>.m4a .info.json  from yt-dlp (step 1)
sources/transcripts/<id>.json .md  step 2
podcast/<ep>.json .md              our own episode's captions, imported (step 2b)
sources/quotes.json                step 3, written by you
sources/citations/                 step 4 outputs
```

## 1. Download (the user runs it)

YouTube blocks anonymous yt-dlp here. Give the user this command rather than running it.
It needs Firefox cookies and the tv/safari clients, and keeps the audio small (Whisper only needs 16 kHz mono):

```bash
cd active_edits/<subject>/sources && for id in ID1 ID2; do yt-dlp --cookies-from-browser firefox --extractor-args "youtube:player_client=tv,web_safari,mweb" -f "wa/w" -x --audio-format m4a --postprocessor-args "ExtractAudio:-ac 1 -ar 16000" --write-info-json --write-auto-subs --sub-langs en --sub-format json3 --no-overwrites -o "audio/%(id)s.%(ext)s" "https://youtu.be/$id"; done
```

For a channel's backlog, list it first, then pick: `yt-dlp --flat-playlist --print "%(id)s %(duration_string)s %(title)s" https://www.youtube.com/@CHANNEL/videos`.
Triage titles with Jev (`vibe-classification`) if the list is long.

## 2. Transcribe

- `citekit.py transcribe sources/audio/<id>.m4a`: mlx-whisper large-v3-turbo, word timestamps. The
  initial prompt is the video's title and description, which fixes most name spellings. It runs about 85× realtime on this Mac (a 15 min stretch takes ~35 s; the model downloads once).
- `citekit.py captions sources/audio/<id>.en.json3`: YouTube's auto-captions. Instant, but no punctuation.
  The tv client often doesn't save them.
- 2b. Our own episodes: `citekit.py itt EP.itt --id podcastN --media EP.mp4 --out active_edits/<subject>/podcast --fix 'REGEX=>Right'`.
  FCP's captions mangle names. For episode 1: `--fix '\bver ?m+[iu]l+e?\b=>Vermeule' --fix '\bvermil\b=>Vermeule' --fix '\bAsian Vermeule=>Adrian Vermeule'`.
  Episode 1 also has word-level fixes logged in `podcast/podcast1.fixes.json` (Schmidt→Schmitt etc.), replayed on re-import.

### Fix mistranscriptions as you go (don't ask)

When you notice a *definite* mis-hearing (a name, a garbled quote, a stutter Whisper doubled), fix it:
`citekit.py fix TRANSCRIPT 'old words=>new words' [...] [--near SECONDS]`. It edits `<id>.json/.md` in place
(new words share the old span's timing, matches can cross segments, trailing punctuation carries over),
keeps the untouched engine output as `<id>.raw.json`, and logs every fix in `<id>.fixes.json`. `transcribe`
and `itt` replay that log, so fixes survive a re-run. Unsure? Re-hear the spot instead of guessing:
`ffmpeg -ss T -to T2 -i audio.m4a x.wav && mlx_whisper x.wav --output-format txt`. Fix first, then quote
the fixed words: `locate` matches against the transcript.

## 3. Mine quotes (your judgment)

1. Read our episode transcript, if there is one, and list the claims the hosts make about the
   subject, each with its episode time. Those are the moments a clip can back up or rebut.
2. For each claim, `citekit.py search 'regex' sources/transcripts/` to find candidates, then read the `.md`
   around the hit. Read whole lectures too: the best lines aren't always the ones the hosts named.
3. A good citation is short (5–25 s spoken), self-contained, unmistakably the speaker's own position (not
   him summarizing an opponent), and quotable on a lower third. Keep the transcript's exact words. Don't
   clean them up, or `locate` can't find them.
4. Write `sources/quotes.json`:

```json
{"project": "Ep1 Vermeule citations", "fps": 29.97, "episode": "../podcast/podcast1.json",
 "quotes": [{"id": "publius-weak-exec", "source": "Bw9M01S8MFI", "approx": 1234,
   "text": "exact words from the transcript",
   "episode_at": 2575, "episode_context": "hosts on Hamilton and the Roman dictator",
   "why": "his own statement of the thesis", "tags": ["executive", "Federalist"],
   "citation": {"author": "~Adrian Vermeule", "title": "The Publius Paradox", "date": "5 Jun, 2018",
                "publication": "Chorley Lecture, LSE"}}]}
```

`episode` (relative to quotes.json) is our episode's transcript. With it, each quote's `episode_at` (roughly
when the hosts raise the point) becomes an insert point: the end of the host's sentence running then.
Quote whole thoughts. If the next sentence completes the image or argument, include it (a 5–25 s clip
is the target, not a hard cap).

`citation` defaults to video title, upload date and channel. Put the real venue and date (from the
description) once per lecture in a top-level `"sources": {"<id>": {"citation": {...}}}`. A quote's own
`citation` overrides that. Authors get the show's `~` prefix, and `\n` breaks a long title onto two lines.

Check anything he is *quoting* (Hamilton, Kafka, the Digest) against the original text. Whisper hears
plausible wrong words: in the Publius lecture it gave Kafka's "sacrificial pitchers" as "pictures".

## 4. Cues and clips

`citekit.py cues sources/quotes.json` snaps each quote to word timestamps (fuzzy; it warns if the match score
is < 0.8) and writes to `sources/citations/`:

| File | For |
|---|---|
| `citations.md` | review sheet in episode order: insert time (as recorded, and after earlier inserts), the hosts' words right before the cut, the quote, source/clip times, YouTube `?t=` link |
| `clips.json` | agent-editing: source in/out, padded in/out (default 5 s each side, `--pad-before/--pad-after`, per-quote `pad_before`/`pad_after`), `insert_at`, `insert_at_after_earlier_inserts`, `insert_after` |
| `citation_cues.json` | `agent-motion/titles_fcpxml.py`: Citation v2 lower thirds timed for the episode *with clips inserted*, coming up as he starts speaking. Unplaced quotes are laid end to end |
| `download_clips.sh` | the user runs it: full-quality video for only those padded ranges (`--download-sections`) |

Then `citekit.py audio-clips sources/citations/clips.json` cuts padded audio previews from the local
audio, to check by ear. To place the lower thirds in FCP, follow the `motion-graphics` skill:
`python3 agent-motion/titles_fcpxml.py sources/citations/citation_cues.json -o citations.fcpxml`.

## Notes

- `transcribe` decodes to 16 kHz WAV itself and refuses audio that decodes much shorter than the
  video. A yt-dlp download resumed with a different `-f` splices two codecs into one .m4a (seen
  2026-10-18: AAC-LC then HE-AAC), and ffmpeg silently drops everything after the switch. Re-download
  with `--no-continue`. Never resume across format changes.
- Verify a clip by ear, or cheaply: `mlx_whisper citations/audio_clips/<id>.m4a --output-format txt` should
  show the quote with a few seconds of lead-in and tail.

- Whisper timestamps are good to about ±0.3 s at word level. That's why the clip pads exist. FCP iTT captions
  only time whole lines, so `itt` spreads the words evenly across each line.
- The Wispr Flow connector reads Meeting Recorder transcripts only. It can't transcribe a file.
