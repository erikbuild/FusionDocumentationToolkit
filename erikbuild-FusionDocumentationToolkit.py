# ABOUTME: Fusion 360 documentation toolkit — configurable visual-style presets
# ABOUTME: and hotkey-friendly viewport image capture with DPI metadata.

import adsk.core
import adsk.fusion
import traceback
import json
import os
import struct
import zlib

_app = None
_ui = None
_handlers = []
_active_panel_id = None
_custom_panel_id = None
_config = None
_current_mode = None

_capture_folder = None
_capture_width = 1920
_capture_height = 1080
_capture_format = 'png'
_capture_transparent = False
_capture_antialias = True
_capture_dpi = 300
_capture_counter = 0

CMD_ID = 'VoronStyleManualModeCmd'
CMD_NAME = 'Voron-style Mode Switch'
CMD_DESCRIPTION = 'Toggle Fusion between the Voron Design Team assembly manual visual preset and the Fusion default preset.'
PANEL_ID = 'InspectPanel'
FALLBACK_PANEL_ID = 'SolidScriptsAddinsPanel'

WORKSPACE_ID = 'FusionSolidEnvironment'
TAB_ID = 'SolidTab'

VORON_MODE = 'voron'
DEFAULT_MODE = 'default'
TODO_PREFIX = 'TODO_'

CAPTURE_CMD_ID = 'CaptureImageCmd'
CAPTURE_CMD_NAME = 'Capture Image'
CAPTURE_CMD_DESCRIPTION = 'Save the active viewport to an image file using the configured settings. The first capture of each Fusion session prompts for an output folder; subsequent captures save silently with auto-incrementing names.'

CONFIGURE_CAPTURE_CMD_ID = 'ConfigureCaptureCmd'
CONFIGURE_CAPTURE_CMD_NAME = 'Configure Capture'
CONFIGURE_CAPTURE_CMD_DESCRIPTION = 'Adjust the per-session capture settings: output folder, image dimensions, format, transparency, and anti-aliasing.'

LOG_PREFIX = '[CaptureImage] '


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def get_or_create_custom_panel(panel_id, panel_name):
    try:
        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            return None
        tab = workspace.toolbarTabs.itemById(TAB_ID)
        if not tab:
            return None
        panel = tab.toolbarPanels.itemById(panel_id)
        if not panel:
            panel = tab.toolbarPanels.add(panel_id, panel_name)
        return panel
    except:
        return None


def purge_stale_controls(cmd_ids):
    """Remove every toolbar control matching these command IDs from every panel.
    Catches orphaned buttons from prior runs that placed controls on different
    panels (e.g. before use_custom_panel was switched on)."""
    if not _ui:
        return
    panels = _ui.allToolbarPanels
    for i in range(panels.count):
        panel = panels.item(i)
        for cid in cmd_ids:
            try:
                ctrl = panel.controls.itemById(cid)
                if ctrl:
                    ctrl.deleteMe()
            except Exception:
                pass


def register_command(panel, cmd_id, name, description, resource_dir, created_handler):
    """Create or refresh a button command, attach the supplied CommandCreated
    handler, and place a control on the given panel. Returns the CommandDefinition
    so callers can configure it further if needed."""
    existing = _ui.commandDefinitions.itemById(cmd_id)
    if existing:
        existing.deleteMe()
    cmd_def = _ui.commandDefinitions.addButtonDefinition(
        cmd_id, name, description, resource_dir
    )
    cmd_def.commandCreated.add(created_handler)
    _handlers.append(created_handler)
    if panel:
        existing_ctrl = panel.controls.itemById(cmd_id)
        if not existing_ctrl:
            ctrl = panel.controls.addCommand(cmd_def)
            ctrl.isPromotedByDefault = True
            ctrl.isPromoted = True
    return cmd_def


def preset(name):
    presets = (_config or {}).get('presets', {})
    return presets.get(name, {})


def other_mode(name):
    return DEFAULT_MODE if name == VORON_MODE else VORON_MODE


def debug_enabled():
    return bool((_config or {}).get('debug'))


def run_command(cmd_entry):
    """Execute a single preset command entry.

    An entry has either a `visual_style` key (naming a value from the
    adsk.core.VisualStyles enum) or a `cmd` key (a text command string
    passed to Application.executeTextCommand). The `visual_style` path
    is used because the Viewport.visualStyle API is the only verified
    way to set visual style programmatically.

    Returns (ok, reason) where ok is True on success, False/'pending'
    for legacy TODO placeholders, or False/error text on failure.
    """
    style_name = (cmd_entry.get('visual_style') or '').strip()
    if style_name:
        try:
            style_enum = getattr(adsk.core.VisualStyles, style_name)
            _app.activeViewport.visualStyle = style_enum
            return True, ''
        except AttributeError:
            return False, 'unknown VisualStyles value: {}'.format(style_name)
        except Exception as exc:
            return False, str(exc)

    cmd = (cmd_entry.get('cmd') or '').strip()
    if not cmd:
        return False, 'empty command'
    if cmd.startswith(TODO_PREFIX):
        return False, 'pending'

    try:
        _app.executeTextCommand(cmd)
        return True, ''
    except Exception as exc:
        return False, str(exc)


def apply_preset(mode):
    preset_data = preset(mode)
    commands = preset_data.get('commands', [])
    if not commands:
        _ui.messageBox("No commands configured for preset '{}'. Edit config.json.".format(mode))
        return False

    applied = 0
    failed = []
    pending = []

    for entry in commands:
        ok, reason = run_command(entry)
        label = entry.get('label', '(unlabeled)')
        if ok:
            applied += 1
        elif reason == 'pending':
            pending.append(label)
        else:
            failed.append('{}: {}'.format(label, reason))

    if debug_enabled():
        lines = ['Preset: {}'.format(preset_data.get('label', mode)),
                 'Applied: {}/{}'.format(applied, len(commands))]
        if pending:
            lines.append('')
            lines.append('Pending (TODO, not yet discovered):')
            lines.extend('  - {}'.format(p) for p in pending)
        if failed:
            lines.append('')
            lines.append('Failed:')
            lines.extend('  - {}'.format(f) for f in failed)
        _ui.messageBox('\n'.join(lines))

    return applied > 0


def capture_log(message):
    """Write a status line to Fusion's Text Commands palette."""
    if _app:
        try:
            _app.log(LOG_PREFIX + message)
        except Exception:
            pass


def capture_filename_prefix():
    return str((_config or {}).get('capture', {}).get('filename_prefix', 'capture'))


def capture_format_extension():
    return 'jpg' if _capture_format in ('jpg', 'jpeg') else _capture_format


def init_capture_defaults():
    """Populate per-session capture state from the 'capture' section of config.json."""
    global _capture_folder, _capture_width, _capture_height, _capture_format
    global _capture_transparent, _capture_antialias, _capture_dpi, _capture_counter
    cap = (_config or {}).get('capture', {})
    _capture_folder = None
    _capture_width = int(cap.get('default_width', 1920))
    _capture_height = int(cap.get('default_height', 1080))
    fmt = str(cap.get('default_format', 'png')).lower()
    _capture_format = fmt if fmt in ('png', 'jpg', 'jpeg') else 'png'
    _capture_transparent = bool(cap.get('default_transparent', False))
    _capture_antialias = bool(cap.get('default_antialias', True))
    _capture_dpi = int(cap.get('default_dpi', 300))
    _capture_counter = 0


def prompt_for_capture_folder():
    """Show a folder picker. Returns the chosen folder path, or None on cancel."""
    try:
        dialog = _ui.createFolderDialog()
        dialog.title = 'Select Capture Output Folder'
        if _capture_folder:
            dialog.initialDirectory = _capture_folder
        if dialog.showDialog() == adsk.core.DialogResults.DialogOK:
            return dialog.folder
        return None
    except Exception as exc:
        capture_log('Folder dialog failed: {}'.format(exc))
        return None


def seed_capture_counter(folder, prefix, ext):
    """Scan folder for existing prefix_NNN.ext files and set the counter past the max."""
    global _capture_counter
    try:
        if not folder or not os.path.isdir(folder):
            _capture_counter = 0
            return
        max_n = 0
        prefix_lc = (prefix + '_').lower()
        ext_lc = '.' + ext.lower()
        for name in os.listdir(folder):
            name_lc = name.lower()
            if not name_lc.startswith(prefix_lc) or not name_lc.endswith(ext_lc):
                continue
            stem = name[len(prefix) + 1:-len(ext_lc)]
            try:
                n = int(stem)
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
        _capture_counter = max_n
    except Exception as exc:
        capture_log('Counter seed failed: {}'.format(exc))
        _capture_counter = 0


def set_image_dpi(path, dpi):
    """Write DPI metadata to a PNG or JPG file in place. Pixel dimensions are
    not modified — only the file's reported resolution, which apps like
    InDesign/Photoshop read to size placed images for print. Silently no-ops
    on unsupported formats or malformed files."""
    if not path or not os.path.isfile(path) or dpi <= 0:
        return
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.png':
            _set_png_dpi(path, dpi)
        elif ext in ('.jpg', '.jpeg'):
            _set_jpg_dpi(path, dpi)
    except Exception as exc:
        capture_log('DPI tag failed for {}: {}'.format(path, exc))


def _set_png_dpi(path, dpi):
    """Insert or replace the pHYs chunk in a PNG file."""
    px_per_m = int(round(dpi / 0.0254))
    with open(path, 'rb') as f:
        data = f.read()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return
    phys_payload = struct.pack('>IIB', px_per_m, px_per_m, 1)
    crc = zlib.crc32(b'pHYs' + phys_payload) & 0xFFFFFFFF
    phys_chunk = struct.pack('>I', 9) + b'pHYs' + phys_payload + struct.pack('>I', crc)

    phys_pos = data.find(b'pHYs')
    if phys_pos > 4:
        chunk_start = phys_pos - 4
        chunk_end = phys_pos + 4 + 9 + 4
        new_data = data[:chunk_start] + phys_chunk + data[chunk_end:]
    else:
        ihdr_end = 8 + 4 + 4 + 13 + 4
        new_data = data[:ihdr_end] + phys_chunk + data[ihdr_end:]
    with open(path, 'wb') as f:
        f.write(new_data)


def _set_jpg_dpi(path, dpi):
    """Update the JFIF APP0 segment's density fields in a JPEG file."""
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    if data[:2] != b'\xff\xd8':
        return
    i = 2
    while i < len(data) - 3:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xE0 and data[i + 4:i + 9] == b'JFIF\x00':
            data[i + 11] = 1
            struct.pack_into('>HH', data, i + 12, dpi, dpi)
            with open(path, 'wb') as f:
                f.write(data)
            return
        if 0xD0 <= marker <= 0xD9 or marker == 0x01:
            i += 2
            continue
        seg_len = (data[i + 2] << 8) | data[i + 3]
        i += 2 + seg_len


def next_capture_path():
    """Increment the session counter and return a non-colliding full path."""
    global _capture_counter
    prefix = capture_filename_prefix()
    ext = capture_format_extension()
    while True:
        _capture_counter += 1
        candidate = os.path.join(
            _capture_folder,
            '{}_{:03d}.{}'.format(prefix, _capture_counter, ext)
        )
        if not os.path.exists(candidate):
            return candidate


def capture_image():
    """Save the active viewport to the session output folder. Prompts for the
    folder on first use; logs every meaningful event to the Text Commands palette."""
    global _capture_folder
    if not _app or not _app.activeViewport:
        if _ui:
            _ui.messageBox('No active viewport. Open a document before capturing.')
        return False

    if not _capture_folder:
        chosen = prompt_for_capture_folder()
        if not chosen:
            capture_log('Capture cancelled (no folder selected)')
            return False
        _capture_folder = chosen
        seed_capture_counter(_capture_folder, capture_filename_prefix(),
                             capture_format_extension())
        capture_log('Session folder set: {}'.format(_capture_folder))

    if not os.path.isdir(_capture_folder):
        try:
            os.makedirs(_capture_folder, exist_ok=True)
        except Exception as exc:
            capture_log('Cannot create folder {}: {}'.format(_capture_folder, exc))
            if _ui:
                _ui.messageBox('Unable to create capture folder:\n{}'.format(exc))
            return False

    path = next_capture_path()
    try:
        options = adsk.core.SaveImageFileOptions.create(path)
        options.width = _capture_width
        options.height = _capture_height
        options.isBackgroundTransparent = _capture_transparent
        options.isAntiAliased = _capture_antialias
        ok = _app.activeViewport.saveAsImageFileWithOptions(options)
        if ok:
            set_image_dpi(path, _capture_dpi)
            capture_log('Saved: {}  ({}x{}, {}, {}dpi, transparent={}, aa={})'.format(
                path, _capture_width, _capture_height, _capture_format,
                _capture_dpi, _capture_transparent, _capture_antialias))
            return True
        capture_log('Save failed (returned False): {}'.format(path))
        return False
    except Exception as exc:
        capture_log('Save raised: {}'.format(exc))
        if _ui:
            _ui.messageBox('Capture failed:\n{}'.format(traceback.format_exc()))
        return False


def run(context):
    global _app, _ui, _active_panel_id, _custom_panel_id, _config, _current_mode
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _config = load_config()
        _current_mode = _config.get('start_mode', DEFAULT_MODE)
        if _current_mode not in (VORON_MODE, DEFAULT_MODE):
            _current_mode = DEFAULT_MODE

        init_capture_defaults()

        purge_stale_controls((CMD_ID, CAPTURE_CMD_ID, CONFIGURE_CAPTURE_CMD_ID))

        panel = None
        if _config.get('use_custom_panel'):
            panel_id = _config.get('panel_id', 'ErikBuildPlugins_Panel')
            panel_name = _config.get('panel_name', 'ERIKBUILD PLUGINS')
            _custom_panel_id = panel_id
            panel = get_or_create_custom_panel(panel_id, panel_name)

        if not panel:
            panel = _ui.allToolbarPanels.itemById(PANEL_ID)
        if not panel:
            panel = _ui.allToolbarPanels.itemById(FALLBACK_PANEL_ID)

        if panel:
            _active_panel_id = panel.id

        resources_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')

        register_command(panel, CMD_ID, CMD_NAME, CMD_DESCRIPTION,
                         os.path.join(resources_root, 'voronToggle'),
                         CommandCreatedHandler())
        register_command(panel, CAPTURE_CMD_ID, CAPTURE_CMD_NAME,
                         CAPTURE_CMD_DESCRIPTION,
                         os.path.join(resources_root, 'capture'),
                         CaptureCreatedHandler())
        register_command(panel, CONFIGURE_CAPTURE_CMD_ID, CONFIGURE_CAPTURE_CMD_NAME,
                         CONFIGURE_CAPTURE_CMD_DESCRIPTION,
                         os.path.join(resources_root, 'configureCapture'),
                         ConfigureCaptureCreatedHandler())

    except:
        if _ui:
            _ui.messageBox('Failed to start FusionDocumentationToolkit:\n{}'.format(traceback.format_exc()))


def stop(context):
    global _handlers, _active_panel_id, _custom_panel_id
    try:
        cmd_ids = (CMD_ID, CAPTURE_CMD_ID, CONFIGURE_CAPTURE_CMD_ID)
        purge_stale_controls(cmd_ids)

        if _custom_panel_id:
            panel = _ui.allToolbarPanels.itemById(_custom_panel_id)
            if panel and panel.controls.count == 0:
                panel.deleteMe()
        _active_panel_id = None
        _custom_panel_id = None

        for cid in cmd_ids:
            cmd_def = _ui.commandDefinitions.itemById(cid)
            if cmd_def:
                cmd_def.deleteMe()

        _handlers = []

    except:
        if _ui:
            _ui.messageBox('Failed to stop FusionDocumentationToolkit:\n{}'.format(traceback.format_exc()))


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            cmd.okButtonText = 'Toggle'

            on_execute = ExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            _ui.messageBox('CommandCreated failed:\n{}'.format(traceback.format_exc()))


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _current_mode
        try:
            target_mode = other_mode(_current_mode)
            ok = apply_preset(target_mode)
            if ok:
                _current_mode = target_mode
        except:
            _ui.messageBox('Execute failed:\n{}'.format(traceback.format_exc()))


class CaptureCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Wires up the execute handler. The work itself runs in execute so that
    modal dialogs and viewport saves never fire during the create-command
    lifecycle (which crashes Fusion). Setting isAutoExecute when available
    skips Fusion's empty OK dialog so a hotkey press feels instantaneous."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            try:
                cmd.isAutoExecute = True
            except AttributeError:
                pass
            cmd.isExecutedWhenPreEmpted = False

            on_execute = CaptureExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            if _ui:
                _ui.messageBox('Capture setup failed:\n{}'.format(traceback.format_exc()))


class CaptureExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            capture_image()
        except:
            if _ui:
                _ui.messageBox('Capture failed:\n{}'.format(traceback.format_exc()))


class ConfigureCaptureCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            cmd.okButtonText = 'Save Settings'
            inputs = cmd.commandInputs

            folder_display = _capture_folder if _capture_folder else '(prompt on first capture)'
            folder_input = inputs.addStringValueInput('folder', 'Output Folder', folder_display)
            folder_input.isReadOnly = True

            inputs.addBoolValueInput('pickFolder', 'Pick Folder...', False, '', False)

            inputs.addIntegerSpinnerCommandInput(
                'width', 'Width (px)', 108, 4000, 10, _capture_width
            )
            inputs.addIntegerSpinnerCommandInput(
                'height', 'Height (px)', 108, 4000, 10, _capture_height
            )
            inputs.addIntegerSpinnerCommandInput(
                'dpi', 'Resolution (DPI)', 72, 1200, 1, _capture_dpi
            )

            fmt = inputs.addDropDownCommandInput(
                'format', 'Format', adsk.core.DropDownStyles.TextListDropDownStyle
            )
            fmt.listItems.add('png', _capture_format == 'png')
            fmt.listItems.add('jpg', _capture_format in ('jpg', 'jpeg'))

            inputs.addBoolValueInput(
                'transparent', 'Transparent Background', True, '', _capture_transparent
            )
            inputs.addBoolValueInput(
                'antialias', 'Anti-Aliasing', True, '', _capture_antialias
            )

            on_changed = ConfigureCaptureInputChangedHandler()
            cmd.inputChanged.add(on_changed)
            _handlers.append(on_changed)

            on_execute = ConfigureCaptureExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            if _ui:
                _ui.messageBox('Configure setup failed:\n{}'.format(traceback.format_exc()))


class ConfigureCaptureInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Handles the 'Pick Folder...' button: when pressed, opens the OS folder
    dialog and writes the result back into the read-only folder display input."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            changed = args.input
            if changed.id != 'pickFolder' or not changed.value:
                return
            inputs = changed.parentCommand.commandInputs
            folder_display = inputs.itemById('folder')
            chosen = prompt_for_capture_folder()
            if chosen:
                folder_display.value = chosen
            changed.value = False
        except:
            if _ui:
                _ui.messageBox('Folder picker failed:\n{}'.format(traceback.format_exc()))


class ConfigureCaptureExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _capture_folder, _capture_width, _capture_height
        global _capture_format, _capture_transparent, _capture_antialias, _capture_dpi
        try:
            inputs = args.command.commandInputs
            folder_val = inputs.itemById('folder').value
            new_width = inputs.itemById('width').value
            new_height = inputs.itemById('height').value
            new_dpi = inputs.itemById('dpi').value
            new_format = inputs.itemById('format').selectedItem.name
            new_transparent = inputs.itemById('transparent').value
            new_antialias = inputs.itemById('antialias').value

            new_folder = folder_val if folder_val and not folder_val.startswith('(') else None
            if new_folder and new_folder != _capture_folder:
                _capture_folder = new_folder
                ext = 'jpg' if new_format in ('jpg', 'jpeg') else new_format
                seed_capture_counter(_capture_folder, capture_filename_prefix(), ext)
                capture_log('Session folder set: {}'.format(_capture_folder))

            _capture_width = int(new_width)
            _capture_height = int(new_height)
            _capture_dpi = int(new_dpi)
            _capture_format = new_format
            _capture_transparent = bool(new_transparent)
            _capture_antialias = bool(new_antialias)

            capture_log('Settings updated: {}x{} {} {}dpi transparent={} aa={}'.format(
                _capture_width, _capture_height, _capture_format, _capture_dpi,
                _capture_transparent, _capture_antialias))
        except:
            if _ui:
                _ui.messageBox('Configure execute failed:\n{}'.format(traceback.format_exc()))
