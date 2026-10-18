# vibe-podcast

Goal: an agent that handles podcast video editing end to end, through a set of skills,
for the Tiresias Foundation Podcast. Episodes 1–4 exist (FCP libraries in `~/Movies/Podcast*`).
Episode 5 was started on 2026-01-04 (`~/Movies/Podcast5`).

## Subtask folders

| Folder | Scope | Status |
|---|---|---|
| `agent-motion/` | Title cards, citation lower thirds (Apple Motion templates → FCPXML) | tooling started, skill `motion-graphics` |
| `agent-subtitles/` | FCP's built-in captions as a first pass, then an LLM cleanup pass (Sonnet/Haiku) with episode context | empty |
| `agent-citations/` | Find what's quoted or referenced, then produce citation cues for `agent-motion` | empty |
| `agent-editing/` | Rough cut, speaker-based camera choice (Jev for "who is talking/whose angle"), FCPXML timelines | empty |
| `agent-sound/` | Levels, loudness, noise | empty |
| `scratch/` | throwaway | |

## Tools on this machine (checked 2026-10-18)

- Final Cut Pro 11.0.1 (FCPXML up to 1.13; DTDs inside the app bundle), Motion 5.9. Neither has
  an AppleScript dictionary we rely on. FCP reads FCPXML (`open -a "Final Cut Pro" x.fcpxml`).
  Motion files are XML, so edit them directly (see `.claude/skills/motion-graphics`).
- ffmpeg/ffprobe, uv, python3.14, node, yt-dlp (Homebrew). No local Whisper yet.
- Blender (has an MCP), OBS.
- TypeSafe / Jev (`vibe-classification`, `typesafe-ai` skills) for cheap typed judgments,
  e.g. which speaker is on, or whether a line is a quote that needs a citation.
- FCP libraries are bundles. Event DBs (`CurrentVersion.fcpevent`) are SQLite, and `strings`
  on them recovers title texts that were used.

## Conventions

- Don't commit media, FCP libraries, or renders (see `.gitignore`). Do commit templates
  (`.motn`/`.moti`) and small specs.
- Never write into the user's FCP libraries or Motion Templates folder without asking.
  Generate FCPXML and new files instead.
- See `docs/prior-art.md` for other people's projects worth borrowing from.
