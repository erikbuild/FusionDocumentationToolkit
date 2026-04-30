# FusionDocumentationToolkit

![Version 1.0](https://img.shields.io/badge/version-1.0-blue)

A Fusion 360 add-in for documentation and assembly-manual workflows: a one-click visual-style preset toggle, hotkey-friendly viewport image capture with auto-numbered filenames and embedded DPI metadata, and a custom toolbar panel.

![Demo](demo.gif)

## Install

**macOS**
```
cd ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/
git clone https://github.com/erikbuild/FusionDocumentationToolkit.git
```

**Windows**
Clone or download the repo into `%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns\`.

Then in Fusion: **Utilities → Add-Ins** (or `Shift+S`), find **FusionDocumentationToolkit**, click **Run**. Three buttons land on a new **DOCUMENTATION** panel in the Solid workspace.

## Assign a hotkey to Capture Image

This is the headline workflow — pressing one key combo to fire a screenshot. Fusion's API can't bind shortcuts programmatically, so do it once via the UI:

1. On the **DOCUMENTATION** panel, click the **dropdown arrow** next to the panel label.
2. Hover over **Capture Image** in the dropdown.
3. Click the **⋯** (three-dot menu) that appears on the right.
4. Choose **Change Keyboard Shortcut**.
5. Press the key combo — `Control+Shift+S` is a good default.

Repeat for **Configure Capture** if you want a separate shortcut for the settings dialog.

## Use

| Button | What it does |
|---|---|
| **Voron-style Mode Switch** | Toggles between the bundled Voron-style visual preset and Fusion defaults. |
| **Capture Image** | Silent capture. First press of each Fusion session prompts for an output folder; later presses save auto-numbered files (`capture_001.png`, `capture_002.png`, …) with DPI metadata embedded. Status logs to the Text Commands palette. |
| **Configure Capture** | Edit per-session capture settings: folder, dimensions, format (PNG/JPG), DPI, transparent background, anti-aliasing. |

## Configuration

All settings live in `config.json` next to the source. Edit and re-run the add-in to apply. Notable keys:

- `capture.default_dpi` — DPI metadata for saved files (default `300`).
- `capture.default_width` / `default_height` — pixel size, 108–4000.
- `capture.default_format` — `"png"` or `"jpg"`.
- `presets.voron.commands` / `presets.default.commands` — Fusion text commands applied when toggling. Edit to build your own preset.
- `panel_name` — toolbar panel label (default `DOCUMENTATION`).

The bundled `voron` preset matches the Voron Design Team's recommended assembly-manual settings: Photobooth environment, wireframe with visible edges only, ambient occlusion on, ground plane / shadow / reflection off, orthographic camera. One setting the API can't script is **Hidden Edge Dimming** — set it to 0% once in Fusion's Preferences and leave it.

## License

[MIT + Commons Clause](LICENSE) — © Erik Reynolds ([@erikbuild](https://github.com/erikbuild))
