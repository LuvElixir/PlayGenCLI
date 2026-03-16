"""playgen input - Manage input mappings in project.godot."""

from __future__ import annotations

import json
import re

import click

from playgen.godot.project_file import load_project, save_project


# ---------------------------------------------------------------------------
# Godot 4.x key constants (physical_keycode values)
# SPKEY = 1 << 22 = 4194304
# ---------------------------------------------------------------------------

KEY_MAP: dict[str, int] = {
    # Letters (ASCII)
    "a": 65, "b": 66, "c": 67, "d": 68, "e": 69, "f": 70, "g": 71,
    "h": 72, "i": 73, "j": 74, "k": 75, "l": 76, "m": 77, "n": 78,
    "o": 79, "p": 80, "q": 81, "r": 82, "s": 83, "t": 84, "u": 85,
    "v": 86, "w": 87, "x": 88, "y": 89, "z": 90,
    # Numbers
    "0": 48, "1": 49, "2": 50, "3": 51, "4": 52,
    "5": 53, "6": 54, "7": 55, "8": 56, "9": 57,
    # Special keys
    "space": 32, "escape": 4194305, "tab": 4194306,
    "backspace": 4194308, "enter": 4194309,
    "insert": 4194311, "delete": 4194312,
    "home": 4194317, "end": 4194318,
    "left": 4194319, "up": 4194320, "right": 4194321, "down": 4194322,
    "pageup": 4194323, "pagedown": 4194324,
    "shift": 4194325, "ctrl": 4194326, "alt": 4194328,
    # Function keys
    "f1": 4194332, "f2": 4194333, "f3": 4194334, "f4": 4194335,
    "f5": 4194336, "f6": 4194337, "f7": 4194338, "f8": 4194339,
    "f9": 4194340, "f10": 4194341, "f11": 4194342, "f12": 4194343,
    # Punctuation
    "minus": 45, "equal": 61, "bracketleft": 91, "bracketright": 93,
    "semicolon": 59, "apostrophe": 39, "comma": 44, "period": 46,
    "slash": 47, "backslash": 92, "grave": 96,
}

# Reverse lookup for display
_REV_KEY_MAP: dict[int, str] = {v: k for k, v in KEY_MAP.items()}

# Joypad button indices
JOYPAD_MAP: dict[str, int] = {
    "joypad_a": 0, "joypad_b": 1, "joypad_x": 2, "joypad_y": 3,
    "joypad_select": 4, "joypad_guide": 5, "joypad_start": 6,
    "joypad_lstick": 7, "joypad_rstick": 8,
    "joypad_lb": 9, "joypad_rb": 10,
    "joypad_up": 11, "joypad_down": 12, "joypad_left": 13, "joypad_right": 14,
}

# Mouse button indices
MOUSE_MAP: dict[str, int] = {
    "mouse_left": 1, "mouse_right": 2, "mouse_middle": 3,
    "mouse_wheel_up": 4, "mouse_wheel_down": 5,
}


def _make_key_event(keycode: int) -> str:
    return (
        'Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"",'
        '"device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,'
        '"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,'
        f'"physical_keycode":{keycode},"key_label":0,"unicode":0,'
        '"location":0,"echo":false,"script":null)'
    )


def _make_joypad_event(button_index: int) -> str:
    return (
        'Object(InputEventJoypadButton,"resource_local_to_scene":false,'
        f'"resource_name":"","device":-1,"button_index":{button_index},'
        '"pressure":0.0,"pressed":false,"script":null)'
    )


def _make_mouse_event(button_index: int) -> str:
    return (
        'Object(InputEventMouseButton,"resource_local_to_scene":false,'
        '"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,'
        '"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,'
        '"button_mask":0,"position":Vector2(0, 0),"global_position":Vector2(0, 0),'
        f'"factor":1.0,"button_index":{button_index},"canceled":false,'
        '"pressed":false,"double_click":false,"script":null)'
    )


def make_input_event(key_name: str) -> str:
    """Create an input event Object() string for a key name."""
    name = key_name.lower()
    if name in KEY_MAP:
        return _make_key_event(KEY_MAP[name])
    if name in JOYPAD_MAP:
        return _make_joypad_event(JOYPAD_MAP[name])
    if name in MOUSE_MAP:
        return _make_mouse_event(MOUSE_MAP[name])
    # Try as numeric keycode
    try:
        return _make_key_event(int(key_name))
    except ValueError:
        pass
    # Fallback: treat as unknown key
    return _make_key_event(0)


def format_input_value(keys: list[str], deadzone: float = 0.2) -> str:
    """Format the complete input action value for project.godot."""
    events = [make_input_event(k) for k in keys]
    events_str = ", ".join(events)
    return f'{{\n"deadzone": {deadzone},\n"events": [{events_str}]\n}}'


def _extract_event_names(
    value: str,
    rev_joy: dict[int, str],
    rev_mouse: dict[int, str],
) -> list[str]:
    """Extract human-readable event names from an input action value."""
    names: list[str] = []
    # Split by Object( prefix to find each event block
    parts = value.split("Object(")
    for part in parts[1:]:  # skip first empty/non-event part
        if part.startswith("InputEventKey,"):
            kc_m = re.search(r'"physical_keycode":(\d+)', part)
            if kc_m:
                kc = int(kc_m.group(1))
                if kc in _REV_KEY_MAP:
                    names.append(_REV_KEY_MAP[kc])
                elif kc > 0:
                    names.append(f"key({kc})")
        elif part.startswith("InputEventJoypadButton,"):
            btn_m = re.search(r'"button_index":(\d+)', part)
            if btn_m:
                btn = int(btn_m.group(1))
                names.append(rev_joy.get(btn, f"joypad({btn})"))
        elif part.startswith("InputEventMouseButton,"):
            btn_m = re.search(r'"button_index":(\d+)', part)
            if btn_m:
                btn = int(btn_m.group(1))
                names.append(rev_mouse.get(btn, f"mouse({btn})"))
    return names


@click.group("input")
def input_cmd() -> None:
    """Input mapping: add, remove, list input actions.

    \b
    Available key names:
      Letters:  a-z
      Numbers:  0-9
      Arrows:   up, down, left, right
      Special:  space, enter, escape, tab, backspace, shift, ctrl, alt
      F-keys:   f1-f12
      Mouse:    mouse_left, mouse_right, mouse_middle
      Joypad:   joypad_a, joypad_b, joypad_x, joypad_y, joypad_lb, joypad_rb
    """
    pass


@input_cmd.command("add")
@click.argument("action")
@click.option("--key", "-k", "keys", multiple=True, required=True,
              help="Key binding (repeatable, e.g., -k w -k up)")
@click.option("--deadzone", "-d", default=0.2, help="Deadzone (default: 0.2)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def input_add(ctx: click.Context, action: str, keys: tuple[str, ...], deadzone: float, as_json: bool) -> None:
    """Add an input action with key bindings.

    ACTION is the action name (e.g., 'move_left', 'jump').

    \b
    Examples:
      playgen input add move_left -k a -k left
      playgen input add move_right -k d -k right
      playgen input add move_up -k w -k up
      playgen input add move_down -k s -k down
      playgen input add jump -k space
      playgen input add attack -k mouse_left -k joypad_x
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    value = format_input_value(list(keys), deadzone)
    proj.set("input", action, value)
    save_project(proj, project_path)

    if as_json:
        click.echo(json.dumps({"action": action, "keys": list(keys)}))
    else:
        click.echo(f"Input added: {action} -> [{', '.join(keys)}]")


@input_cmd.command("remove")
@click.argument("action")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def input_remove(ctx: click.Context, action: str, as_json: bool) -> None:
    """Remove an input action."""
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    inputs = proj.sections.get("input", {})
    if action not in inputs:
        msg = f"Input action '{action}' not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    del proj.sections["input"][action]
    save_project(proj, project_path)

    if as_json:
        click.echo(json.dumps({"removed": action}))
    else:
        click.echo(f"Input removed: {action}")


@input_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def input_list(ctx: click.Context, as_json: bool) -> None:
    """List all input actions and their bindings."""
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    inputs = proj.sections.get("input", {})

    if as_json:
        actions = []
        for name, value in inputs.items():
            keycodes = [int(k) for k in re.findall(r'"physical_keycode":(\d+)', value)]
            actions.append({"action": name, "keycodes": keycodes})
        click.echo(json.dumps(actions, indent=2))
    else:
        if not inputs:
            click.echo("No input actions configured.")
            return
        rev_joy = {v: k for k, v in JOYPAD_MAP.items()}
        rev_mouse = {v: k for k, v in MOUSE_MAP.items()}
        for name, value in inputs.items():
            key_names: list[str] = _extract_event_names(value, rev_joy, rev_mouse)
            click.echo(f"  {name:25s} [{', '.join(key_names)}]")
