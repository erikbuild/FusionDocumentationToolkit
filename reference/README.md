# Reference

## fusion_textcommands_8176.txt

Dump of ~2600 Fusion 360 text commands, captured from Fusion build 8176. Sourced from [kantoku-code/Fusion360_Small_Tools_for_Developers](https://github.com/kantoku-code/Fusion360_Small_Tools_for_Developers/blob/master/TextCommands/TextCommands_txt_Ver2_0_8176.txt).

Each line has the form `  CommandName  - description and optional [/args]`. Use `grep` or the Grep tool to find commands relevant to whatever setting you want to script.

### How to regenerate

Inside Fusion's Text Commands palette (Py mode):

```
DebugCommands.ListCommandDefinitions /Summary
```

Capture the palette output to get the current build's complete list. Useful if a command referenced in this file has been renamed in a newer Fusion version.

### How to use commands from this list

Open Fusion → **File → View → Show Text Commands Palette** (`Cmd+Option+C` on macOS, `Ctrl+Alt+C` on Windows). Set the dropdown at the bottom of the palette to **Py**. Type a command line from this file and press Enter. Fusion executes it immediately.

From Python code, the same commands are dispatched via:

```python
app = adsk.core.Application.get()
app.executeTextCommand("Scene.Camera /ortho")
```

### Useful subsets

| Prefix | What it controls |
|---|---|
| `Scene.*` | Scene/graphics-level state (camera, wireframe, environment loading, MSAA count) |
| `Options.*` | Persistent option toggles (MSAA, dome, ground plane, object shadow type, selection effect, transparency effect) |
| `NuCommands.View*Cmd` | Menu toggle commands (ambient occlusion, ground reflection, ground shadow) — these flip from current state |
| `DebugCommands.*` | Introspection: list commands, count objects, trace |
| `Application.log` / `Debug.*` | Logging and debug utilities |
