"""playgen resource - Create and manage .tres resource files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click


# Default properties for common resource types
RESOURCE_DEFAULTS: dict[str, dict[str, str]] = {
    "RectangleShape2D": {"size": "Vector2(32, 32)"},
    "CircleShape2D": {"radius": "16.0"},
    "CapsuleShape2D": {"radius": "10.0", "height": "30.0"},
    "WorldBoundaryShape2D": {},
    "StyleBoxFlat": {
        "bg_color": "Color(0.2, 0.2, 0.2, 1)",
    },
    "StyleBoxEmpty": {},
    "LabelSettings": {"font_size": "16"},
    "PhysicsMaterial": {"bounce": "0.0", "friction": "1.0"},
    "Environment": {},
    "Gradient": {},
    "Curve": {},
    "Theme": {},
}

# Theme preset: dark modern UI
THEME_PRESETS: dict[str, dict] = {
    "dark": {
        "sub_resources": [
            {
                "type": "StyleBoxFlat", "id": "panel_style",
                "properties": {
                    "bg_color": "Color(0.12, 0.12, 0.15, 0.95)",
                    "corner_radius_top_left": "8",
                    "corner_radius_top_right": "8",
                    "corner_radius_bottom_right": "8",
                    "corner_radius_bottom_left": "8",
                },
            },
            {
                "type": "StyleBoxFlat", "id": "button_normal",
                "properties": {
                    "bg_color": "Color(0.22, 0.22, 0.28, 1)",
                    "corner_radius_top_left": "4",
                    "corner_radius_top_right": "4",
                    "corner_radius_bottom_right": "4",
                    "corner_radius_bottom_left": "4",
                },
            },
            {
                "type": "StyleBoxFlat", "id": "button_hover",
                "properties": {
                    "bg_color": "Color(0.3, 0.3, 0.4, 1)",
                    "corner_radius_top_left": "4",
                    "corner_radius_top_right": "4",
                    "corner_radius_bottom_right": "4",
                    "corner_radius_bottom_left": "4",
                },
            },
            {
                "type": "StyleBoxFlat", "id": "button_pressed",
                "properties": {
                    "bg_color": "Color(0.15, 0.15, 0.2, 1)",
                    "corner_radius_top_left": "4",
                    "corner_radius_top_right": "4",
                    "corner_radius_bottom_right": "4",
                    "corner_radius_bottom_left": "4",
                },
            },
        ],
        "properties": {
            "default_font_size": "16",
            "Button/styles/normal": 'SubResource("button_normal")',
            "Button/styles/hover": 'SubResource("button_hover")',
            "Button/styles/pressed": 'SubResource("button_pressed")',
            "Panel/styles/panel": 'SubResource("panel_style")',
            "Button/colors/font_color": "Color(0.88, 0.88, 0.92, 1)",
            "Button/colors/font_hover_color": "Color(1, 1, 1, 1)",
            "Label/colors/font_color": "Color(0.88, 0.88, 0.92, 1)",
        },
    },
    "light": {
        "sub_resources": [
            {
                "type": "StyleBoxFlat", "id": "panel_style",
                "properties": {
                    "bg_color": "Color(0.95, 0.95, 0.97, 0.95)",
                    "corner_radius_top_left": "8",
                    "corner_radius_top_right": "8",
                    "corner_radius_bottom_right": "8",
                    "corner_radius_bottom_left": "8",
                },
            },
            {
                "type": "StyleBoxFlat", "id": "button_normal",
                "properties": {
                    "bg_color": "Color(0.85, 0.85, 0.9, 1)",
                    "corner_radius_top_left": "4",
                    "corner_radius_top_right": "4",
                    "corner_radius_bottom_right": "4",
                    "corner_radius_bottom_left": "4",
                },
            },
            {
                "type": "StyleBoxFlat", "id": "button_hover",
                "properties": {
                    "bg_color": "Color(0.78, 0.78, 0.85, 1)",
                    "corner_radius_top_left": "4",
                    "corner_radius_top_right": "4",
                    "corner_radius_bottom_right": "4",
                    "corner_radius_bottom_left": "4",
                },
            },
        ],
        "properties": {
            "default_font_size": "16",
            "Button/styles/normal": 'SubResource("button_normal")',
            "Button/styles/hover": 'SubResource("button_hover")',
            "Panel/styles/panel": 'SubResource("panel_style")',
            "Button/colors/font_color": "Color(0.15, 0.15, 0.2, 1)",
            "Label/colors/font_color": "Color(0.15, 0.15, 0.2, 1)",
        },
    },
}


def write_tres(
    res_type: str,
    properties: dict[str, str],
    sub_resources: list[dict] | None = None,
) -> str:
    """Write a .tres resource file."""
    lines: list[str] = []

    load_steps = 1
    if sub_resources:
        load_steps += len(sub_resources)

    if load_steps > 1:
        lines.append(f'[gd_resource type="{res_type}" load_steps={load_steps} format=3]')
    else:
        lines.append(f'[gd_resource type="{res_type}" format=3]')
    lines.append("")

    if sub_resources:
        for sub in sub_resources:
            sub_type = sub.get("type", "")
            sub_id = sub.get("id", "")
            lines.append(f'[sub_resource type="{sub_type}" id="{sub_id}"]')
            for k, v in sub.get("properties", {}).items():
                lines.append(f"{k} = {v}")
            lines.append("")

    lines.append("[resource]")
    for k, v in properties.items():
        lines.append(f"{k} = {v}")
    lines.append("")

    return "\n".join(lines)


@click.group("resource")
def resource_cmd() -> None:
    """Resource operations: create and list .tres files.

    Resources include themes, shapes, materials, and any Godot Resource type.
    """
    pass


@resource_cmd.command("create")
@click.argument("path")
@click.option("--type", "-t", "res_type", required=True,
              help="Resource type (e.g., Theme, StyleBoxFlat, RectangleShape2D)")
@click.option("--property", "-P", "properties", multiple=True,
              help="Property as key=value (repeatable)")
@click.option("--preset", default=None,
              help="Use a preset (for Theme: 'dark', 'light')")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def resource_create(ctx: click.Context, path: str, res_type: str,
                    properties: tuple[str, ...], preset: str | None, as_json: bool) -> None:
    """Create a .tres resource file.

    PATH is the resource filename (e.g., 'ui_theme.tres').

    \b
    Examples:
      playgen resource create ui_theme.tres -t Theme --preset dark
      playgen resource create player_shape.tres -t RectangleShape2D -P "size=Vector2(28, 44)"
      playgen resource create btn_style.tres -t StyleBoxFlat -P "bg_color=Color(0.3,0.3,0.8,1)"
    """
    project_path: Path = ctx.obj["project_path"]
    if not path.endswith(".tres"):
        path += ".tres"

    file_path = project_path / path

    # Build properties
    props: dict[str, str] = {}
    sub_resources: list[dict] | None = None

    # Apply preset if available
    if preset and res_type == "Theme" and preset in THEME_PRESETS:
        preset_data = THEME_PRESETS[preset]
        sub_resources = preset_data.get("sub_resources")
        props.update(preset_data.get("properties", {}))
    elif res_type in RESOURCE_DEFAULTS:
        props.update(RESOURCE_DEFAULTS[res_type])

    # Apply user properties (override defaults)
    for prop in properties:
        if "=" not in prop:
            click.echo(f"Error: Invalid property format '{prop}', expected key=value", err=True)
            ctx.exit(1)
            return
        k, v = prop.split("=", 1)
        props[k.strip()] = v.strip()

    content = write_tres(res_type, props, sub_resources)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"created": path, "type": res_type, "properties": props}))
    else:
        extra = f" [preset: {preset}]" if preset else ""
        click.echo(f"Created resource: {path} ({res_type}){extra}")


@resource_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def resource_list(ctx: click.Context, as_json: bool) -> None:
    """List all .tres resource files in the project."""
    project_path: Path = ctx.obj["project_path"]

    resources: list[dict[str, str]] = []
    for f in sorted(project_path.rglob("*.tres")):
        if ".godot" in str(f):
            continue
        rel = f.relative_to(project_path)
        res_type = ""
        try:
            first_line = f.read_text(encoding="utf-8").split("\n")[0]
            m = re.search(r'type="(\w+)"', first_line)
            if m:
                res_type = m.group(1)
        except Exception:
            pass
        resources.append({"path": str(rel).replace("\\", "/"), "type": res_type})

    if as_json:
        click.echo(json.dumps(resources, indent=2))
    else:
        if not resources:
            click.echo("No .tres resource files found.")
            return
        for r in resources:
            click.echo(f"  res://{r['path']:40s} ({r['type']})")
