FolderExporter 1.10.0 — Apple Silicon source

Build on your Mac after extracting the source:

  cd "$HOME/Downloads/FolderExporter-v1.10.0"
  bash build_macos.sh

The builder prepares private Python tools, runs export safety tests and creates a DMG in Downloads. No .command launcher is required. Close the older app before opening the new one.

CHANGES
1. Frame labels can include prefixes/suffixes: work #3, work #3A and lowercase work #3a. Lettered matching remains opt-in. Several plausible numbers require a manual match.
2. Chapter/section organizers are classified before card matching. 3Chapter remains an organizer, not Card 3C.
3. The Storyboard Studio block offers a chapter for loose drawings. Unresolved drawings get a chapter/card assignment window with optional previews. Accepted assignments persist.
4. Switching CSP sources retains the connected project folder while each source keeps its own saved bindings. Different sources can contribute different cards.
5. Project names use Storyboard Studio's shared component pattern and bottom-to-top stack indices. Custom filename slots remain available.
6. Existing same-card source conflict prompts, hidden-folder rendering, read-only source handling and one current inventory per source remain intact.

Choose the same main project folder used by Storyboard Studio. Studio Link discovery is automatic; a separate reference import is unnecessary. See WORKFLOW_MANUAL.md for short practical rules and TESTING_CHECKLIST.md for the full coordinated patch checklist.
