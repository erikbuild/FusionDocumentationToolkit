# VoronStyleManualMode

![Version 0.1](https://img.shields.io/badge/version-0.1-blue)

A Fusion 360 add-in that toggles the viewport between the Voron Design Team's recommended assembly manual visual preset and a user-configurable default preset, with one click from the toolbar.

## Why?

The Voron Design Team uses a specific set of visual settings — Photobooth environment, wireframe with visible edges only, orthographic camera, ambient occlusion on, ground plane/shadow/reflection off, specific Preferences panel tweaks — for authoring their assembly manuals. Configuring all of that by hand every time you want to take a screenshot is tedious. This add-in flips all of those settings on and off with a single button.

## Installation

**macOS:**
```
cd ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/
git clone https://github.com/erikbuild/VoronStyleManualMode.git VoronStyleManualMode
```

**Windows:**
Download or clone this repository, then copy the `erikbuild-VoronStyleManualMode` folder to your Fusion 360 add-ins directory:
```
%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns\
```

Then in Fusion 360:

1. Go to **UTILITIES > ADD-INS** (or press **Shift+S**)
2. Select the **Add-Ins** tab
3. Find **VoronStyleManualMode** in the list and click **Run**

A **"Voron Manual Mode"** button will appear in your configured toolbar panel (by default: Solid Workspace --> Inspect Panel).

## Usage

Click the **Voron Manual Mode** button to flip between presets. The first click switches to the Voron preset; the next click switches back to the default preset.

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
| `panel_id` | `"CustomPlugins_Panel"` | Internal ID for the custom panel. |
| `panel_name` | `"ERIKBUILD"` | Display name shown in the toolbar for the custom panel. |
| `debug` | `false` | When `true`, shows a report popup after each toggle. |
| `start_mode` | `"default"` | Which preset the add-in assumes is active at startup. Must be `"voron"` or `"default"`. |
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
    "panel_id": "CustomPlugins_Panel",
    "panel_name": "ERIKBUILD"
}
```

- `panel_id` — internal identifier. Pick anything unique; Fusion uses it to look the panel up across sessions. Share the same ID across your add-ins and they'll all land in the same panel.
- `panel_name` — display label shown on the toolbar.

The custom panel is created on first run and removed when the last button is unregistered (i.e. when you stop every add-in that uses it).

### Debug mode

Set `"debug": true` in `config.json` to get a post-toggle popup report listing which commands applied and which failed (with the error text). Useful while verifying `"tentative": true` entries; the shipped config has it off.

### Unsupported setting

**Hidden Edge Dimming %** — no text command exists for this; it's a pure Preferences dialog setting. **Set it to 0% once in Fusion's Preferences dialog and leave it.** It does not flip when you toggle the add-in.

## Project Structure

```
erikbuild-VoronStyleManualMode/
├── erikbuild-VoronStyleManualMode.py        # Add-in source code
├── erikbuild-VoronStyleManualMode.manifest  # Fusion 360 manifest
├── config.json                               # Panel placement + preset commands
├── resources/
│   └── 64x64.png
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
