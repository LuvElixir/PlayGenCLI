"""playgen build - Build a complete scene from a JSON description.

This is the highest-leverage command for Agent-driven development.
Instead of 20+ sequential CLI calls, an Agent can output one JSON
description and get a complete, runnable scene with all resources,
scripts, nodes, and signal connections.

v0.5.0 enhancements:
- Auto-snapshot before build (--snapshot)
- Asset references in node definitions (auto ext_resource)
- Optional engine-native validation after build (--validate)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from playgen.godot.tscn import Scene, Connection, write_tscn, auto_quote_value, BODY_TYPES, BODY_TYPES_3D
from playgen.godot.project_file import load_project, save_project
from playgen.templates import SCRIPT_TEMPLATES, EXTENDS_DEFAULTS


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

            if content_raw:
                content = content_raw
            elif template_name and template_name in SCRIPT_TEMPLATES:
                content = SCRIPT_TEMPLATES[template_name]
            elif extends_type in EXTENDS_DEFAULTS:
                content = EXTENDS_DEFAULTS[extends_type]
            else:
                content = f"extends {extends_type}\n\n\nfunc _ready() -> void:\n\tpass\n\n\nfunc _process(delta: float) -> void:\n\tpass\n"
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

    def _add_node(node_def: dict, parent: str | None) -> None:
        name = node_def.get("name", "Node")
        node_type = node_def.get("type", "")
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

        # Recurse children
        children = node_def.get("children", [])
        if children:
            if parent is None:
                child_parent = "."
            elif parent == ".":
                child_parent = name
            else:
                child_parent = f"{parent}/{name}"
            for child_def in children:
                _add_node(child_def, child_parent)

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
