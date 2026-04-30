# FusionDocumentationToolkit

![Version 0.2](https://img.shields.io/badge/version-0.2-blue)

A Fusion 360 add-in that streamlines documentation and assembly-manual creation: configurable visual-style presets (with the Voron Design Team's preset bundled), hotkey-friendly viewport image capture with auto-numbering and DPI metadata, and a dedicated **DOCUMENTATION** toolbar panel.

## Why?

Producing assembly manuals or technical documentation in Fusion 360 means juggling visual-style settings and capturing dozens of screenshots per session. This toolkit collapses both into single-click commands. The bundled Voron preset is the canonical example of what a "manual mode" looks like; you can edit `config.json` to add or replace presets for any other documentation style.

The Voron Design Team uses a specific set of visual settings — Photobooth environment, wireframe with visible edges only, orthographic camera, ambient occlusion on, ground plane/shadow/reflection off, specific Preferences panel tweaks — for authoring their assembly manuals. Configuring all of that by hand every time you want to take a screenshot is tedious. This add-in flips all of those settings on and off with a single button, and lets you fire silent, auto-numbered captures from a hotkey of your choice.

## Installation

**macOS:**
```
cd ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/
git clone https://github.com/erikbuild/FusionDocumentationToolkit.git FusionDocumentationToolkit
```

**Windows:**
Download or clone this repository, then copy the `FusionDocumentationToolkit` folder to your Fusion 360 add-ins directory:
```
%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns\
```

Then in Fusion 360:

1. Go to **UTILITIES > ADD-INS** (or press **Shift+S**)
2. Select the **Add-Ins** tab
3. Find **FusionDocumentationToolkit** in the list and click **Run**

A **"Voron-style Mode Switch"** button (and the **Capture Image** / **Configure Capture** buttons) will appear in your configured toolbar panel — by default a custom panel named **DOCUMENTATION** in the Solid workspace.

## Usage

Click the **Voron-style Mode Switch** button to flip between presets. The first click switches to the Voron preset; the next click switches back to the default preset.

## Image Capture

Two additional commands streamline the screenshotting workflow that goes hand-in-hand with the Voron preset:

- **Capture Image** — Saves the active viewport to an image file with the current session settings. The first press of each Fusion session prompts for an output folder; subsequent presses save silently with auto-incrementing names (`capture_001.png`, `capture_002.png`, …). Each save is logged to the Text Commands palette so you can confirm without a popup.
- **Configure Capture** — Opens a dialog where you can change the folder, dimensions, format (PNG/JPG), transparent background, and anti-aliasing for the rest of the session. Defaults come from `config.json` and reset on every Fusion launch.

### Assigning a hotkey

Fusion's API has no programmatic hotkey registration, so you assign one manually — one time per machine:

1. Find the **Capture Image** button on the panel where the add-in's buttons live (default: `DOCUMENTATION`).
2. Right-click the button → **Change Keyboard Shortcut**.
3. Enter the key combination (e.g. `F12`).

Repeat for **Configure Capture** if you want a separate shortcut for the settings dialog.

### Notes and caveats

- **Transparent background disables shadows** — documented Fusion behavior, not a bug.
- **No active document, no capture** — if no design is open, Capture Image shows a friendly error.
- **Filename collisions** — if the chosen folder already contains `capture_NNN.png` files, the counter starts past the highest existing number; nothing is overwritten.
- **Format support** — only PNG and JPG are exposed.

## Voron Team Recommended Settings

These are the target settings the `voron` preset applies.

- **Environment:** Photobooth
- **Visual Style:** Wireframe with Visible Edges Only
- **Effects:**
  - Ambient Occlusion: enabled
  - Anti-aliasing: enabled
  - Environment Dome: disabled
  - Ground Plane: disabled
  - Ground Shadow: disabled
  - Ground Reflection: disabled
  - Object Shadow: disabled
- **Camera:** Orthographic
- **Layout Grid:** disabled
- **Preferences:**
  - Selection Display Style: Normal
  - Degraded Selection Display Style: Normal
  - Transparency Effect: Better Display
  - Hidden Edge Dimming: 0% *(set this once manually — not scriptable, see note above)*

## Configuration

The add-in reads settings from `config.json` in the add-in directory. If the file is missing, defaults are used.

### Top-level keys

| Setting | Default | Description |
|---|---|---|
| `use_custom_panel` | `false` | When `true`, creates a dedicated toolbar panel in the Solid tab (see below). When `false`, the button lands in the built-in Inspect panel. |
| `panel_id` | `"Documentation_Panel"` | Internal ID for the custom panel. |
| `panel_name` | `"DOCUMENTATION"` | Display name shown in the toolbar for the custom panel. |
| `debug` | `false` | When `true`, shows a report popup after each toggle. |
| `start_mode` | `"default"` | Which preset the add-in assumes is active at startup. Must be `"voron"` or `"default"`. |
| `capture` | *(see file)* | Per-session image capture defaults — see **Capture defaults** below. |
| `presets.voron` | *(see file)* | Voron Manual Mode preset — `{label, tooltip, commands}`. |
| `presets.default` | *(see file)* | Default mode preset — `{label, tooltip, commands}`. |

### Preset `commands` entries

Each entry has a `label` plus **either** a `cmd` or a `visual_style` key:

- `label` — human-readable string shown in the debug report.
- `cmd` — a text command string passed to `app.executeTextCommand()`. Used for most settings.
- `visual_style` — a value name from the `adsk.core.VisualStyles` enum (e.g. `"WireframeWithVisibleEdgesOnlyVisualStyle"`). Used because visual style is the one setting that has a verified direct-API path and no reliable text command equivalent. When present, the dispatcher sets `app.activeViewport.visualStyle` directly and ignores `cmd`.
- `tentative` *(optional)* — metadata flag indicating the `cmd` string is an unverified best guess. Ignored at runtime; used by humans to know which entries to test first.

### Tweaking the `default` preset

The shipped `default` preset mirrors Fusion's out-of-box defaults (Photobooth environment, Shaded with Visible Edges Only, etc.) so toggling back feels like "reset to Fusion defaults." If you prefer a darker viewport, swap the Photobooth entry for Grey Room:

```json
{"label": "Environment: Grey Room", "cmd": "NuCommands.ViewEnvironmentCmd ViewEnvGreyRoomCommand"}
```

Grey Room is a neutral dark-grey HDRI — a common pick for a "dark mode"-ish working environment.



### Using a custom toolbar panel

By default, the add-in drops its button into Fusion's built-in **Inspect** panel on the Solid tab. If you run several add-ins and would rather group them into your own panel, set `use_custom_panel` to `true`:

```json
{
    "use_custom_panel": true,
    "panel_id": "Documentation_Panel",
    "panel_name": "DOCUMENTATION"
}
```

- `panel_id` — internal identifier. Pick anything unique; Fusion uses it to look the panel up across sessions. Share the same ID across your add-ins and they'll all land in the same panel.
- `panel_name` — display label shown on the toolbar.

The custom panel is created on first run and removed when the last button is unregistered (i.e. when you stop every add-in that uses it).

### Capture defaults

The `capture` block seeds the initial values that **Capture Image** and **Configure Capture** use. Changes made via the Configure dialog apply only to the current Fusion session — restart Fusion or stop/start the add-in to revert to these baseline values.

| Key | Default | Description |
|---|---|---|
| `default_width` | `1920` | Initial image width in pixels (Fusion clamps to 108–4000). |
| `default_height` | `1080` | Initial image height in pixels. |
| `default_format` | `"png"` | `"png"` or `"jpg"`. |
| `default_transparent` | `false` | When `true`, captures with a transparent background (and no shadows). |
| `default_antialias` | `true` | When `true`, anti-aliases the rendered image. |
| `default_dpi` | `300` | Resolution metadata written to the file (PNG `pHYs` chunk / JPG JFIF density). Pixel dimensions are unchanged — this only affects how apps like InDesign or Photoshop size the placed image for print. |
| `filename_prefix` | `"capture"` | First component of generated filenames, e.g. `capture_001.png`. |

There is no `default_folder` key — the add-in always prompts for the output folder on the first capture of each session.

### Debug mode

Set `"debug": true` in `config.json` to get a post-toggle popup report listing which commands applied and which failed (with the error text). Useful while verifying `"tentative": true` entries; the shipped config has it off.

### Unsupported setting

**Hidden Edge Dimming %** — no text command exists for this; it's a pure Preferences dialog setting. **Set it to 0% once in Fusion's Preferences dialog and leave it.** It does not flip when you toggle the add-in.

## Project Structure

```
FusionDocumentationToolkit/
├── erikbuild-FusionDocumentationToolkit.py        # Add-in source code
├── erikbuild-FusionDocumentationToolkit.manifest  # Fusion 360 manifest
├── config.json                               # Panel placement + preset commands
├── resources/
│   ├── 16x16-normal.png
│   ├── 32x32-normal.png
│   └── 64x64.png
├── plans/                                    # Implementation plans for completed/upcoming work
├── reference/
│   ├── README.md                             # How to use the command dump
│   └── fusion_textcommands_8176.txt          # Full dump of ~2600 Fusion text commands
├── CLAUDE.md                                 # Architecture notes
├── TEXT_COMMAND_DISCOVERY.md                 # Verification workflow for tentative strings
├── LICENSE
└── README.md
```

## License

[MIT + Commons Clause](LICENSE)

## Made By

@erikbuild
