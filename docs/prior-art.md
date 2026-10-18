# Prior art (surveyed 2026-10-18, not yet read in depth)

Final Cut / FCPXML + Claude:
- **ButterCut** (github.com/barefootford/buttercut): Claude Code skills plus a Ruby lib. WhisperX transcription → rough-cut timelines for FCP/Premiere/Resolve. The closest match to our `agent-editing`.
- **fcp-mcp-server** (PyPI): FCPXML MCP. Whisper transcription, filler-word and silence removal on podcast timelines.
- **fcp-mcp** (dreliq9): FCPXML engine + AppleScript bindings, ~88 tools.
- **daredev256/fcpxml-mcp-server**: smaller, FCPXML output only.
- **cutlass** (github.com/andrewarrow/cutlass): Go library that builds FCPXML from templates.
- **video-use** (browser-use): filler removal + burned subtitles, renders MP4 directly (not FCP).

Audio / transcript pipelines:
- **openclaudia `podcast-edit` skill**: trim, filler/silence removal, −16 LUFS, resemblyzer diarization.
- **danielmiessler/personal_ai_infrastructure `Audioeditor`**: Whisper → Claude classifies fillers/false starts → ffmpeg with crossfades, and a preview-before-cut mode.
- **stephankostov/podcast-transcriber** (WhisperX + pyannote), **MahmoudAshraf97/whisper-diarization** (Whisper + NeMo).

Motion:
- Nothing open-source found that generates .motn. Apple's archived "Motion XML guide" is the reference. "CSV to Motn Generator" (Mac App Store) is a commercial batch tool, so the approach works in practice.

Gaps nobody seems to cover: speaker → camera-angle switching for multicam (our Jev idea),
and context-aware caption cleanup.
