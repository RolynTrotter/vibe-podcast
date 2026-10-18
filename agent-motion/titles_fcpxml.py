#!/usr/bin/env python3
"""Turn a list of title cues into FCPXML that Final Cut Pro can import.

Input is JSON (file or stdin):

  {"project": "Ep5 titles", "fps": 29.97,
   "cues": [
     {"template": "Citation v2", "at": 754.2, "duration": 5,
      "texts": {"~Author Lastname": "Timothy Snyder",
                "Person Writes Silly Headline to": "On Tyranny",
                "Publication": "Tim Duggan Books", "20 Apr, 1969": "2017"}},
     {"template": "TF_Podcast_title", "at": 0,
      "texts": {"Episode 4: Carl Schmitt": "Episode 5: Something"}}]}

`texts` keys are the template's text layer names (see `motionkit.py inspect`) or
its current placeholder text; layers you leave out keep the placeholder.

Output: one project with a gap on the spine and each title connected above it
at its time, ready to copy/paste onto the real edit (or replace the gap with
the episode's compound clip). Templates are looked up in Motion's Titles folder.
"""
import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).parent))
import motionkit  # noqa: E402

TITLES = motionkit.TEMPLATES_ROOT / "Titles.localized"
MOTION_DEFAULT_SIZE = 48.0
FONT_SWIFT = """
import AppKit
for n in CommandLine.arguments.dropFirst() {
  if let f = NSFont(name: n, size: 12) {
    print(n + "\\t" + (f.familyName ?? n) + "\\t" + ((f.fontDescriptor.object(forKey: .face) as? String) ?? "Regular"))
  }
}
"""


def find_template(name):
    hits = sorted(TITLES.rglob(f"{name}.moti"))
    if not hits:
        sys.exit(f"no installed title template named {name!r} under {TITLES}")
    path = hits[0]
    return path, "~/" + str(path.relative_to(motionkit.TEMPLATES_ROOT))


def font_faces(postscript_names):
    names = sorted({n for n in postscript_names if n})
    if not names:
        return {}
    out = subprocess.run(["swift", "-e", FONT_SWIFT, *names], capture_output=True, text=True).stdout
    return {ps: (fam, face) for ps, fam, face in (l.split("\t") for l in out.splitlines() if l.count("\t") == 2)}


def frames(t, fps):
    """Seconds -> FCPXML rational time snapped to the frame grid."""
    fd = Fraction(1001, 30000) if abs(fps - 29.97) < 0.01 else Fraction(1001, 24000) if abs(fps - 23.976) < 0.01 \
        else Fraction(1, round(fps))
    n = round(Fraction(t) / fd)
    v = n * fd
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s", fd


def text_layers(path):
    info = motionkit.summary(path)
    return [n for n in info["nodes"] if n["kind"] == "Text"], info["duration_s"]


def import_options(library):
    """FCP imports straight into this .fcpbundle (created if missing), no library picker."""
    url = Path(library).expanduser().resolve().as_uri()
    return ("  <import-options>\n"
            f'    <option key="library location" value={quoteattr(url)}/>\n'
            '    <option key="copy assets" value="0"/>\n'
            '    <option key="suppress warnings" value="1"/>\n'
            "  </import-options>\n")


def build(spec, library=None, style="none"):
    fps = spec.get("fps", 29.97)
    _, fd = frames(0, fps)
    templates, styles, cues_xml = {}, [], []
    for cue in spec["cues"]:
        if cue["template"] not in templates:
            path, uid = find_template(cue["template"])
            layers, dur = text_layers(path)
            templates[cue["template"]] = {"id": f"r{len(templates) + 2}", "uid": uid, "layers": layers, "dur": dur}
    faces = {} if style == "none" else font_faces(l.get("font") for t in templates.values() for l in t["layers"])

    end = 0
    for i, cue in enumerate(spec["cues"]):
        t = templates[cue["template"]]
        wanted = dict(cue.get("texts", {}))
        texts = []
        for layer in t["layers"]:
            val = layer["text"] or ""
            for key in (layer["id"], layer["name"], (layer["text"] or "").strip()):
                if key in wanted:
                    val = wanted.pop(key)
                    break
            body = escape(val).replace(chr(10), "&#10;")
            if style == "none":  # bare text: the template keeps its own font, size, colour
                texts.append(f"<text>{body}</text>")
                continue
            sid = f"ts{i}_{len(texts)}"
            fam, face = faces.get(layer.get("font"), (layer.get("font") or "Helvetica", "Regular"))
            size = layer.get("size") or MOTION_DEFAULT_SIZE  # absent Size param = Motion default
            styles.append(f'<text-style-def id="{sid}"><text-style font={quoteattr(fam)} fontFace={quoteattr(face)} fontSize="{size:g}"/></text-style-def>')
            texts.append(f'<text><text-style ref="{sid}">{body}</text-style></text>')
        if wanted:
            names = [l["name"] for l in t["layers"]]
            sys.exit(f"cue {i}: unknown text layers {list(wanted)}; {cue['template']} has {names}")
        dur_s = cue.get("duration", t["dur"])
        off, _ = frames(cue["at"], fps)
        dur, _ = frames(dur_s, fps)
        end = max(end, cue["at"] + dur_s)
        name = cue.get("name") or f"{next(iter(cue.get('texts', {}).values()), cue['template'])} - {cue['template']}"
        own_styles, styles = styles, []
        cues_xml.append(
            f'<title ref="{t["id"]}" lane="1" offset="{off}" start="0s" duration="{dur}" name={quoteattr(name)}>\n'
            + "\n".join("  " + x for x in texts + own_styles) + "\n</title>")

    total, _ = frames(end + 1, fps)
    fmt_name = {Fraction(1001, 30000): "FFVideoFormat1080p2997", Fraction(1001, 24000): "FFVideoFormat1080p2398"}.get(fd, "FFVideoFormat1080p30")
    fd_s = f"{fd.numerator}/{fd.denominator}s"
    res = [f'<format id="r1" name="{fmt_name}" frameDuration="{fd_s}" width="1920" height="1080"/>']
    res += [f'<effect id="{t["id"]}" name={quoteattr(n)} uid={quoteattr(t["uid"])}/>' for n, t in templates.items()]
    body = "\n".join("            " + line for c in cues_xml for line in c.splitlines())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.11">
{import_options(library) if library else ""}  <resources>
    {chr(10).join('    ' + r for r in res).strip()}
  </resources>
  <library>
    <event name={quoteattr(spec.get("event", "Agent titles"))}>
      <project name={quoteattr(spec.get("project", "Titles"))}>
        <sequence format="r1" duration="{total}" tcStart="0s" tcFormat="NDF">
          <spine>
            <gap name="Gap" offset="0s" start="0s" duration="{total}">
{body}
            </gap>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="JSON spec (default stdin)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--library", help="target .fcpbundle for zero-click import (created if missing)")
    ap.add_argument("--style", choices=["none", "font"], default="none",
                    help="none: bare text, template styling wins; font: also send font/face/size")
    ap.add_argument("--push", action="store_true", help="send to Final Cut Pro now, in the background")
    a = ap.parse_args()
    if a.push and not a.library:
        sys.exit("--push needs --library, or FCP blocks on a library picker")
    spec = json.load(open(a.spec) if a.spec else sys.stdin)
    out = motionkit.safe_output(a.out, *([a.spec] if a.spec else []))
    out.write_text(build(spec, a.library, a.style), encoding="utf-8")
    print("wrote", a.out)
    if a.push:
        subprocess.run(["open", "-g", "-a", "Final Cut Pro", a.out], check=True)
        print("sent to Final Cut Pro ->", a.library)
    else:
        print("import with: open -g -a 'Final Cut Pro'", quoteattr(a.out))


if __name__ == "__main__":
    main()
