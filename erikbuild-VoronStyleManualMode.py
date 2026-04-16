# ABOUTME: Fusion 360 add-in that toggles the viewport between the Voron Design
# ABOUTME: Team assembly manual visual preset and a user-configurable default preset.

import adsk.core
import adsk.fusion
import traceback
import json
import os

_app = None
_ui = None
_handlers = []
_active_panel_id = None
_custom_panel_id = None
_config = None
_current_mode = None

CMD_ID = 'VoronStyleManualModeCmd'
CMD_NAME = 'Voron Manual Mode'
CMD_DESCRIPTION = 'Toggle Fusion between the Voron Design Team assembly manual visual preset and the Fusion default preset.'
PANEL_ID = 'InspectPanel'
FALLBACK_PANEL_ID = 'SolidScriptsAddinsPanel'

WORKSPACE_ID = 'FusionSolidEnvironment'
TAB_ID = 'SolidTab'

VORON_MODE = 'voron'
DEFAULT_MODE = 'default'
TODO_PREFIX = 'TODO_'


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


def run(context):
    global _app, _ui, _active_panel_id, _custom_panel_id, _config, _current_mode
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _config = load_config()
        _current_mode = _config.get('start_mode', DEFAULT_MODE)
        if _current_mode not in (VORON_MODE, DEFAULT_MODE):
            _current_mode = DEFAULT_MODE

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

        resource_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_DESCRIPTION, resource_dir
        )

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)

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
            existing = panel.controls.itemById(CMD_ID)
            if not existing:
                ctrl = panel.controls.addCommand(cmd_def)
                ctrl.isPromotedByDefault = True
                ctrl.isPromoted = True

    except:
        if _ui:
            _ui.messageBox('Failed to start VoronStyleManualMode:\n{}'.format(traceback.format_exc()))


def stop(context):
    global _handlers, _active_panel_id, _custom_panel_id
    try:
        if _active_panel_id:
            panel = _ui.allToolbarPanels.itemById(_active_panel_id)
            if panel:
                ctrl = panel.controls.itemById(CMD_ID)
                if ctrl:
                    ctrl.deleteMe()
                if _custom_panel_id and _active_panel_id == _custom_panel_id and panel.controls.count == 0:
                    panel.deleteMe()
            _active_panel_id = None
            _custom_panel_id = None

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

        _handlers = []

    except:
        if _ui:
            _ui.messageBox('Failed to stop VoronStyleManualMode:\n{}'.format(traceback.format_exc()))


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
