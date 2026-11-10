# Studio Link contract: 0.8 / FolderExporter 1.9

Choose one main project root. Storyboard Studio owns project.json, storyboard.ssreference.json, spoken-script.json and storyboard-outputs.json. Subtitler owns its project/timing files. FolderExporter owns one inventory per CSP/PSD source. All apps share the active media-index.json catalog keyed by permanent [sourceCardId, variantIndex].

Card IDs, display labels, export labels and playback order are distinct. Reference cards keep unique numeric ordinal fields for older readers and add frameLabel/globalFrameLabel/displayLabel, exportNumber/globalExportNumber and slightModifyIndex. Source IDs and variant snapshots never derive from a filename.

Media inside the root uses forward-slash relativePath. Its saved absolute path is a fallback, possibly from another OS. External/manual media keeps its original location and is not renamed automatically. Native validation accepts foreign absolute references while filesystem access still resolves on the current machine.

Active cleanup entries use files in back-to-front order. FolderExporter publishes components when present and retains the flattened reference under referenceFiles. managed=true and componentSuffix identify outputs eligible for coordinated renaming. Manual attachments are not managed. removed=true is a tombstone; retained retired-file metadata is not an active cleanup connection.

Naming includes chapter/card/archiveFolder/archiveCard/sheet/timeline, padding, and {slight_modify_index}. The display letter toggle does not change permanent identities. Archive paths and managed names update in batches before exports/handoffs and at close; ordinary local project autosave remains independent. No 650ms shared-file writer is used.

A cross-app .workflow.lock serializes writes. Move batches stage all sources before installing destinations and use organization-journal.json to recover interruption. Missing/shadowed rough records cannot move an active replacement cleanup. Only registry-owned outputs can be replaced or retired, with unrelated files protected. Keep both is explicit and retains a tracked version suffix. Deleted source exports retire into the configured archive with their deleted ID.

Managed path changes update the global catalog, output registry, manifest and relevant inventory paths. Inventories also refresh descriptive labels from the current reference while retaining original source structure, export dates and variant snapshots. pathRevision tells readers to refresh path/label caches without treating the inventory as a new cleanup export. A fresh export still receives a new exportId and timestamp. Timing text and word intervals are not rewritten by Storyboard Studio.

FolderExporter retains known source-frame/card bindings; changed numbering can require confirming whether to keep those IDs or rematch names. Conflicting active cleanup ownership is reviewed before files are written. Each card has one active cleanup representation.

Timeline exports reference existing media, original full audio and current script-linked timing. V1 is rough-only; V2+ is cleanup. Cleanup transparency never reveals a rough beneath it. Existing edited NLE timelines do not read Studio Link and can require relinking after managed renames.
