# Storyboard Studio 0.9 / FolderExporter 1.10 / Subtitler 0.6

Use a copy of your test project for the first checks. Close the older app versions before opening these builds.

## Storyboard Studio — changes to test

- [ ] Drop an image from Finder between two cards. The insertion line appears and the new card stays at that position.
- [ ] Drop a cleanup on the second, third and later cards, on both normal and Retina-scaled displays. Only the intended card receives it.
- [ ] Reorder cards and drag between Holding Area and the storyboard.
- [ ] Compare card-number alignment with the drawing's left edge in large and small windows.
- [ ] Storyboard/Clean up retains its active highlight and has a rounded hover outline. Clean up retains the gray background you preferred.
- [ ] The disconnected-media glow is substantially quieter. Missing one component leaves all available components visible and keeps the missing component listed.
- [ ] Print → Export all cards as PNG immediately displays a saving/progress overlay and reports completion.
- [ ] Re-export the same cards: tracked outputs update without numbered duplicates. Unknown/externally changed files remain protected.
- [ ] File naming fields grow vertically as long patterns are entered. Padding starts at 1 in a fresh profile and retains a manually saved choice.
- [ ] Set a shared cleanup-component pattern, including `{component_name}` if desired, and compare its preview with FolderExporter's project-name output.
- [ ] Cmd/Ctrl+S saves the project, Studio Link and changed/missing rough PNGs. Repeating it without changes should leave the PNGs untouched.
- [ ] Change a blank card's visible note/drawing and save: its PNG should update.
- [ ] Closing shows Saving and keeps the window open if saving fails.
- [ ] Create a Slight modify card from a regular card. Its context menu offers **Make regular card** in bold.
- [ ] A Slight modify card no longer offers creating another modification from it. In scissors mode, choose a regular source or switch to blank-card creation.
- [ ] In an existing nested modification family, delete intermediate 3A: 3B retains the original family's number and remains 3B.
- [ ] Move a modification's source off the board: the surviving modification retains its last source number.
- [ ] Delete 1A while 1B survives; its letter is not recycled. Moving the modification preserves its artwork, cleanup, text link and source reminder.
- [ ] Add normal and lettered cards after cleanups exist. Saving keeps those cleanups, adds the new roughs and updates shared identities/order separately.
- [ ] Change naming settings or reorder cards, then save: managed cleanup/component/reference/archive paths update together. Custom external attachments keep their names. A deliberate filename collision stops safely.
- [ ] Replace a tracked rough PNG in its chapter folder with a cleanup using that location. Open/focus/Refresh Storyboard Studio: the replacement becomes cleanup; the original rough is recreated in the configured archive. Saving again preserves the cleanup.
- [ ] If identification is ambiguous, the collision window includes **Use existing file as cleanup**.
- [ ] Place correctly named manual cleanup components in a registered chapter folder. They link to the existing card and stack bottom-to-top; a whole frame remains a reference.
- [ ] A random image that does not match the complete naming pattern remains ignored and untouched. Ambiguous names never attach one file to several independent cards.
- [ ] Remove a cleanup or one component, then Refresh/reopen. Its unchanged file remains disconnected; the original media is kept. A new replacement or explicit Attach cleanup can reconnect it. Saving keeps any original rough in its safe archive.
- [ ] Reorder managed components manually, then refresh/save. Discovery must retain that order while the file rename transaction runs.
- [ ] Copy a larger file into a chapter folder: incomplete/unreadable files are retried briefly instead of immediately becoming broken cleanup links.
- [ ] Prepare Video → **Media locations** lists rough/archive, cleanup/component and reference paths. Reveal works; optional CSV is saved only when requested.
- [ ] Click the recording name in Perform or Prepare Video to choose another audio. A different recording requires its own usable timing; an incoming unrelated handoff cannot silently switch it.
- [ ] Editor export has no editor-format dropdown. It creates `.xml` and no per-card range markers. Perform chapter flags are retained.
- [ ] Import the XML in Resolve/Premiere and test left/right extension of stills. Check V1 roughs, V2+ cleanups, and empty V1 under cleanup cues.
- [ ] Stereo preserves both original channels without copying the original audio. The editor may show linked channel clips. Mono creates/reuses one mixed WAV and leaves the original unchanged.

## FolderExporter — changes to test

- [ ] Enable Storyboard Studio export, select the same main project folder, and verify automatic Studio Link discovery.
- [ ] Try `work #3`, `work #3A` and `work #3a`; enable lettered matching for A/B suffixes.
- [ ] A configured organizational folder such as `3Chapter` remains a chapter organizer, never Card 3C.
- [ ] A source containing loose frames offers the integration block's chapter choice. It must not silently assign every separate CSP file's first drawing to Card 1.
- [ ] Unresolved drawings open a chapter/card assignment window. Preview the drawing, accept assignments, reopen the CSP source and verify those assignments persist.
- [ ] Switch between different CSP files for the same project: the project-folder connection remains available, while each file retains its own accepted card bindings.
- [ ] Export different cards from separate CSP files. Storyboard Studio reads the combined media catalog and source inventories automatically.
- [ ] Export components with project names. Their names follow the shared component pattern and bottom-to-top stack indices; whole-frame references do not enter the timeline with components.
- [ ] Custom filename slots still work when custom-name mode is selected.
- [ ] Reorder/renumber in Storyboard Studio: saved IDs remain linked. Review the numbering-drift prompt before choosing to rematch source names.
- [ ] Two sources targeting the same card still offer Replace / Keep existing / Cancel. Hidden-folder export and read-only source handling continue working.

## Subtitler — changes to test

- [ ] Select the main project folder. The app searches its root for audio and Studio Link for the shared script/transcript. A missing recording offers manual selection.
- [ ] Matching timing from Storyboard Studio opens/reuses the transcript for the actual recording. It does not select an unrelated transcript merely because its filename or project folder matches.
- [ ] A deliberately selected active recording is passed between the apps. Moving the same recording can preserve its identity through its content fingerprint.
- [ ] Linked automatic `.subtitler` saves are inside Studio Link. Repeated transcription updates the same project instead of creating “new transcription” copies.
- [ ] Explicitly change the recording in Storyboard Studio and match it again. One automatic editable transcript remains current; the previous editable work is preserved in Studio Link/.transcript-archive.
- [ ] Exactly one current `subtitler-audio.timing.json` is published. Obsolete derived handoffs are retired after successful publication. Existing distinct editable transcripts are preserved.
- [ ] Import audio unrelated to the linked project. It starts without that project or script and saves privately rather than into the last selected project folder.
- [ ] The linked project's main-folder path appears at the top; it clears for an unrelated import.
- [ ] File → Recently opened reopens closed work. File → Reveal saved transcript opens its saved location. The native desktop menu and browser fallback route to the same actions.
- [ ] Export includes `.subtitler` and makes an editable copy through the Save dialog, including for a linked project.
- [ ] Delete and Delete all remove the selected editable transcript files and corresponding timing handoffs, with the original audio untouched. Check temporary Undo restoration.
- [ ] Retranscribe the linked Nora test recording. All five paragraphs should be present, rather than beginning at “A black cat…”. Actual recognition still depends on the selected model.
- [ ] The real audio duration must remain authoritative. A bad result extending beyond it is retried or rejected; it must not inflate a 23.58-second recording to 30 seconds.
- [ ] Match timing on an older bad saved transcript: the original audio is prepared again, and obviously out-of-range saved timing triggers retranscription rather than reuse.
- [ ] Check the timing report. Missing/failed alignment keeps existing timing and reports the failure; it does not publish invalid timing over a usable handoff.
- [ ] Silence labels appear at chronological word boundaries. Duplicate/overlapping intervals merge; distinct pauses separated by speech remain distinct.
- [ ] Test spoken integers in English, Portuguese, Spanish and Japanese. Internal alignment readings keep the displayed digits and subtitle division. Ambiguous dates/decimals/unsupported forms retain fallback timing.
- [ ] During playback the active subtitle moves toward the panel center; paused/manual scrolling is preserved.
- [ ] Retest text editing, scissors, split/merge/delete, speakers, light/dark settings, waveform seeking and DOCX/TXT/SRT/CSV/XLSX/JSON exports.

## Verification limits

Automated checks cover core models, actual filesystem modules, real PSD export/composition, cross-app index parsing/XML generation, FFmpeg mono mixing/cache reuse, worker fixtures and browser workflows with native API mocks. They do not substitute for building the complete macOS app or importing into Resolve/Premiere. A real Whisper/WhisperX model was not run here; please use the linked Nora recording for that final regression check.

Deferred: Subtitler video import/burn-in styling, Perform MP4 export, and updating an already edited editor timeline.
