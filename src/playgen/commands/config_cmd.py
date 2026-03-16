"""playgen config - Manage project.godot settings."""

from __future__ import annotations

import json
import re

import click

from playgen.godot.project_file import load_project, save_project


# Patterns for values that should NOT be auto-quoted in project.godot
_NO_QUOTE_CONFIG = [
    re.compile(r"^-?\d+(\.\d+)?$"),                     # Numbers
    re.compile(r"^0x[0-9a-fA-F]+$"),                     # Hex
    re.compile(r"^(true|false|null)$"),                   # Keywords
    re.compile(r"^(Vector[234i]?|Color|Rect2i?|Transform[23]D)\("),  # Constructors
    re.compile(r"^Packed(String|Vector|Int|Float|Byte|Color)"),       # Packed arrays
    re.compile(r'^".*"$'),                                # Already quoted
    re.compile(r"^\["),                                   # Arrays
    re.compile(r"^\{"),                                   # Dicts
    re.compile(r'^&"'),                                   # StringName
    re.compile(r'^\^"'),                                  # NodePath
    re.compile(r'^SubResource\('),                        # SubResource
    re.compile(r'^ExtResource\('),                        # ExtResource
]


def _auto_quote_config_value(value: str) -> str:
    """Auto-quote a project.godot value if it looks like a plain string.

    Numbers, booleans, constructors, arrays, dicts, and already-quoted
    strings are left as-is. Everything else gets quoted.
    """
    for pattern in _NO_QUOTE_CONFIG:
        if pattern.match(value):
            return value
    return f'"{value}"'


@click.group("config")
def config_cmd() -> None:
    """Project configuration: set, get, list settings in project.godot.

    Keys use 'section/key' format where the first path component is the
    section name and the rest is the key within that section.
    """
    pass


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--section", "-s", default=None, help="Section name (if not using section/key format)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str, section: str | None, as_json: bool) -> None:
    """Set a project configuration value.

    KEY uses 'section/key/path' format. The first component is the section.

    \b
    Examples:
      playgen config set display/window/size/viewport_width 1920
      playgen config set display/window/size/viewport_height 1080
      playgen config set application/config/name '"My Game"'
      playgen config set rendering/renderer/rendering_method '"gl_compatibility"'
      playgen config set physics/2d/default_gravity 980
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    if section is None:
        parts = key.split("/", 1)
        if len(parts) < 2:
            click.echo("Error: key must be 'section/key' format (e.g., 'display/window/size/viewport_width')", err=True)
            ctx.exit(1)
            return
        section, key = parts[0], parts[1]

    quoted_value = _auto_quote_config_value(value)
    proj.set(section, key, quoted_value)
    save_project(proj, project_path)

    if as_json:
        click.echo(json.dumps({"section": section, "key": key, "value": quoted_value}))
    else:
        click.echo(f"Set [{section}] {key} = {quoted_value}")


@config_cmd.command("get")
@click.argument("key")
@click.option("--section", "-s", default=None, help="Section name (if not using section/key format)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def config_get(ctx: click.Context, key: str, section: str | None, as_json: bool) -> None:
    """Get a project configuration value.

    \b
    Examples:
      playgen config get application/config/name
      playgen config get display/window/size/viewport_width
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    if section is None:
        parts = key.split("/", 1)
        if len(parts) < 2:
            click.echo("Error: key must be 'section/key' format", err=True)
            ctx.exit(1)
            return
        section, key = parts[0], parts[1]

    value = proj.get(section, key)

    if as_json:
        click.echo(json.dumps({"section": section, "key": key, "value": value}))
    else:
        if value:
            click.echo(f"[{section}] {key} = {value}")
        else:
            click.echo(f"[{section}] {key} is not set")


@config_cmd.command("list")
@click.option("--section", "-s", default=None, help="Only show entries in this section")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def config_list(ctx: click.Context, section: str | None, as_json: bool) -> None:
    """List project configuration.

    \b
    Examples:
      playgen config list                  # All sections
      playgen config list -s application   # Application section only
      playgen config list -s display       # Display settings
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    if as_json:
        if section:
            data = proj.sections.get(section, {})
            click.echo(json.dumps({section: data}, indent=2))
        else:
            click.echo(json.dumps(
                {"sections": {s: dict(kvs) for s, kvs in proj.sections.items()}},
                indent=2,
            ))
    else:
        sections_to_show = {section: proj.sections.get(section, {})} if section else proj.sections
        for sec_name, kvs in sections_to_show.items():
            if not kvs:
                continue
            click.echo(f"[{sec_name}]")
            for k, v in kvs.items():
                # Truncate long values for display
                display_v = v if len(v) < 80 else v[:77] + "..."
                click.echo(f"  {k} = {display_v}")
            click.echo()
