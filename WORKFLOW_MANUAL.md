# Studio workflow rules

1. **Choose the same main project folder in all three apps.** Select its parent, such as Desktop/My Video. The apps find its Studio Link folder themselves. Keep the original `.StoryboardStudio` project wherever you prefer.

2. **Keep the finished recording directly inside that main folder.** One combined recording is the normal workflow. Match timing with Subtitler reuses a matching transcript; if no audio is found, choose it manually. Click the recording name in Perform or Prepare Video to change it deliberately.

3. **A new unrelated Subtitler import starts independently.** Its automatic `.subtitler` save is kept in the app's private storage, without inheriting the last project or script. File → Recently opened and Reveal saved transcript provide access. Explicitly linked transcripts save inside Studio Link. Export → `.subtitler` makes a portable editable copy.

4. **Organize CSP however the drawings require.** One file per chapter is NOT required. Complex backgrounds, individual drawings and animations can stay in separate CSP files. Different files can export different cards into the same project. If two sources target the same card, FolderExporter asks whether to replace or keep the existing cleanup.

5. **Use chapter organizers and one clear card label per frame folder.** With configured chapter/section keywords, those folders remain organizers, not cards. `3Chapter` can identify Chapter 3; it is not Card 3C. `Frame 8`, `work #8` and, with lettered matching enabled, `work #8a` are supported. Several plausible numbers require a manual assignment.

6. **For loose drawings, choose their chapter in FolderExporter.** The Storyboard Studio block has a chapter choice for drawings outside chapter organizers. Unmatched drawings get a chapter/card window with optional previews. Accepted assignments are remembered. Existing saved links take priority until you deliberately change them.

7. **Keep established CSP connections when Storyboard Studio reorders cards.** Permanent IDs identify the artwork; display numbers and playback position can change. Do not blindly rename all CSP frame folders after a reorder. FolderExporter warns about numbering drift and lets you retain the saved connection or deliberately rematch the names.

8. **Use Slight modify for independent artwork.** Optional letter display gives 3, 3A, 3B, 4. Moving 3A does not change its family. Deleting 3A leaves 3B as 3B. New modifications are created from regular cards; Make regular card removes the letter relationship. Existing nested modifications retain their original family. Reusable copies share artwork and block deleting their source until those copies are removed. Independent modifications survive source deletion with a historical reminder.

9. **Export rough cards with Storyboard Studio.** Cmd/Ctrl+S saves the project, shared records and changed/missing rough PNGs. Closing also saves; wait for Saving to finish. A card with a cleanup keeps its rough export in the configured storyboard archive. New normal or lettered cards export alongside the existing cleanups without replacing them.

10. **Direct cleanup files can stay at their chosen locations.** Drag them onto the intended card in Clean up, or use Attach cleanup. These are links, not copies. Arbitrary attached files keep their original names. Delete in Clean up removes the cleanup association; it does not delete the original media. Refresh does not reattach an unchanged file you explicitly disconnected. Attach it again, or replace/export it again, to reconnect it. Storyboard deletion removes the card and its associations.

11. **Automatic folder discovery requires the complete shared naming pattern and an existing card.** Put correctly named media in that card's registered chapter folder. An unrelated file such as `texture.png` is ignored. When you replace a tracked rough at the same location, Storyboard Studio accepts the replacement as cleanup and recreates the original rough in its archive. Use existing file as cleanup is a fallback when automatic identification is ambiguous. An extension is the final part of a filename, such as `.png`, `.jpg` or `.mov`.

12. **Manual components need the shared component pattern.** Configure it in Storyboard Studio's File naming. For example, with card name `8_2.Test`, `{card_name}_component-{component_index}` gives `8_2.Test_component-1.png` and `8_2.Test_component-2.png`. Component 1 is at the bottom. `{component_name}` can be included too. FolderExporter uses this same pattern in project-name mode; its custom filename slots remain available.

13. **Check stacking in Clean up when attaching several files.** The top organizer row is in front. Only components enter the timeline when a whole frame and components exist; the whole frame remains a reference on disk. Missing one component does not hide or disconnect the others.

14. **Save before switching apps after reorganizing.** Managed cleanup/component names, rough archives and Studio Link records update together on save/export/close. Custom external attachments retain their names. Collisions stop the transaction rather than overwrite another drawing. File copies are given time to settle before discovery; Refresh is available if needed.

15. **Use Media locations to trace every file.** Prepare Video lists each card's rough/archive path, cleanup components and whole-frame references, with Reveal and optional CSV export. No extra CSV is created automatically.

16. **Relink moved media rather than changing card identity.** The red broken-link button searches a chosen folder and its subfolders. Unique matches reconnect; ambiguous matches need choosing. To move between Mac and Windows, copy the whole project folder and reselect it in each app. External media must also be copied and reattached or found with the missing-file search.

17. **Export one XML assembly for Premiere or Resolve.** V1 is reserved for rough storyboards; V2 and above hold cleanups. A cleanup cue leaves V1 empty so roughs do not show through transparency. Components are independent unless Link stacked components is enabled. Exported cue range markers have been removed; Perform chapter flags remain.

18. **Choose Stereo or Mono deliberately.** Stereo references the original recording and preserves both channels; an editor may display linked left/right clips. Mono averages both channels into one reusable WAV in Studio Link's Media cache. The original audio is never replaced.

19. **A new XML import is a new assembly.** It does not update an already edited timeline or inherit its edits. Renaming/moving media can require relinking an existing editor project. You can import a fresh assembly and copy clips into your main timeline. Still-image left extension must be checked in the receiving editor; the selected XML route is the one Filipe already verified.

20. **Keep recognition and silence distinct.** Subtitler's silence labels represent intervals in the recording, not spoken words. Numbers can use internal spoken forms during alignment while their displayed text stays unchanged. Bad or out-of-range recognition must not replace the last usable shared timing. Review the timing report and retranscribe the affected recording if necessary.

Deferred: importing video into Subtitler to burn in styled subtitles; MP4 export from Perform; updating an existing edited editor timeline. These are not part of this patch. Native macOS builds, real Whisper model recognition and Resolve/Premiere imports still require testing on the target computer.
