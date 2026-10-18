#!/usr/bin/env python3
"""motionkit: read and rewrite Apple Motion project/template files (.motn/.moti) as XML.

Motion has no AppleScript dictionary or CLI renderer, but its files are plain
"ozml" XML. This tool covers the parts we need for podcast graphics:

  inspect      layer tree, text content, fonts, timing, published params, media refs
  set-text     replace the text of one or more text layers (keeps style runs valid)
  install      copy a project into Motion's Titles folder as an FCP title template

Times in ozml are rational "value timescale flags epoch" strings; 596596/120000 s
is 4.97 s, i.e. frame 149 at 29.97 fps.
"""
import argparse
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE ozxmlscene>\n'
NODE_TAGS = {"layer", "group", "scenenode", "footage", "clip", "behavior", "filter", "mask"}
TEMPLATES_ROOT = Path.home() / "Library/Containers/com.apple.motionapp/Data/Movies/Motion Templates.localized"
TEXT_PARAM_ID = "369"  # Object > Text


def parse_time(s):
    if not s:
        return None
    v, scale = s.split()[:2]
    return int(v) / int(scale)


def load(path):
    return ET.parse(path)


def save(tree, path):
    body = ET.tostring(tree.getroot(), encoding="unicode").replace(" />", "/>")
    Path(path).write_text(HEADER + body + "\n", encoding="utf-8")


def factories(root):
    return {f.get("id"): f.findtext("description") for f in root.findall("factory")}


def utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def text_param(node):
    obj = node.find("parameter[@name='Object']")
    return None if obj is None else obj.find(f"parameter[@id='{TEXT_PARAM_ID}']")


def text_info(node):
    st = node.find("style")
    info = {}
    if st is not None:
        info["font"] = st.findtext("parameter[@name='Font']/font")
        size = st.find("parameter[@name='Size']")
        if size is not None:
            info["size"] = float(size.get("value", size.get("default", "nan")))
    tp = text_param(node)
    info["text"] = tp.findtext("text") if tp is not None else None
    info["style_runs"] = len(node.findall("styleRun"))
    return info


def position(node):
    pos = node.find("parameter[@name='Properties']//parameter[@name='Position']")
    if pos is None:
        return None
    try:
        return [round(float(pos.find(f"parameter[@name='{a}']").get("value", 0)), 1) for a in "XY"]
    except (AttributeError, TypeError, ValueError):
        return None


def walk(elem, facs, depth=0):
    for c in elem:
        if c.tag not in NODE_TAGS:
            continue
        t = c.find("timing")
        item = {
            "tag": c.tag,
            "id": c.get("id"),
            "name": c.get("name"),
            "kind": facs.get(c.get("factoryID"), c.tag),
            "depth": depth,
        }
        if t is not None:
            item["in"] = parse_time(t.get("in"))
            item["out"] = parse_time(t.get("out"))
        if item["kind"] == "Text":
            item.update(text_info(c))
        p = position(c)
        if p:
            item["pos"] = p
        yield item
        yield from walk(c, facs, depth + 1)


def media_refs(root):
    out = []
    for clip in root.iter("clip"):
        url = clip.findtext(".//pathURL")
        rel = clip.findtext(".//relativeURL")
        if url or rel:
            p = unquote(urlparse(url).path) if url and url.startswith("file:") else url
            out.append({"clip": clip.get("name"), "path": p, "relative": unquote(rel) if rel else None,
                        "exists": bool(p) and Path(p).exists()})
    return out


def summary(path):
    tree = load(path)
    root = tree.getroot()
    s = root.find("scene/sceneSettings")
    fps = float(s.findtext("frameRate"))
    if s.findtext("NTSC") == "1":
        fps = fps * 1000 / 1001
    facs = factories(root)
    pub = root.find("scene/publishSettings")
    return {
        "file": str(path),
        "motion_version": root.findtext("displayversion"),
        "size": [int(s.findtext("width")), int(s.findtext("height"))],
        "fps": round(fps, 3),
        "duration_frames": int(s.findtext("duration")),
        "duration_s": round(int(s.findtext("duration")) / fps, 3),
        "published": [t.attrib for t in pub.findall("target")] if pub is not None else [],
        "nodes": list(walk(root.find("scene"), facs)),
        "media": media_refs(root),
    }


def cmd_inspect(a):
    info = summary(a.file)
    if a.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return
    print(f"{info['file']}\n  Motion {info['motion_version']}  {info['size'][0]}x{info['size'][1]}  "
          f"{info['fps']} fps  {info['duration_frames']} frames ({info['duration_s']} s)")
    print("  published to FCP:", ", ".join(t.get("name", "?") for t in info["published"]) or "(none)")
    print("  layers:")
    for n in info["nodes"]:
        if n["tag"] == "group" or (n["kind"] in ("Channel",) and not a.all):
            continue
        timing = f"{n['in']:.2f}-{n['out']:.2f}s" if n.get("in") is not None and n.get("out", 0) > 0 else ""
        line = f"    {'  ' * n['depth']}{n['kind']:<10} [{n['id']}] {n['name']!r} {timing}"
        if n.get("pos"):
            line += f" @{n['pos']}"
        print(line)
        if n["kind"] == "Text":
            extra = f" ({n['style_runs']} style runs)" if n["style_runs"] > 1 else ""
            print(f"    {'  ' * n['depth']}           text={n['text']!r} font={n.get('font')} size={n.get('size')}{extra}")
    if info["media"]:
        print("  media:")
        for m in info["media"]:
            print(f"    {m['clip']}: {m['relative'] or m['path']} {'' if m['exists'] else '(MISSING)'}")


def find_text_node(root, key):
    facs = factories(root)
    texts = [n for n in root.iter("scenenode") if facs.get(n.get("factoryID")) == "Text"]
    hits = [n for n in texts if n.get("id") == key] or [n for n in texts if n.get("name") == key]
    if not hits:
        hits = [n for n in texts if (text_param(n).findtext("text") or "").strip() == key.strip()]
    if len(hits) != 1:
        names = ", ".join(f"[{n.get('id')}] {n.get('name')!r}" for n in texts)
        sys.exit(f"text layer {key!r}: {len(hits)} matches. Text layers: {names}")
    return hits[0]


def set_text(root, key, new, rename=False):
    node = find_text_node(root, key)
    tp = text_param(node).find("text")
    tp.text = new
    runs = node.findall("styleRun")
    if len(runs) > 1:
        print(f"warning: {node.get('name')!r} had {len(runs)} style runs; collapsing to the first style", file=sys.stderr)
        for r in runs[1:]:
            node.remove(r)
    if runs:
        runs[0].set("offset", "0")
        runs[0].set("length", str(utf16_len(new)))
    if rename:
        node.set("name", new.splitlines()[0][:40] if new else node.get("name"))
    return node


def cmd_set_text(a):
    tree = load(a.file)
    for pair in a.set:
        key, _, val = pair.partition("=")
        val = val.replace("\\n", "\n")
        node = set_text(tree.getroot(), key, val, a.rename)
        print(f"[{node.get('id')}] -> {val!r}")
    save(tree, a.out)
    print("wrote", a.out)


def cmd_install(a):
    src = Path(a.file)
    name = a.name or re.sub(r"_\d{4}-\d{2}-\d{2}_\d{4}$", "", src.stem)
    dest = TEMPLATES_ROOT / f"{a.kind}.localized" / (a.category or "Templates") / name
    if dest.exists() and not a.force:
        sys.exit(f"{dest} exists; pass --force to overwrite (Motion keeps its own copy, back it up first)")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "Media").mkdir(exist_ok=True)
    shutil.copy(src, dest / f"{name}.moti")
    print("installed", dest / f"{name}.moti", "- restart FCP or reopen the Titles browser to see it")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("inspect")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="include channel/parameter nodes")
    p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("set-text", help="KEY is a text layer's id, name, or current text")
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--set", action="append", required=True, metavar="KEY=TEXT", help=r"use \n for line breaks")
    p.add_argument("--rename", action="store_true", help="also rename the layer to its new text")
    p.set_defaults(fn=cmd_set_text)
    p = sub.add_parser("install")
    p.add_argument("file")
    p.add_argument("--name")
    p.add_argument("--kind", default="Titles", choices=["Titles", "Generators", "Effects", "Transitions"])
    p.add_argument("--category")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_install)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
