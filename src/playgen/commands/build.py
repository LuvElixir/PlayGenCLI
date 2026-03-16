"""playgen build - Build a complete scene from a JSON description.

This is the highest-leverage command for Agent-driven development.
Instead of 20+ sequential CLI calls, an Agent can output one JSON
description and get a complete, runnable scene with all resources,
scripts, nodes, and signal connections.

v0.7.0 enhancements:
- Auto-visual placeholders for body types (fixes #1 Agent failure mode at build time)
- Type inference from shorthands (texture → Sprite2D, text → Label, audio → AudioStreamPlayer)
- "text" shorthand for Label/Button nodes
- "color" shorthand for visual nodes
- "size" shorthand for Control nodes (custom_minimum_size)
- collision_layer / collision_mask shorthand (integer or list of layer numbers)
- Script template variables ({{SPEED}}, {{JUMP_VELOCITY}}, etc.)

v0.5.0 enhancements:
- Auto-snapshot before build (--snapshot)
- Asset references in node definitions (auto ext_resource)
- Optional engine-native validation after build (--validate)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import click

from playgen.godot.tscn import Scene, Connection, write_tscn, auto_quote_value, BODY_TYPES, BODY_TYPES_3D
from playgen.godot.project_file import load_project, save_project
from playgen.templates import SCRIPT_TEMPLATES, EXTENDS_DEFAULTS


# ─── Type inference rules ────────────────────────────────────────────
# If "type" is omitted in a node definition, infer from context.

def _infer_type(node_def: dict) -> str:
    """Infer node type from shorthands present in the definition."""
    if node_def.get("type"):
        return node_def["type"]
    if node_def.get("texture"):
        return "Sprite2D"
    if node_def.get("audio"):
        return "AudioStreamPlayer"
    if node_def.get("text") is not None:
        # Has text → Label (unless it has a "pressed" signal → Button)
        return "Label"
    if node_def.get("font"):
        return "Label"
    if node_def.get("instance"):
        return ""  # Instance nodes have empty type
    return ""


# ─── Auto-visual placeholder colors ──────────────────────────────────
# Rotating palette so each body gets a different color.

_PLACEHOLDER_COLORS = [
    "Color(0.25, 0.6, 1.0, 1)",     # Blue
    "Color(1.0, 0.4, 0.4, 1)",      # Red
    "Color(0.4, 0.9, 0.4, 1)",      # Green
    "Color(1.0, 0.8, 0.2, 1)",      # Yellow
    "Color(0.8, 0.4, 1.0, 1)",      # Purple
    "Color(1.0, 0.6, 0.2, 1)",      # Orange
    "Color(0.3, 0.9, 0.9, 1)",      # Cyan
    "Color(1.0, 0.5, 0.7, 1)",      # Pink
]

_DEFAULT_PLACEHOLDER_SIZE = (32, 32)  # Default polygon half-size


def _collision_layers_to_int(layers) -> int:
    """Convert collision layer spec to integer bitmask.

    Accepts:
    - int: used directly
    - list of ints: each is a layer number (1-based), OR'd together
    - str: parsed as int
    """
    if isinstance(layers, int):
        return layers
    if isinstance(layers, str):
        return int(layers)
    if isinstance(layers, list):
        mask = 0
        for layer in layers:
            n = int(layer)
            if 1 <= n <= 32:
                mask |= (1 << (n - 1))
        return mask
    return 1


_TEMPLATE_DEFAULTS: dict[str, dict[str, str]] = {
    "platformer-player": {"SPEED": "300.0", "JUMP_VELOCITY": "-450.0"},
    "topdown-player": {"SPEED": "200.0"},
}

# Defaults also apply to EXTENDS_DEFAULTS templates
_EXTENDS_TEMPLATE_DEFAULTS: dict[str, dict[str, str]] = {
    "CharacterBody2D": {"SPEED": "200.0"},
}


def _apply_template_vars(content: str, variables: dict[str, str]) -> str:
    """Replace {{VAR}} placeholders in script content with values."""
    for key, val in variables.items():
        content = content.replace("{{" + key + "}}", str(val))
    return content


def _fill_template_defaults(content: str, template_name: str | None,
                            extends_type: str | None) -> str:
    """Fill any remaining {{VAR}} placeholders with default values."""
    defaults = {}
    if template_name and template_name in _TEMPLATE_DEFAULTS:
        defaults.update(_TEMPLATE_DEFAULTS[template_name])
    if extends_type and extends_type in _EXTENDS_TEMPLATE_DEFAULTS:
        defaults.update(_EXTENDS_TEMPLATE_DEFAULTS[extends_type])
    for key, val in defaults.items():
        content = content.replace("{{" + key + "}}", val)
    return content


@click.command("build")
@click.argument("source", default="-")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.option("--dry-run", is_flag=True, help="Show what would be created without writing files")
@click.option("--snapshot", "snap_name", default=None, help="Auto-save snapshot before build (safety net)")
@click.option("--validate", is_flag=True, help="Validate scene with Godot engine after build (requires Godot)")
@click.pass_context
def build_cmd(ctx: click.Context, source: str, as_json: bool, dry_run: bool, snap_name: str | None, validate: bool) -> None:
    """Build a scene from a JSON description.

    SOURCE is a JSON file path, or '-' to read from stdin.
    The Agent can pipe a complete scene description and get a runnable result.

    \b
    JSON schema:
    {
      "scene": "main.tscn",
      "autoloads": {"GameManager": "game_manager.gd"},
      "config": {"display/window/size/viewport_width": "1920"},
      "input_map": {"jump": ["space", "up"], "attack": ["mouse_left"]},
      "resources": [
        {"id": "player_shape", "type": "RectangleShape2D",
         "properties": {"size": "Vector2(28, 44)"}}
      ],
      "scripts": {
        "player.gd": {"template": "platformer-player"},
        "game_manager.gd": {"template": "game-manager"}
      },
      "root": {
        "name": "Main", "type": "Node2D",
        "children": [...]
      },
      "connections": [
        {"signal": "body_entered", "from": "Coin",
         "to": ".", "method": "_on_coin_collected"}
      ]
    }
    """
    project_path: Path = ctx.obj["project_path"]

    # Read input
    try:
        if source == "-":
            raw = sys.stdin.read()
        else:
            src_path = Path(source)
            if not src_path.is_absolute():
                src_path = project_path / src_path
            raw = src_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _error(f"Invalid JSON: {e}", as_json, ctx)
        return
    except FileNotFoundError:
        _error(f"File not found: {source}", as_json, ctx)
        return

    scene_name = data.get("scene", "main.tscn")
    if not scene_name.endswith(".tscn"):
        scene_name += ".tscn"

    created_files: list[str] = []
    errors: list[str] = []

    # Auto-snapshot before build if requested
    if snap_name and not dry_run:
        from playgen.commands.snapshot_cmd import save_snapshot
        snap_result = save_snapshot(project_path, snap_name)
        if "error" in snap_result:
            errors.append(f"Snapshot failed: {snap_result['error']}")
        elif not as_json:
            click.echo(f"Snapshot saved: {snap_name}")

    # --- 0. Configure project (autoloads, config, input_map) ---
    _configure_project(data, project_path, errors, dry_run)

    # --- 1. Create scripts ---
    scripts_def = data.get("scripts", {})
    for script_name, script_spec in scripts_def.items():
        if not script_name.endswith(".gd"):
            script_name += ".gd"

        script_path = project_path / script_name
        if script_path.exists() and not data.get("overwrite", False):
            continue

        if isinstance(script_spec, str):
            # Inline content
            content = script_spec
        elif isinstance(script_spec, dict):
            template_name = script_spec.get("template")
            extends_type = script_spec.get("extends", "Node")
            # Support both "body" and "content" keys for inline script content
            content_raw = script_spec.get("body") or script_spec.get("content")
            template_vars = script_spec.get("vars", {})

            if content_raw:
                content = content_raw
            elif template_name and template_name in SCRIPT_TEMPLATES:
                content = SCRIPT_TEMPLATES[template_name]
            elif extends_type in EXTENDS_DEFAULTS:
                content = EXTENDS_DEFAULTS[extends_type]
            else:
                content = f"extends {extends_type}\n\n\nfunc _ready() -> void:\n\tpass\n\n\nfunc _process(delta: float) -> void:\n\tpass\n"

            # Apply template variable substitutions (user vars first, then defaults)
            if template_vars:
                content = _apply_template_vars(content, template_vars)
            content = _fill_template_defaults(content, template_name, extends_type)
        else:
            content = "extends Node\n\n\nfunc _ready() -> void:\n\tpass\n"

        if not dry_run:
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(content, encoding="utf-8")
        created_files.append(script_name)

    # --- 2. Build scene ---
    scene = Scene()

    # Process sub-resources (with user-defined alias IDs)
    resource_map: dict[str, str] = {}  # alias -> actual SubResource id
    for res_def in data.get("resources", []):
        alias = res_def.get("id", "")
        res_type = res_def.get("type", "")
        props = res_def.get("properties", {})
        sub_res = scene.add_sub_resource(res_type, props)
        if alias:
            resource_map[alias] = sub_res.id

    # Process node tree recursively
    root_def = data.get("root")
    if not root_def:
        _error("Missing 'root' in build description", as_json, ctx)
        return

    color_index = [0]  # mutable counter for auto-visual colors

    def _add_node(node_def: dict, parent: str | None) -> None:
        name = node_def.get("name", "Node")
        node_type = node_def.get("type", "") or _infer_type(node_def)
        # Convert all property values to strings first (JSON may have int/float/bool)
        raw_props = node_def.get("properties", {})
        props = {}
        for k, v in raw_props.items():
            if isinstance(v, bool):
                props[k] = "true" if v else "false"
            elif isinstance(v, (int, float)):
                props[k] = str(v)
            else:
                props[k] = auto_quote_value(str(v))
        instance_scene = node_def.get("instance")
        node_groups = list(node_def.get("groups", []))

        # Handle "text" shorthand for Label/Button/RichTextLabel
        text_val = node_def.get("text")
        if text_val is not None:
            props["text"] = auto_quote_value(str(text_val))

        # Handle "color" shorthand
        color_val = node_def.get("color")
        if color_val is not None:
            color_str = str(color_val)
            # If it's already a Godot Color(), use as-is; otherwise wrap it
            if not color_str.startswith("Color"):
                color_str = auto_quote_value(color_str)
            if node_type in ("Polygon2D", "ColorRect"):
                props["color"] = color_str
            else:
                props["modulate"] = color_str

        # Handle "size" shorthand for Control-derived nodes
        size_val = node_def.get("size")
        if size_val is not None:
            if isinstance(size_val, list) and len(size_val) == 2:
                props["custom_minimum_size"] = f"Vector2({size_val[0]}, {size_val[1]})"
            elif isinstance(size_val, str):
                props["custom_minimum_size"] = size_val

        # Handle collision_layer / collision_mask shorthands
        col_layer = node_def.get("collision_layer")
        if col_layer is not None:
            props["collision_layer"] = str(_collision_layers_to_int(col_layer))
        col_mask = node_def.get("collision_mask")
        if col_mask is not None:
            props["collision_mask"] = str(_collision_layers_to_int(col_mask))

        # Handle script shorthand
        script = node_def.get("script")
        if script:
            if not script.startswith("res://"):
                script = f"res://{script}"
            ext_res = scene.add_ext_resource("Script", script)
            props["script"] = f'ExtResource("{ext_res.id}")'

        # Handle shape shorthand
        shape_ref = node_def.get("shape")
        shape_sub_id = None
        if shape_ref:
            if shape_ref in resource_map:
                shape_sub_id = resource_map[shape_ref]
            elif ":" in shape_ref:
                shape_type, shape_params = shape_ref.split(":", 1)
                shape_props = _parse_inline_shape(shape_type, shape_params)
                sub = scene.add_sub_resource(shape_type, shape_props)
                resource_map[shape_ref] = sub.id
                shape_sub_id = sub.id
            else:
                shape_sub_id = shape_ref

            # For body types, DON'T set shape on the node itself —
            # create a CollisionShape2D/3D child instead
            if node_type in BODY_TYPES:
                pass  # Will add child after creating this node
            else:
                props["shape"] = f'SubResource("{shape_sub_id}")'

        # Handle texture shorthand
        texture = node_def.get("texture")
        if texture:
            if not texture.startswith("res://"):
                texture = f"res://{texture}"
            ext_res = scene.add_ext_resource("Texture2D", texture)
            props["texture"] = f'ExtResource("{ext_res.id}")'

        # Handle audio shorthand (for AudioStreamPlayer nodes)
        audio = node_def.get("audio")
        if audio:
            if not audio.startswith("res://"):
                audio = f"res://{audio}"
            ext_res = scene.add_ext_resource("AudioStream", audio)
            props["stream"] = f'ExtResource("{ext_res.id}")'

        # Handle font shorthand (for Label/Button nodes)
        font = node_def.get("font")
        if font:
            if not font.startswith("res://"):
                font = f"res://{font}"
            ext_res = scene.add_ext_resource("FontFile", font)
            props["theme_override_fonts/font"] = f'ExtResource("{ext_res.id}")'

        # Handle instance
        if instance_scene:
            if not instance_scene.startswith("res://"):
                instance_scene = f"res://{instance_scene}"
            ext_res = scene.add_ext_resource("PackedScene", instance_scene)
            node = scene.add_node(name, "", parent=parent, properties=props, groups=node_groups)
            node.instance_id = ext_res.id
        else:
            scene.add_node(name, node_type, parent=parent, properties=props, groups=node_groups)

        # If shape was used on a body type, create CollisionShape child
        if shape_sub_id and node_type in BODY_TYPES:
            col_type = "CollisionShape3D" if node_type in BODY_TYPES_3D else "CollisionShape2D"
            if parent is None:
                col_parent = "."
            elif parent == ".":
                col_parent = name
            else:
                col_parent = f"{parent}/{name}"
            scene.add_node(
                f"{name}Collision", col_type, parent=col_parent,
                properties={"shape": f'SubResource("{shape_sub_id}")'},
            )

        # Determine child parent path for recursion and auto-visual
        if parent is None:
            child_parent = "."
        elif parent == ".":
            child_parent = name
        else:
            child_parent = f"{parent}/{name}"

        # Recurse children
        children = node_def.get("children", [])
        if children:
            for child_def in children:
                _add_node(child_def, child_parent)

        # Auto-visual: if body type has no visual children, auto-create placeholder
        if node_type in BODY_TYPES and not instance_scene:
            _has_visual = _def_has_visual_child(node_def)
            if not _has_visual:
                c = _PLACEHOLDER_COLORS[color_index[0] % len(_PLACEHOLDER_COLORS)]
                color_index[0] += 1
                # Determine placeholder size from shape if available
                w, h = _DEFAULT_PLACEHOLDER_SIZE
                if shape_ref and ":" in str(shape_ref):
                    w, h = _extract_shape_size(str(shape_ref))
                is_3d = node_type in BODY_TYPES_3D
                if is_3d:
                    scene.add_node(
                        f"{name}Visual", "MeshInstance3D", parent=child_parent,
                    )
                else:
                    poly = f"PackedVector2Array(-{w}, -{h}, {w}, -{h}, {w}, {h}, -{w}, {h})"
                    scene.add_node(
                        f"{name}Visual", "Polygon2D", parent=child_parent,
                        properties={"color": c, "polygon": poly},
                    )
                auto_visuals.append(name)

    auto_visuals: list[str] = []  # track which nodes got auto-visual placeholders
    _add_node(root_def, None)

    # Process connections
    for conn_def in data.get("connections", []):
        scene.connections.append(Connection(
            signal_name=conn_def.get("signal", ""),
            from_node=conn_def.get("from", ""),
            to_node=conn_def.get("to", "."),
            method=conn_def.get("method", ""),
        ))

    # Write scene file
    scene_path = project_path / scene_name
    if not dry_run:
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(write_tscn(scene), encoding="utf-8")
    created_files.append(scene_name)

    # Optional engine-native validation
    validation = None
    if validate and not dry_run:
        from playgen.godot.bridge import validate_scene as _validate_scene
        val_result = _validate_scene(project_path, scene_name)
        validation = val_result.to_dict()
        if not val_result.success:
            errors.append(f"Engine validation failed: {val_result.error}")

    # Auto-check visibility (always, not optional — this is the #1 Agent failure mode)
    from playgen.godot.visibility import check_visibility
    vis_report = check_visibility(scene, scene_name, project_path)

    # Output
    result = {
        "scene": scene_name,
        "created_files": created_files,
        "node_count": len(scene.nodes),
        "sub_resources": len(scene.sub_resources),
        "ext_resources": len(scene.ext_resources),
        "connections": len(scene.connections),
        "dry_run": dry_run,
    }
    if auto_visuals:
        result["auto_visuals"] = auto_visuals
    if vis_report.has_issues:
        result["visibility_warnings"] = [w.to_dict() for w in vis_report.warnings]
    if snap_name:
        result["snapshot"] = snap_name
    if validation is not None:
        result["validation"] = validation
    if errors:
        result["errors"] = errors

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if dry_run:
            click.echo("[dry-run] Would create:")
        else:
            click.echo("Built scene successfully:")
        click.echo(f"  Scene: {scene_name}")
        click.echo(f"  Nodes: {len(scene.nodes)}")
        click.echo(f"  SubResources: {len(scene.sub_resources)}")
        click.echo(f"  ExtResources: {len(scene.ext_resources)}")
        click.echo(f"  Connections: {len(scene.connections)}")
        if created_files:
            click.echo(f"  Files ({len(created_files)}):")
            for f in created_files:
                click.echo(f"    {project_path / f}")
        if auto_visuals:
            click.echo(f"  Auto-visual placeholders ({len(auto_visuals)}):")
            for av in auto_visuals:
                click.echo(f"    {av} — Polygon2D placeholder added (replace with Sprite2D + texture)")
        if vis_report.has_issues:
            click.echo(f"  Visibility warnings:")
            for w in vis_report.warnings:
                icon = "!!" if w.severity == "warning" else "??"
                click.echo(f"    [{icon}] {w.node_name} ({w.node_type}) — {w.message}")
        if errors:
            for e in errors:
                click.echo(f"  Warning: {e}", err=True)


def _configure_project(data: dict, project_path: Path, errors: list[str], dry_run: bool) -> None:
    """Apply autoloads, config, and input_map to project.godot."""
    autoloads = data.get("autoloads", {})
    config = data.get("config", {})
    input_map = data.get("input_map", {})

    if not autoloads and not config and not input_map:
        return

    try:
        proj = load_project(project_path)
    except FileNotFoundError:
        errors.append("project.godot not found, skipping project config")
        return

    for name, script in autoloads.items():
        if not script.startswith("res://"):
            script = f"res://{script}"
        proj.set("autoload", name, f'"*{script}"')

    for key, value in config.items():
        parts = key.split("/", 1)
        if len(parts) == 2:
            from playgen.commands.config_cmd import _auto_quote_config_value
            proj.set(parts[0], parts[1], _auto_quote_config_value(str(value)))

    if input_map:
        from playgen.commands.input_cmd import format_input_value
        for action, keys in input_map.items():
            if isinstance(keys, list):
                proj.set("input", action, format_input_value(keys))
            elif isinstance(keys, str):
                proj.set("input", action, format_input_value([keys]))

    if not dry_run:
        save_project(proj, project_path)


def _def_has_visual_child(node_def: dict) -> bool:
    """Check if a node definition has any visual child in its JSON tree."""
    from playgen.godot.visibility import VISUAL_TYPES
    for child in node_def.get("children", []):
        child_type = child.get("type", "")
        if child_type in VISUAL_TYPES:
            return True
        if child.get("instance"):
            return True  # Instances may contain visuals
        if _def_has_visual_child(child):
            return True
    return False


def _extract_shape_size(shape_ref: str) -> tuple[int, int]:
    """Extract half-size from inline shape for auto-visual polygon sizing."""
    if ":" not in shape_ref:
        return _DEFAULT_PLACEHOLDER_SIZE
    shape_type, params = shape_ref.split(":", 1)
    parts = [p.strip() for p in params.split(",")]
    try:
        if shape_type == "RectangleShape2D" and len(parts) == 2:
            return int(float(parts[0]) / 2), int(float(parts[1]) / 2)
        elif shape_type == "CircleShape2D" and len(parts) == 1:
            r = int(float(parts[0]))
            return r, r
        elif shape_type == "CapsuleShape2D" and len(parts) == 2:
            return int(float(parts[0])), int(float(parts[1]) / 2)
    except (ValueError, IndexError):
        pass
    return _DEFAULT_PLACEHOLDER_SIZE


def _parse_inline_shape(shape_type: str, params: str) -> dict[str, str]:
    """Parse inline shape definition like 'RectangleShape2D:30,50'."""
    parts = [p.strip() for p in params.split(",")]
    if shape_type == "RectangleShape2D" and len(parts) == 2:
        return {"size": f"Vector2({parts[0]}, {parts[1]})"}
    elif shape_type == "CircleShape2D" and len(parts) == 1:
        return {"radius": parts[0]}
    elif shape_type == "CapsuleShape2D" and len(parts) == 2:
        return {"radius": parts[0], "height": parts[1]}
    elif shape_type == "WorldBoundaryShape2D":
        return {}
    else:
        return {"size": f"Vector2({', '.join(parts)})"}


def _error(msg: str, as_json: bool, ctx: click.Context) -> None:
    if as_json:
        click.echo(json.dumps({"error": msg}))
    else:
        # Output to both stdout (for Agent capture) and stderr (for humans)
        click.echo(f"Error: {msg}")
        click.echo(f"Error: {msg}", err=True)
    ctx.exit(1)
