# Rename: VoronStyleManualMode → FusionDocumentationToolkit

## Context

The project's scope has outgrown its original name. It started as a single-purpose
viewport toggle for Voron Design Team's assembly-manual visual style. It now also
includes a hotkey-friendly image capture command, a configuration dialog with DPI
metadata embedding, a custom DOCUMENTATION toolbar panel, and the renamed
"Voron-style Mode Switch" button. Voron is no longer the project's identity — it's
just one bundled preset configuration that any Fusion 360 user creating documentation
or assembly manuals can use or replace.

The new name **FusionDocumentationToolkit** describes what the project actually is:
a toolkit for creating documentation in Autodesk Fusion 360. The Voron preset
becomes the canonical example, not the framing.

## Approach

A pure metadata/identity change. No feature code is altered. We rename the folder
and its two filename-mirroring files, update the manifest's `id`/`description`/`version`,
update LICENSE and README references, and refresh the file-header ABOUTME comments.
**Internal CMD_IDs are deliberately preserved** so any keyboard shortcuts the user has
already assigned via Fusion's right-click → Change Keyboard Shortcut continue to work.

### Filesystem renames

Use `git mv` so history follows the files.

| Old | New |
|---|---|
| `VoronStyleManualMode/` | `FusionDocumentationToolkit/` |
| `erikbuild-VoronStyleManualMode.py` | `erikbuild-FusionDocumentationToolkit.py` |
| `erikbuild-VoronStyleManualMode.manifest` | `erikbuild-FusionDocumentationToolkit.manifest` |

Fusion convention: the folder and the two basename-paired files must share a name.
The `erikbuild-` prefix stays — it's the author/namespace prefix Erik uses across his
add-ins.

### Manifest content changes (`*.manifest`)

```json
{
    "autodeskProduct": "Fusion",
    "type": "addin",
    "id": "FusionDocumentationToolkit",
    "author": "Erik Reynolds (erikbuild)",
    "description": {
        "en-US": "Toolkit for creating Fusion 360 documentation: configurable visual-style presets (Voron-style preset bundled), hotkey-friendly viewport image capture with DPI metadata, and a dedicated DOCUMENTATION toolbar panel."
    },
    "version": "0.2.0",
    "runOnStartup": true,
    "supportedOS": "windows|mac"
}
```

Three changes from current: `id`, `description.en-US`, and `version` (0.1.0 → 0.2.0
since rename + capture features represent a meaningful change).

### Python file changes (`*.py`)

Only the two `# ABOUTME:` header lines change. Update them to:

```python
# ABOUTME: Fusion 360 documentation toolkit — configurable visual-style presets
# ABOUTME: and hotkey-friendly viewport image capture with DPI metadata.
```

**Not changed**: `CMD_ID = 'VoronStyleManualModeCmd'`, `CAPTURE_CMD_ID`,
`CONFIGURE_CAPTURE_CMD_ID`. These are stable internal identifiers that Fusion uses
to look up commands across sessions and to associate user-assigned keyboard shortcuts.
Renaming them would orphan any existing shortcut bindings.

### LICENSE

Update line 40: `Software: VoronStyleManualMode` → `Software: FusionDocumentationToolkit`.
Nothing else changes (MIT + Commons Clause text is unchanged).

### README

Targeted updates, not a full rewrite:

- **Title** (line 1): `# VoronStyleManualMode` → `# FusionDocumentationToolkit`
- **Lead paragraph** (line 5): rewrite to position as a documentation toolkit with the
  Voron preset as the bundled example. Roughly:

  > A Fusion 360 add-in that streamlines documentation and assembly-manual creation:
  > configurable visual-style presets (with the Voron Design Team's preset bundled),
  > hotkey-friendly viewport image capture with auto-numbering and DPI metadata, and
  > a dedicated **DOCUMENTATION** toolbar panel.

- **Installation** section: `git clone https://github.com/erikbuild/VoronStyleManualMode.git VoronStyleManualMode`
  → `... FusionDocumentationToolkit.git FusionDocumentationToolkit`. Same for the
  Windows path reference to `erikbuild-VoronStyleManualMode`.
- **Project Structure** block: rename folder and the two file basenames in the tree.
- **"Why?" section**: keep the existing Voron rationale but add a one-line lead-in
  framing it as the bundled example use case.

Other sections (Image Capture, Voron Team Recommended Settings, Configuration table,
Capture defaults, Custom panel, Debug mode, Unsupported setting) are unaffected — they
reference features and config keys, not the project name.

### Files that don't change

- `config.json` — no project-name strings.
- `plans/` — historical record, leave as-is.
- `reference/` — Fusion text-command dump, untouched.
- `resources/` — icon PNGs, untouched.
- `.vscode/` — untracked, ignore.

### Fusion re-registration (one-time, after rename)

Fusion's Scripts and Add-Ins registry stores the add-in by its old folder path. After
the rename, Erik must:

1. Open **Utilities → Add-Ins** (Shift+S).
2. Find the old `VoronStyleManualMode` entry — likely shown red/missing now.
3. Stop it (if still running) and click **Remove from list**.
4. Click **+** and point at the new `FusionDocumentationToolkit/` folder.
5. Run.

Because manifest `id` changed (`VoronStyleManualMode` → `FusionDocumentationToolkit`),
Fusion treats this as a new add-in. CMD_IDs are unchanged, so any keyboard shortcuts
previously assigned via right-click should still bind. If Fusion doesn't pick them up,
re-assign once.

## Files to modify

| File | Change |
|---|---|
| `VoronStyleManualMode/` (folder) | `git mv` to `FusionDocumentationToolkit/` |
| `erikbuild-VoronStyleManualMode.py` | `git mv` to `erikbuild-FusionDocumentationToolkit.py`; update ABOUTME header (2 lines) |
| `erikbuild-VoronStyleManualMode.manifest` | `git mv` to `erikbuild-FusionDocumentationToolkit.manifest`; update `id`, `description.en-US`, `version` |
| `LICENSE` | Update line 40 (`Software: ...`) |
| `README.md` | Update title, lead paragraph, installation, project-structure tree |

## Verification

1. `python3 -m py_compile FusionDocumentationToolkit/erikbuild-FusionDocumentationToolkit.py` — syntax OK.
2. `python3 -c "import json; json.load(open('FusionDocumentationToolkit/erikbuild-FusionDocumentationToolkit.manifest'))"` — manifest is valid JSON.
3. `python3 -c "import json; json.load(open('FusionDocumentationToolkit/config.json'))"` — config still parses.
4. `git log --follow FusionDocumentationToolkit/erikbuild-FusionDocumentationToolkit.py` — confirms history is preserved through the rename.
5. `grep -rn "VoronStyleManualMode" FusionDocumentationToolkit/` — should return only legitimate stragglers (none expected outside `plans/` and `reference/`); zero matches in source/manifest/README/LICENSE.
6. In Fusion: remove the old add-in entry, add the renamed folder, run. Verify all three buttons appear on the **DOCUMENTATION** panel.
7. Click **Voron-style Mode Switch** — preset toggle works.
8. Click **Capture Image** — folder prompt → save → log line in Text Commands palette.
9. Click **Configure Capture** — dialog opens with current session settings.
10. If a hotkey was previously bound to Capture Image, verify it still triggers. If not, re-bind via right-click.

## Out of scope (deferred / not changing)

- Renaming `CMD_ID` constants in the Python file (would orphan Fusion's stored shortcut bindings).
- Renaming the GitHub repo URL (Erik's call; if done, the README's `git clone` line should match).
- Restructuring the README beyond the four targeted updates above.
- Splitting the bundled Voron preset into a separate "preset library" (possible future work, not now).
- Renaming `presets.voron.label` in `config.json` (used in debug popups; preset is still called "Voron Manual Mode" as a config concept).
