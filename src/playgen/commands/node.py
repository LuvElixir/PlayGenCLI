"""playgen node - Node operations within scenes."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.tscn import parse_tscn, write_tscn, auto_quote_value, BODY_TYPES, BODY_TYPES_3D


def _load_scene(ctx: click.Context, scene: str, as_json: bool):
    """Load a scene file. Returns (scene_obj, scene_path, scene_name) or exits."""
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"
    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return None, None, None
    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))
    return scene_obj, scene_path, scene


@click.group("node")
def node_cmd() -> None:
    """Node operations: add, remove, set, copy, and list nodes in scenes."""
    pass


@node_cmd.command("add")
@click.argument("scene")
@click.option("--name", "-n", required=True, help="Node name")
@click.option("--type", "-t", "node_type", default="", help="Node type (e.g., Sprite2D, CharacterBody2D)")
@click.option("--parent", "-p", default=".", help="Parent node path (default: '.' for root's child)")
@click.option("--property", "-P", "properties", multiple=True, help="Node property as key=value (repeatable)")
@click.option("--script", "-s", "script_path", default=None, help="Attach script (auto-handles ext_resource)")
@click.option("--shape", default=None, help="Add collision shape: TYPE:W,H (e.g., RectangleShape2D:28,44 or CircleShape2D:30)")
@click.option("--instance", "instance_scene", default=None, help="Instance a sub-scene (e.g., coin.tscn)")
@click.option("--group", "-g", "groups", multiple=True, help="Add node to group (repeatable)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def node_add(
    ctx: click.Context,
    scene: str,
    name: str,
    node_type: str,
    parent: str,
    properties: tuple[str, ...],
    script_path: str | None,
    shape: str | None,
    instance_scene: str | None,
    groups: tuple[str, ...],
    as_json: bool,
) -> None:
    """Add a node to a scene.

    SCENE is the scene filename (e.g., 'main.tscn').

    \b
    Examples:
      playgen node add main -n Player -t CharacterBody2D --script player.gd
      playgen node add main -n Col -t CollisionShape2D -p Player --shape RectangleShape2D:28,44
      playgen node add main -n Coin1 --instance coin.tscn -P position=Vector2(300,400)
    """
    scene_obj, scene_path, scene = _load_scene(ctx, scene, as_json)
    if scene_obj is None:
        return

    if scene_obj.find_node(name):
        msg = f"Node '{name}' already exists in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Parse -P properties with auto-quoting
    props: dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(f"Error: Invalid property format '{prop}', expected key=value", err=True)
            ctx.exit(1)
            return
        k, v = prop.split("=", 1)
        props[k.strip()] = auto_quote_value(v.strip())

    # Handle --script: auto-create ext_resource and set property
    if script_path:
        if not script_path.startswith("res://"):
            res_path = f"res://{script_path}"
        else:
            res_path = script_path
        ext_res = scene_obj.add_ext_resource("Script", res_path)
        props["script"] = f'ExtResource("{ext_res.id}")'

    node_groups = list(groups)

    # Handle --shape: auto-create SubResource
    # For body types (Area2D, CharacterBody2D, etc.), create a CollisionShape2D child
    # For CollisionShape2D itself, set shape directly
    shape_sub_res = None
    if shape:
        if ":" in shape:
            shape_type, shape_params = shape.split(":", 1)
            shape_props = _parse_shape(shape_type, shape_params)
        else:
            shape_type = shape
            shape_props = {}
        shape_sub_res = scene_obj.add_sub_resource(shape_type, shape_props)

        if node_type in BODY_TYPES:
            pass  # Will create CollisionShape2D child after adding the node
        else:
            # CollisionShape2D or unknown: set shape directly
            props["shape"] = f'SubResource("{shape_sub_res.id}")'

    # Handle --instance: instance a sub-scene
    if instance_scene:
        if not instance_scene.startswith("res://"):
            instance_scene = f"res://{instance_scene}"
        ext_res = scene_obj.add_ext_resource("PackedScene", instance_scene)
        node = scene_obj.add_node(name, "", parent=parent, properties=props, groups=node_groups)
        node.instance_id = ext_res.id
    else:
        if not node_type and not instance_scene:
            click.echo("Error: --type or --instance is required", err=True)
            ctx.exit(1)
            return
        scene_obj.add_node(name, node_type, parent=parent, properties=props, groups=node_groups)

    # If --shape was used on a body type, create CollisionShape2D child
    if shape_sub_res and node_type in BODY_TYPES:
        col_type = "CollisionShape3D" if node_type in BODY_TYPES_3D else "CollisionShape2D"
        col_parent = name if parent == "." else f"{parent}/{name}"
        scene_obj.add_node(
            f"{name}Collision", col_type, parent=col_parent,
            properties={"shape": f'SubResource("{shape_sub_res.id}")'},
        )

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"added": name, "type": node_type, "parent": parent, "scene": scene}))
    else:
        extras = []
        if script_path:
            extras.append(f"script={script_path}")
        if shape:
            extras.append(f"shape={shape}")
        if instance_scene:
            extras.append(f"instance={instance_scene}")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        click.echo(f"Added node: {name} ({node_type or 'instance'}) -> parent: {parent}{extra_str}")


def _parse_shape(shape_type: str, params: str) -> dict[str, str]:
    parts = [p.strip() for p in params.split(",")]
    if shape_type == "RectangleShape2D" and len(parts) == 2:
        return {"size": f"Vector2({parts[0]}, {parts[1]})"}
    elif shape_type == "CircleShape2D" and len(parts) >= 1:
        return {"radius": f"{parts[0]}.0" if "." not in parts[0] else parts[0]}
    elif shape_type == "CapsuleShape2D" and len(parts) == 2:
        return {"radius": f"{parts[0]}.0" if "." not in parts[0] else parts[0],
                "height": f"{parts[1]}.0" if "." not in parts[1] else parts[1]}
    return {}


@node_cmd.command("set")
@click.argument("scene")
@click.option("--name", "-n", required=True, help="Node name to modify")
@click.option("--property", "-P", "properties", multiple=True, help="Property as key=value (repeatable)")
@click.option("--group", "-g", "groups", multiple=True, help="Add node to group (repeatable)")
@click.option("--script", "-s", "script_path", default=None, help="Attach or change script")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def node_set(ctx: click.Context, scene: str, name: str, properties: tuple[str, ...],
             groups: tuple[str, ...], script_path: str | None, as_json: bool) -> None:
    """Set properties on an existing node (can add new properties too).

    SCENE is the scene filename (e.g., 'main.tscn').

    \b
    Examples:
      playgen node set main -n Player -P position=Vector2(100,200)
      playgen node set main -n Sprite -P "color=Color(1,0,0,1)" -P "visible=false"
      playgen node set main -n Key -g keys -g collectibles
      playgen node set main -n Player --script new_player.gd
    """
    if not properties and not groups and not script_path:
        click.echo("Error: provide --property, --group, or --script", err=True)
        ctx.exit(1)
        return

    scene_obj, scene_path, scene = _load_scene(ctx, scene, as_json)
    if scene_obj is None:
        return

    target = scene_obj.find_node(name)
    if not target:
        msg = f"Node '{name}' not found in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    changed: list[str] = []
    for prop in properties:
        if "=" not in prop:
            click.echo(f"Error: Invalid property format '{prop}', expected key=value", err=True)
            ctx.exit(1)
            return
        k, v = prop.split("=", 1)
        k, v = k.strip(), v.strip()
        target.properties[k] = auto_quote_value(v)
        changed.append(k)

    if script_path:
        if not script_path.startswith("res://"):
            res_path = f"res://{script_path}"
        else:
            res_path = script_path
        ext_res = scene_obj.add_ext_resource("Script", res_path)
        target.properties["script"] = f'ExtResource("{ext_res.id}")'
        changed.append(f"script={script_path}")

    if groups:
        for g in groups:
            if g not in target.groups:
                target.groups.append(g)
        changed.append(f"groups+=[{', '.join(groups)}]")

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"node": name, "updated": changed, "scene": scene}))
    else:
        click.echo(f"Updated {name}: {', '.join(changed)}")


@node_cmd.command("remove")
@click.argument("scene")
@click.option("--name", "-n", required=True, help="Node name to remove")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def node_remove(ctx: click.Context, scene: str, name: str, as_json: bool) -> None:
    """Remove a node from a scene (and all its children).

    SCENE is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))
    target = scene_obj.find_node(name)
    if not target:
        msg = f"Node '{name}' not found in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Collect node and all descendants
    target_path = scene_obj.get_node_path(target)
    to_remove = {name}

    def _collect_children(path: str) -> None:
        for n in scene_obj.nodes:
            if n.parent == path or (n.parent and n.parent == f"./{path}"):
                to_remove.add(n.name)
                child_path = f"{path}/{n.name}" if path != "." else n.name
                _collect_children(child_path)

    parent_ref = "." if target.parent is None else target_path
    _collect_children(parent_ref)

    scene_obj.nodes = [n for n in scene_obj.nodes if n.name not in to_remove]
    scene_obj.connections = [
        c for c in scene_obj.connections
        if c.from_node not in to_remove and c.to_node not in to_remove
    ]

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"removed": sorted(to_remove), "scene": scene}))
    else:
        click.echo(f"Removed {len(to_remove)} node(s): {', '.join(sorted(to_remove))}")


@node_cmd.command("copy")
@click.argument("scene")
@click.option("--name", "-n", required=True, help="Source node name")
@click.option("--to", "new_name", required=True, help="New node name")
@click.option("--parent", "-p", default=None, help="New parent (default: same as source)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def node_copy(ctx: click.Context, scene: str, name: str, new_name: str,
              parent: str | None, as_json: bool) -> None:
    """Copy a node (and its children) within the scene.

    SCENE is the scene filename (e.g., 'main.tscn').

    \b
    Examples:
      playgen node copy main -n Platform1 --to Platform4
      playgen node copy main -n Coin --to Coin2 -p Level2
    """
    scene_obj, scene_path, scene = _load_scene(ctx, scene, as_json)
    if scene_obj is None:
        return

    source = scene_obj.find_node(name)
    if not source:
        msg = f"Node '{name}' not found in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    if scene_obj.find_node(new_name):
        msg = f"Node '{new_name}' already exists in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    new_parent = parent if parent is not None else source.parent
    copied = [new_name]

    # Copy the node itself
    scene_obj.add_node(
        new_name, source.type, parent=new_parent,
        properties=dict(source.properties),
        groups=list(source.groups),
    )
    if source.instance_id:
        scene_obj.find_node(new_name).instance_id = source.instance_id

    # Copy children recursively
    source_path = scene_obj.get_node_path(source)

    def _copy_children(src_parent: str, dst_parent: str) -> None:
        for n in list(scene_obj.nodes):
            if n.parent == src_parent:
                child_new_name = n.name
                # Avoid duplicate names by prefixing if needed
                if scene_obj.find_node(child_new_name) and child_new_name not in copied:
                    child_new_name = f"{new_name}_{n.name}"
                scene_obj.add_node(
                    child_new_name, n.type, parent=dst_parent,
                    properties=dict(n.properties),
                    groups=list(n.groups),
                )
                if n.instance_id:
                    scene_obj.find_node(child_new_name).instance_id = n.instance_id
                copied.append(child_new_name)
                # Recurse
                old_child_path = f"{src_parent}/{n.name}"
                new_child_path = f"{dst_parent}/{child_new_name}"
                _copy_children(old_child_path, new_child_path)

    if source.parent is None:
        src_ref = "."
    elif source.parent == ".":
        src_ref = name
    else:
        src_ref = f"{source.parent}/{name}"

    if new_parent is None:
        dst_ref = "."
    elif new_parent == ".":
        dst_ref = new_name
    else:
        dst_ref = f"{new_parent}/{new_name}"

    _copy_children(src_ref, dst_ref)

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"copied": name, "to": new_name, "nodes": copied, "scene": scene}))
    else:
        click.echo(f"Copied {name} -> {new_name} ({len(copied)} node(s))")


@node_cmd.command("list")
@click.argument("scene")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def node_list(ctx: click.Context, scene: str, as_json: bool) -> None:
    """List all nodes in a scene.

    SCENE is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))

    if as_json:
        nodes = []
        for n in scene_obj.nodes:
            nd: dict = {"name": n.name, "type": n.type}
            if n.parent is not None:
                nd["parent"] = n.parent
            if n.groups:
                nd["groups"] = n.groups
            if n.properties:
                nd["properties"] = n.properties
            nodes.append(nd)
        click.echo(json.dumps(nodes, indent=2))
    else:
        for n in scene_obj.nodes:
            parent_info = f"parent={n.parent}" if n.parent is not None else "(root)"
            groups_info = f" groups={n.groups}" if n.groups else ""
            click.echo(f"  {n.name:25s} {n.type:25s} {parent_info}{groups_info}")
