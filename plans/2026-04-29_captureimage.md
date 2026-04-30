# Capture Image Workflow

## Context

Fusion 360's built-in Capture Image dialog is fine but slow: every screenshot requires
opening a modal, choosing a path, picking dimensions, clicking save. For Voron assembly
manual work — where dozens of screenshots are taken per session, all with the same
settings into the same folder — this is high-friction.

We want a hotkey-driven, silent capture command that:

- Prompts for an output folder once per Fusion session (no config default — Erik's choice).
- Subsequent presses save immediately, with auto-incrementing filenames, no dialog.
- Logs each save path to Fusion's Text Commands palette so feedback is visible without a popup.
- A separate Configure command exposes folder / width / height / format / transparent /
  anti-alias settings via a CommandInputs dialog and updates the session state.

The Capture command will live in this add-in (alongside the Voron toggle) on the
existing `ERIKBUILD` panel. The user assigns the hotkey manually once via Fusion's
"Change Keyboard Shortcut" right-click menu — Fusion's API has no programmatic hotkey
registration.

## Approach

### Architecture summary

Two new commands registered in `run()` next to the existing `VoronStyleManualModeCmd`:

| Command ID            | Behavior                                                                 |
|-----------------------|--------------------------------------------------------------------------|
| `CaptureImageCmd`     | Silent. Press → if no session folder, prompt; then save + log.           |
| `ConfigureCaptureCmd` | Opens CommandInputs dialog. Updates session state. No persistence to disk in v1. |

Both buttons go on the same `ERIKBUILD` panel as the existing toggle.

### Silent-capture pattern

Standard Fusion command flow shows a tiny floating panel with an OK button even when a
command has no inputs. For a hotkey-driven silent capture this is one extra click too many.

**Initial attempt (rejected — crashed Fusion):** doing the work directly inside
`commandCreated.notify()` and calling `args.command.doExecute(True)` to terminate without
firing execute. The crash trace pointed at `Xl::APICommandDefinitionImpl::doOnCreateCommand`,
i.e. Fusion segfaulted while still mid-create-command — it is unsafe to run modal native
dialogs (`createFolderDialog`) or viewport saves (`saveAsImageFileWithOptions`) from inside
the create-command lifecycle.

**Corrected pattern:** standard `commandCreated → execute` split, plus a best-effort
`cmd.isAutoExecute = True` to skip the empty OK dialog when Fusion supports it. If
`isAutoExecute` doesn't exist on the user's Fusion build, the worst case degrades to a
brief empty OK dialog — never a crash.

```python
class CaptureCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        cmd = args.command
        try:
            cmd.isAutoExecute = True   # skip the empty OK dialog where supported
        except AttributeError:
            pass
        cmd.isExecutedWhenPreEmpted = False
        on_execute = CaptureExecuteHandler()
        cmd.execute.add(on_execute)
        _handlers.append(on_execute)


class CaptureExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        capture_image()                    # folder prompt + save + logging
```

The Configure command uses the same standard `CommandCreated → inputs → Execute` pattern
since it needs a dialog regardless.

### Per-session state

New module-level globals, mirroring the existing `_current_mode` pattern in
`erikbuild-VoronStyleManualMode.py:16`:

```python
_capture_folder    = None     # str | None — set on first capture or via Configure
_capture_width     = 1920
_capture_height    = 1080
_capture_format    = 'png'    # 'png' | 'jpg'
_capture_transparent = False
_capture_antialias = True
_capture_counter   = 0        # bumped per save; collision-checked against folder
```

Defaults are read from a new `capture` section in `config.json` (see below) inside the
existing `load_config()` flow at `erikbuild-VoronStyleManualMode.py:32`. State resets to
config defaults on each Fusion launch — no write-back in v1.

### First-capture folder prompt

`capture_image()` checks `_capture_folder`. If `None`, it calls
`_ui.createFolderDialog()`, stores the result, scans the folder for existing
`{prefix}_NNN.{ext}` files to seed `_capture_counter`, then proceeds with the save. If the
user cancels the folder picker, the capture is aborted with a log line — no error popup.

### Auto-incrementing filenames

```
{folder}/{prefix}_001.{ext}
{folder}/{prefix}_002.{ext}
...
```

`prefix` defaults to `"capture"` (configurable). Before each save, `next_capture_path()`
increments the counter and bumps further if the file already exists on disk — this
handles the case where the user picks a folder that already contains captures.

### Saving the image

Uses the modern `Viewport.saveAsImageFileWithOptions()` API (Fusion May 2022+) for full
control:

```python
options = adsk.core.SaveImageFileOptions.create()
options.filename = path
options.width    = _capture_width
options.height   = _capture_height
options.isBackgroundTransparent = _capture_transparent
options.isAntiAliased           = _capture_antialias
ok = _app.activeViewport.saveAsImageFileWithOptions(options)
```

### Logging to Text Commands palette

`adsk.core.Application.log(message)` writes to the Text Commands palette (the same panel
where Erik already discovers commands for the preset engine — see `reference/README.md`).
We log on every meaningful event:

```
[CaptureImage] Session folder set: /Users/erik/Desktop/FusionCaptures
[CaptureImage] Saved: /Users/erik/Desktop/FusionCaptures/capture_001.png  (1920x1080, png)
[CaptureImage] Save failed: <reason>
[CaptureImage] Settings updated: 2560x1440 png transparent=False aa=True
```

### Configure dialog inputs

Built in `ConfigureCaptureCreatedHandler.notify()`:

| Input                          | Type                              | Notes                                     |
|--------------------------------|-----------------------------------|-------------------------------------------|
| `folder` (read-only display)   | `StringValueCommandInput`         | Shows current session folder              |
| `pickFolder`                   | `BoolValueCommandInput` (button)  | Click → `createFolderDialog()`, updates display |
| `width`                        | `IntegerSpinnerCommandInput`      | range 108–4000, step 10                   |
| `height`                       | `IntegerSpinnerCommandInput`      | range 108–4000, step 10                   |
| `format`                       | `DropDownCommandInput`            | PNG / JPG                                 |
| `transparent`                  | `BoolValueCommandInput`           | Note: disables shadows when on            |
| `antialias`                    | `BoolValueCommandInput`           |                                           |

Note on folder picker: Fusion's CommandInputs has no native folder-picker widget. The
common workaround is a `BoolValueCommandInput` styled as a button — when toggled, an
`InputChangedHandler` calls `_ui.createFolderDialog()` and writes the result back into
the read-only string input. This is well-trodden territory.

The Execute handler reads all values and updates the module globals. No config.json
write-back in v1 (Erik can edit config.json directly between sessions if defaults need
to change — matches existing add-in convention which never writes config).

### Hotkey

Documented in README, not code. After install:

1. Open Fusion.
2. Find the **Capture Image** button on the `ERIKBUILD` panel.
3. Right-click → **Change Keyboard Shortcut** → assign desired key (e.g. `F12`).

Same flow for Configure if Erik wants a separate hotkey for it.

## Files to modify

| File | Change |
|------|--------|
| `erikbuild-VoronStyleManualMode.py` | Add constants, module globals, helpers, 4 handler classes; extend `run()`/`stop()` to register/teardown both new commands. ~150 new lines, no changes to existing toggle logic. |
| `config.json` | Add `capture` section (see below). |
| `erikbuild-VoronStyleManualMode.manifest` | **Flag for Erik** — current description (line 7) says "Toggle Fusion 360 between the Voron Design Team assembly manual visual preset and Fusion defaults." If we keep the manifest scope-locked to Voron, we should broaden it ("Voron-style visual presets and image-capture utilities."). Optional, no functional impact. |

### `config.json` additions

```json
"capture": {
    "default_width": 1920,
    "default_height": 1080,
    "default_format": "png",
    "default_transparent": false,
    "default_antialias": true,
    "filename_prefix": "capture"
}
```

No `default_folder` key — Erik chose always-prompt-on-first-capture.

## Patterns reused from existing code

- `load_config()` at `erikbuild-VoronStyleManualMode.py:32` — extended to read new section, no behavior change for callers.
- Module-level globals + `global` declarations — same idiom as `_current_mode` (line 16).
- `CommandCreatedHandler` / `ExecuteHandler` class pattern (lines 216–245).
- Panel resolution chain in `run()` (lines 166–184) — both new buttons are added to the same resolved panel.
- Cleanup pattern in `stop()` (lines 191–213) — both new commands removed alongside the existing one.
- Try/except + `_ui.messageBox(traceback.format_exc())` for fatal errors; `_app.log()` for normal status.

## New helper functions in `erikbuild-VoronStyleManualMode.py`

```python
def init_capture_defaults():
    # Read 'capture' section from _config, populate _capture_* globals.

def prompt_for_capture_folder() -> str | None:
    # Wraps _ui.createFolderDialog(). Returns folder path or None on cancel.

def seed_capture_counter(folder: str, prefix: str, ext: str):
    # Scan folder for {prefix}_NNN.{ext}, set _capture_counter to max found.

def next_capture_path() -> str:
    # Increments _capture_counter, returns full path, bumps past collisions.

def capture_image():
    # Top-level orchestration: ensure folder → build path → save → log.

def log(msg: str):
    # Wrapper around _app.log('[CaptureImage] ' + msg).
```

## Verification

End-to-end check after implementation:

1. **Reload add-in.** Scripts and Add-Ins dialog → stop → start. No errors.
2. **First capture from button.** Click `Capture Image` → folder picker appears → choose
   `~/Desktop/FusionCaptures` → file saved as `capture_001.png` → Text Commands palette
   shows `[CaptureImage] Saved: ...`.
3. **Second capture, silent.** Click again → file `capture_002.png` saved with no dialog
   → log line.
4. **Configure dialog.** Click `Configure Capture` → dialog opens with current values →
   change width to 2560, format to JPG → OK → log shows updated settings.
5. **Capture after Configure.** Click `Capture Image` → `capture_003.jpg` at 2560×heightPreserved.
6. **Hotkey.** Right-click `Capture Image` button → Change Keyboard Shortcut → assign F12
   → press F12 → silent capture, no UI flash, log line appears.
7. **Edge cases.**
   - Folder picker cancelled on first press → log line "Capture cancelled (no folder)", no popup, no file.
   - No active document → `messageBox` with friendly error, no traceback.
   - Pre-existing files in target folder (`capture_001.png` already there) → counter
     starts at 2, no overwrite.
8. **Pristine logs.** No tracebacks during normal flow; popups only on real errors.
9. **Add-in stop.** Disable add-in → both buttons removed from `ERIKBUILD` panel; Voron
   toggle still functions on re-enable.

## Out of scope (deferred)

- Persisting Configure changes back to `config.json` (Erik can hand-edit between sessions).
- Multi-viewport capture.
- DPI / metadata / EXIF.
- Auto-creating subfolders per timestamp.
- Renaming the add-in / broadening the manifest beyond optional description tweak.
