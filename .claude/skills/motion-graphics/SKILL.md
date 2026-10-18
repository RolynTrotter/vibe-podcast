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
4. The user imports it into FCP (`open -a "Final Cut Pro" titles.fcpxml`, then picks a library).
   The titles sit connected above a gap, so they can be copied onto the real edit.

For a one-off baked card (e.g. a thumbnail or a card with a styling change FCP can't
override), use `set-text` on the `.motn` and `open -a Motion OUT.motn` for the user to
eyeball or export.

## Known unknowns (verify, then update this file)

- **FCPXML `<text>` order → template layer mapping.** The generator emits one `<text>`
  per text layer in **document order of the Motion file**. Confirm in FCP that the
  Citation fields land in the right slots. If the order is wrong, fix `text_layers()` in
  `titles_fcpxml.py`.
- Whether the `text-style-def` (font family + face + size only) overrides the template's
  colour/tracking. If it does, we may need to emit fuller styles.
- No way to render a preview frame without the GUI. Screen capture from the shell needs
  Screen Recording permission. Computer use (if enabled) can screenshot Motion.
  Setting `<currentFrame>` in a copy of the .motn makes Motion open at that frame.

## ozml notes

- Times are `"value timescale flags epoch"`; seconds = value/timescale.
- Text content: `scenenode[factory=Text] > parameter[name=Object] > parameter[id=369] > text`.
  Styling is `styleRun style=ID offset length`, so a length mismatch breaks styling.
- Factories at the top map `factoryID` → kind (Text, Shape, Replicator, Image...). The ids
  differ per file, so always resolve them through the factory table.
- Apple's (old, still mostly right) reference: Motion XML guide on developer.apple.com archive.
