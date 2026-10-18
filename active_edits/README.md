# active_edits/

Local working folders, one per subject, e.g. `active_edits/vermeule/`. Everything here except this
README is gitignored: downloads, transcripts, mined quotes, clip lists, FCPXML drafts.

Layout (see `.claude/skills/citations/SKILL.md`):

    <subject>/sources/video_sources.txt   the URLs
    <subject>/sources/audio/              yt-dlp audio + .info.json
    <subject>/sources/transcripts/        <id>.json/.md (+ .raw.json, .fixes.json)
    <subject>/sources/quotes.json         mined quotes
    <subject>/sources/citations/          citations.md, clips.json, citation_cues.json, citations.fcpxml
    <subject>/podcast/                    our own episode's transcript
