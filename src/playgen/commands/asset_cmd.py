"""playgen asset - Import, manage, and attach assets to scenes.

Solves the Agent's key bottleneck: getting images, audio, fonts, and other
resources into a Godot project and wired up to scene nodes — without manual
editor interaction.

Supports: images (png, jpg, svg, webp), audio (wav, ogg, mp3),
fonts (ttf, otf), and generic resources.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import click

from playgen.godot.tscn import parse_tscn, write_tscn, auto_quote_value


# Maps file extensions to Godot resource types and typical node types
ASSET_TYPES: dict[str, dict[str, str]] = {
    # Images
    ".png": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    ".jpg": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    ".jpeg": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    ".svg": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    ".webp": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    ".bmp": {"resource_type": "Texture2D", "node_type": "Sprite2D", "property": "texture"},
    # Audio
    ".wav": {"resource_type": "AudioStream", "node_type": "AudioStreamPlayer", "property": "stream"},
    ".ogg": {"resource_type": "AudioStream", "node_type": "AudioStreamPlayer", "property": "stream"},
    ".mp3": {"resource_type": "AudioStream", "node_type": "AudioStreamPlayer", "property": "stream"},
    # Fonts
    ".ttf": {"resource_type": "FontFile", "node_type": "Label", "property": "theme_override_fonts/font"},
    ".otf": {"resource_type": "FontFile", "node_type": "Label", "property": "theme_override_fonts/font"},
    ".woff": {"resource_type": "FontFile", "node_type": "Label", "property": "theme_override_fonts/font"},
    ".woff2": {"resource_type": "FontFile", "node_type": "Label", "property": "theme_override_fonts/font"},
    # Scenes (for instancing)
    ".tscn": {"resource_type": "PackedScene", "node_type": "", "property": ""},
}

# Known Godot node types that accept specific asset properties
NODE_ASSET_PROPERTIES: dict[str, dict[str, str]] = {
    # Texture-accepting nodes
    "Sprite2D": {"texture_type": "Texture2D", "property": "texture"},
    "Sprite3D": {"texture_type": "Texture2D", "property": "texture"},
    "TextureRect": {"texture_type": "Texture2D", "property": "texture"},
    "TextureButton": {"texture_type": "Texture2D", "property": "texture_normal"},
    "AnimatedSprite2D": {"texture_type": "SpriteFrames", "property": "sprite_frames"},
    "MeshInstance3D": {"texture_type": "Texture2D", "property": ""},
    # Audio-accepting nodes
    "AudioStreamPlayer": {"texture_type": "AudioStream", "property": "stream"},
    "AudioStreamPlayer2D": {"texture_type": "AudioStream", "property": "stream"},
    "AudioStreamPlayer3D": {"texture_type": "AudioStream", "property": "stream"},
    # Font-accepting nodes (via theme overrides)
    "Label": {"texture_type": "FontFile", "property": "theme_override_fonts/font"},
    "RichTextLabel": {"texture_type": "FontFile", "property": "theme_override_fonts/normal_font"},
    "Button": {"texture_type": "FontFile", "property": "theme_override_fonts/font"},
    "LineEdit": {"texture_type": "FontFile", "property": "theme_override_fonts/font"},
}


@click.group("asset")
def asset_cmd() -> None:
    """Manage project assets (images, audio, fonts).

    Import external files into the project, list available assets,
    and attach them to scene nodes.

    \b
    Workflow:
      playgen asset import player.png              # Copy into project
      playgen asset import --dest sprites/ bg.png  # Copy to subfolder
      playgen asset attach main.tscn Player player.png  # Wire to node
      playgen asset list                           # See all assets
    """


@asset_cmd.command("import")
@click.argument("files", nargs=-1, required=True)
@click.option("--dest", "-d", default="", help="Destination subfolder within project (e.g., 'sprites', 'audio')")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def asset_import(ctx: click.Context, files: tuple[str, ...], dest: str, as_json: bool) -> None:
    """Import asset files into the Godot project.

    Copies files into the project directory, placing them where Godot's
    import system can find them. Supports images, audio, fonts, and scenes.

    \b
    Examples:
      playgen asset import player.png enemy.png
      playgen asset import --dest audio/ bgm.ogg sfx_jump.wav
      playgen asset import --dest fonts/ custom_font.ttf
    """
    project_path: Path = ctx.obj["project_path"]
    imported: list[dict[str, str]] = []
    errors: list[str] = []

    for file_arg in files:
        src = Path(file_arg)
        if not src.is_absolute():
            # Try relative to cwd first, then project
            if not src.exists():
                src_in_proj = project_path / file_arg
                if src_in_proj.exists():
                    # Already in project
                    ext = src.suffix.lower()
                    asset_info = ASSET_TYPES.get(ext, {})
                    imported.append({
                        "file": file_arg,
                        "res_path": f"res://{file_arg}",
                        "resource_type": asset_info.get("resource_type", "Resource"),
                        "status": "already_in_project",
                    })
                    continue
                errors.append(f"File not found: {file_arg}")
                continue

        if not src.exists():
            errors.append(f"File not found: {file_arg}")
            continue

        ext = src.suffix.lower()
        if ext not in ASSET_TYPES:
            errors.append(f"Unsupported file type: {ext} ({src.name})")
            continue

        # Determine destination path
        if dest:
            dest_dir = project_path / dest
        else:
            # Auto-organize by type
            asset_info = ASSET_TYPES[ext]
            res_type = asset_info["resource_type"]
            if res_type == "Texture2D":
                dest_dir = project_path
            elif res_type == "AudioStream":
                dest_dir = project_path
            elif res_type == "FontFile":
                dest_dir = project_path
            else:
                dest_dir = project_path

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / src.name

        # Copy file
        shutil.copy2(str(src), str(dest_file))

        # Calculate res:// path
        rel = dest_file.relative_to(project_path)
        res_path = f"res://{rel.as_posix()}"

        asset_info = ASSET_TYPES.get(ext, {})
        imported.append({
            "file": src.name,
            "res_path": res_path,
            "resource_type": asset_info.get("resource_type", "Resource"),
            "suggested_node": asset_info.get("node_type", ""),
            "status": "imported",
        })

    result = {"imported": imported, "errors": errors}

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        for item in imported:
            status = item["status"]
            if status == "already_in_project":
                click.echo(f"  Already in project: {item['res_path']}")
            else:
                click.echo(f"  Imported: {item['file']} -> {item['res_path']}")
                if item.get("suggested_node"):
                    click.echo(f"    Suggested node type: {item['suggested_node']}")
        for err in errors:
            click.echo(f"  Error: {err}", err=True)


@asset_cmd.command("attach")
@click.argument("scene")
@click.argument("node_name")
@click.argument("asset_path")
@click.option("--property", "-p", "prop", default=None, help="Override property name (auto-detected by default)")
@click.option("--create-node", is_flag=True, help="Create a new child node for the asset if node doesn't exist")
@click.option("--node-type", default=None, help="Node type when using --create-node (auto-detected by default)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def asset_attach(
    ctx: click.Context,
    scene: str,
    node_name: str,
    asset_path: str,
    prop: str | None,
    create_node: bool,
    node_type: str | None,
    as_json: bool,
) -> None:
    """Attach an asset to a node in a scene.

    Adds an ext_resource reference for the asset and sets the appropriate
    property on the target node. Auto-detects the correct property based
    on the node type and asset type.

    \b
    Examples:
      playgen asset attach main.tscn Player player.png
      playgen asset attach main.tscn BGM bgm.ogg
      playgen asset attach main.tscn Title custom_font.ttf
      playgen asset attach main.tscn BG bg.png --create-node --node-type TextureRect
    """
    project_path: Path = ctx.obj["project_path"]

    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"Scene not found: {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Normalize asset path
    if not asset_path.startswith("res://"):
        # Check if file exists in project
        asset_file = project_path / asset_path
        if not asset_file.exists():
            msg = f"Asset not found in project: {asset_path}. Run 'playgen asset import' first."
            if as_json:
                click.echo(json.dumps({"error": msg}))
            else:
                click.echo(f"Error: {msg}", err=True)
            ctx.exit(1)
            return
        res_path = f"res://{asset_path}"
    else:
        res_path = asset_path
        # Verify file exists
        rel_path = asset_path.replace("res://", "")
        if not (project_path / rel_path).exists():
            msg = f"Asset not found: {asset_path}"
            if as_json:
                click.echo(json.dumps({"error": msg}))
            else:
                click.echo(f"Error: {msg}", err=True)
            ctx.exit(1)
            return

    # Determine asset type from extension
    ext = Path(res_path).suffix.lower()
    asset_info = ASSET_TYPES.get(ext, {})
    resource_type = asset_info.get("resource_type", "Resource")

    # Parse scene
    content = scene_path.read_text(encoding="utf-8")
    scene_data = parse_tscn(content)

    # Find or create node
    target_node = scene_data.find_node(node_name)
    if target_node is None:
        if create_node:
            # Determine node type
            if node_type is None:
                node_type = asset_info.get("node_type", "Node2D")
            scene_data.add_node(node_name, node_type, parent=".")
            target_node = scene_data.find_node(node_name)
        else:
            msg = f"Node '{node_name}' not found in {scene}. Use --create-node to auto-create."
            if as_json:
                click.echo(json.dumps({"error": msg}))
            else:
                click.echo(f"Error: {msg}", err=True)
            ctx.exit(1)
            return

    # Determine property name
    if prop is None:
        # Auto-detect from node type
        if target_node.type in NODE_ASSET_PROPERTIES:
            prop = NODE_ASSET_PROPERTIES[target_node.type]["property"]
        else:
            # Fallback based on asset type
            prop = asset_info.get("property", "resource")

    if not prop:
        msg = f"Cannot determine property for node type '{target_node.type}'. Use --property to specify."
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Add ext_resource and set property
    ext_res = scene_data.add_ext_resource(resource_type, res_path)
    target_node.properties[prop] = f'ExtResource("{ext_res.id}")'

    # Write scene
    scene_path.write_text(write_tscn(scene_data), encoding="utf-8")

    result = {
        "scene": scene,
        "node": node_name,
        "asset": res_path,
        "property": prop,
        "resource_type": resource_type,
        "ext_resource_id": ext_res.id,
    }
    if create_node:
        result["created_node"] = True
        result["node_type"] = target_node.type

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Attached {res_path} to {node_name}.{prop} in {scene}")
        if create_node:
            click.echo(f"  Created node: {node_name} ({target_node.type})")


@asset_cmd.command("list")
@click.option("--type", "-t", "filter_type", default=None,
              type=click.Choice(["image", "audio", "font", "scene", "all"]),
              help="Filter by asset type")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def asset_list(ctx: click.Context, filter_type: str | None, as_json: bool) -> None:
    """List all importable assets in the project.

    Scans the project directory for recognized asset files and shows
    their paths, types, and suggested node types.
    """
    project_path: Path = ctx.obj["project_path"]

    type_filter_map: dict[str, set[str]] = {
        "image": {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp"},
        "audio": {".wav", ".ogg", ".mp3"},
        "font": {".ttf", ".otf", ".woff", ".woff2"},
        "scene": {".tscn"},
    }

    allowed_exts: set[str] | None = None
    if filter_type and filter_type != "all":
        allowed_exts = type_filter_map.get(filter_type, set())

    assets: list[dict[str, str]] = []
    for fpath in sorted(project_path.rglob("*")):
        if fpath.is_dir():
            continue
        # Skip .godot/ internal directory
        try:
            rel = fpath.relative_to(project_path)
        except ValueError:
            continue
        if str(rel).startswith(".godot") or str(rel).startswith(".playgen"):
            continue

        ext = fpath.suffix.lower()
        if ext not in ASSET_TYPES:
            continue
        if allowed_exts is not None and ext not in allowed_exts:
            continue

        asset_info = ASSET_TYPES[ext]
        assets.append({
            "file": str(rel.as_posix()),
            "res_path": f"res://{rel.as_posix()}",
            "resource_type": asset_info["resource_type"],
            "suggested_node": asset_info.get("node_type", ""),
        })

    if as_json:
        click.echo(json.dumps({"assets": assets, "count": len(assets)}, indent=2))
    else:
        if not assets:
            click.echo("No assets found in project.")
        else:
            click.echo(f"Assets ({len(assets)}):")
            for a in assets:
                click.echo(f"  {a['res_path']} ({a['resource_type']})")
