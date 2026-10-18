---
name: motion-graphics
description: Make per-episode podcast graphics from the show's Apple Motion templates (main title card, citation lower thirds) and place them in Final Cut Pro via FCPXML. Use when asked for a title card, citation/lower third, on-screen text, or anything involving .motn/.moti files or Motion.
---

# Motion graphics for the podcast

Motion 5.9 has **no AppleScript dictionary and no CLI renderer**. Everything here works
by treating Motion files as XML (`ozml`), and by handing Final Cut Pro FCPXML that
references the installed title templates. Final Cut does the rendering.

Tools live in `agent-motion/`:

| Tool | What it does |
|---|---|
| `motionkit.py inspect FILE [--json]` | Layer tree, text layers (text/font/size/position), timing in seconds, what's published to FCP, media refs |
| `motionkit.py set-text IN OUT --set "KEY=TEXT" ...` | Rewrite text layers. KEY = layer id, layer name, or current text. `\n` for line breaks. Fixes `styleRun` lengths (UTF-16) so Motion doesn't choke |
| `motionkit.py keyframes FILE [--grep X] [--all]` | Every animated parameter with keyframe times/values (rotation is in radians) |
| `motionkit.py preview FILE --at 1.9 3.2 [--open]` | Writes copies parked at those times; `--open` opens them in Motion in the background (`open -g`) for an `app_screenshot` |
| `motionkit.py install FILE --name NAME` | Copy a project into Motion's Titles folder as an FCP title template |
| `titles_fcpxml.py SPEC.json -o OUT.fcpxml` | Cue list → FCPXML project with titles at the right times, texts filled in |

## The show's templates

Installed under `~/Library/Containers/com.apple.motionapp/Data/Movies/Motion Templates.localized/Titles.localized/Templates/`
(FCP uid form: `~/Titles.localized/Templates/<Name>/<Name>.moti`). Snapshots of the
two main ones are in `agent-motion/*.motn`.

- **TF_Podcast_title**: main title card, 5 s, 29.97, 1080p. Text layers:
  `Tiersias Foundation Podcast` (shows "Tiresias Foundation Podcast"; the layer name has a typo, keep using it as the key) and
  `Episode 4: Carl Schmitt` (the per-episode line, Futura Medium). It publishes one Drop Zone.
- **Citation v2**: lower third for quotes and sources, PT Serif. Text layers:
  `~Author Lastname` (italic; the show prefixes with `~`), `Person Writes Silly Headline to`
  (title of the work, may be two lines), `20 Apr, 1969` (date), `Publication`.
- **Citation v2 no pub**: same without the publication line. Also Citation v1, Black/Orange/Yellow/PeeTitle, Minister_Types.

Past usage (from the Podcast3/4 libraries): Timothy Snyder, Carl Schmitt, Xunzi,
`~Eric L. Hutton, trans.`, `~Armando Iannucci, dir.`, `95 U.S. 602`. Translators and
directors get a role suffix. Court cases go in the author slot.

## Workflow

1. `python3 agent-motion/motionkit.py inspect "<template>.moti"` to get the text layer keys.
2. Write a cue JSON (see `agent-motion/examples/ep_demo.json`): template, `at` (seconds
   on the episode timeline), optional `duration`, `texts` map.
3. `python3 agent-motion/titles_fcpxml.py cues.json -o titles.fcpxml`, then validate:
   `xmllint --noout --dtdvalid <copy of FCPXMLv1_11.dtd> titles.fcpxml`. The DTDs are in
   `/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources/`.
   Copy one first, because xmllint fails on the path with spaces.
4. The user imports it into FCP (`open -g -a "Final Cut Pro" titles.fcpxml`, then picks a library).
   The titles sit connected above a gap, so they can be copied onto the real edit.

For a one-off baked card (e.g. a thumbnail or a card with a styling change FCP can't
override), use `set-text` on the `.motn` and `open -g -a Motion OUT.motn` for the user to
eyeball or export.

## Known unknowns (verify, then update this file)

- **FCPXML `<text>` order → template layer mapping.** The generator emits one `<text>`
  per text layer in **document order of the Motion file**. Confirm in FCP that the
  Citation fields land in the right slots. If the order is wrong, fix `text_layers()` in
  `titles_fcpxml.py`.
- Whether the `text-style-def` (font family + face + size only) overrides the template's
  colour/tracking. If it does, we may need to emit fuller styles.
- Zero-click FCP import: add `<import-options>` (library location ending in `.fcpbundle`)
  to the FCPXML and FCP imports without the library picker. A new path makes a throwaway
  library. Not built yet, but it's the way to test the two questions above without the user.

## Seeing and rendering (verified 2026-10-18)

- **Preview frames:** `motionkit.py preview FILE --at T --open`, then computer-use
  `app_screenshot` on Motion (bundle `com.apple.motionapp`), then zoom on the canvas.
  Close the window via `app_menu File > Close`. Typing into Motion's playhead field from
  the background does NOT move the playhead. The `<currentFrame>` copy is the reliable route.
- **Rendering:** computer use can't press File > Share (Export Movie, Save Current Frame).
  Ask the user to click Export. Shell `screencapture` lacks Screen Recording permission.
- Never `open -a` without `-g`. The user is working on the same screen.

## Animation (what the XML exposes)

Keyframes are `curve > keypoint{time, value, in/out tangents}` under any parameter
(Transform Position/Rotation/Scale, Blending Opacity, filter params). Behaviors (Gather In,
Pen Speed/Pressure) are their own nodes with timing and Controls params. So we can read the
full choreography, and retime, offset, or add keyframes programmatically. Then preview-and-screenshot to check.
TF_Podcast_title choreography: Tiresias figures (Group 1/2) slide in from ±400 px to 1.5 s,
then sway ±10 px / ±2° to 4.87 s. The snake image pair pops in at 1.74 s (scale 0.17→0.62 by
2.1 s, masked by rounded rectangles) and lunges between keyframes at 2.1/3.17/4.14/4.87 s.
The title line fades in at 1.5–1.7 s with Gather In from 1.0 s, and the episode line Gathers In at 2.37 s.

## ozml notes

- Times are `"value timescale flags epoch"`; seconds = value/timescale.
- Text content: `scenenode[factory=Text] > parameter[name=Object] > parameter[id=369] > text`.
  Styling is `styleRun style=ID offset length`, so a length mismatch breaks styling.
- Factories at the top map `factoryID` → kind (Text, Shape, Replicator, Image...). The ids
  differ per file, so always resolve them through the factory table.
- Apple's (old, still mostly right) reference: Motion XML guide on developer.apple.com archive.
