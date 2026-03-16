"""playgen scene - Scene operations (create, tree, list)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.tscn import Scene, parse_tscn, write_tscn


@click.group("scene")
def scene_cmd() -> None:
    """Scene operations: create, inspect, and list scenes."""
    pass


@scene_cmd.command("create")
@click.argument("name")
@click.option("--root-type", "-r", default="Node2D", help="Root node type (default: Node2D)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def scene_create(ctx: click.Context, name: str, root_type: str, as_json: bool) -> None:
    """Create a new scene file.

    NAME is the scene filename (e.g., 'enemy.tscn' or 'enemy').
    """
    project_path: Path = ctx.obj["project_path"]

    if not name.endswith(".tscn"):
        name += ".tscn"

    scene_path = project_path / name
    if scene_path.exists():
        if as_json:
            click.echo(json.dumps({"error": f"{name} already exists"}))
        else:
            click.echo(f"Error: {name} already exists", err=True)
        ctx.exit(1)
        return

    scene = Scene()
    scene.add_node(name.replace(".tscn", "").title().replace("_", ""), root_type)

    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(write_tscn(scene), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"created": name, "root_type": root_type}))
    else:
        click.echo(f"Created scene: {name} (root: {root_type})")


@scene_cmd.command("tree")
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def scene_tree(ctx: click.Context, name: str, as_json: bool) -> None:
    """Show the node tree of a scene.

    NAME is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]

    if not name.endswith(".tscn"):
        name += ".tscn"

    scene_path = project_path / name
    if not scene_path.exists():
        if as_json:
            click.echo(json.dumps({"error": f"{name} not found"}))
        else:
            click.echo(f"Error: {name} not found", err=True)
        ctx.exit(1)
        return

    scene = parse_tscn(scene_path.read_text(encoding="utf-8"))

    if as_json:
        click.echo(json.dumps(scene.to_dict(), indent=2))
    else:
        _print_tree(scene)


def _print_tree(scene: Scene, indent: str = "") -> None:
    """Pretty-print the scene tree."""
    root = scene.get_root()
    if not root:
        click.echo("(empty scene)")
        return

    def _print_node(node, prefix: str, is_last: bool) -> None:
        connector = "+-" if is_last else "|-"
        tags = []
        if "script" in node.properties:
            tags.append("script")
        if node.groups:
            tags.append(f"groups: {', '.join(node.groups)}")
        tag_str = f" [{'; '.join(tags)}]" if tags else ""
        click.echo(f"{prefix}{connector} {node.name} ({node.type}){tag_str}")

        # Find children
        node_path = scene.get_node_path(node)
        children = []
        for n in scene.nodes:
            if n.parent is None:
                continue
            expected_parent = "." if node.parent is None else node_path
            if n.parent == expected_parent:
                children.append(n)

        child_prefix = prefix + ("   " if is_last else "|  ")
        for i, child in enumerate(children):
            _print_node(child, child_prefix, i == len(children) - 1)

    # Print root
    tags = []
    if "script" in root.properties:
        tags.append("script")
    if root.groups:
        tags.append(f"groups: {', '.join(root.groups)}")
    tag_str = f" [{'; '.join(tags)}]" if tags else ""
    click.echo(f"{root.name} ({root.type}){tag_str}")

    # Find root's children (parent=".")
    children = [n for n in scene.nodes if n.parent == "."]
    for i, child in enumerate(children):
        _print_node(child, "", i == len(children) - 1)


@scene_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def scene_list(ctx: click.Context, as_json: bool) -> None:
    """List all scenes in the project."""
    project_path: Path = ctx.obj["project_path"]

    scenes = sorted(project_path.rglob("*.tscn"))
    # Exclude .godot directory
    scenes = [s for s in scenes if ".godot" not in s.parts]

    if as_json:
        result = []
        for s in scenes:
            rel = s.relative_to(project_path)
            scene = parse_tscn(s.read_text(encoding="utf-8"))
            root = scene.get_root()
            result.append({
                "path": str(rel).replace("\\", "/"),
                "res_path": f"res://{str(rel).replace(chr(92), '/')}",
                "root_type": root.type if root else "",
                "node_count": len(scene.nodes),
            })
        click.echo(json.dumps(result, indent=2))
    else:
        if not scenes:
            click.echo("No scenes found.")
            return
        for s in scenes:
            rel = s.relative_to(project_path)
            scene = parse_tscn(s.read_text(encoding="utf-8"))
            root = scene.get_root()
            root_info = f"({root.type})" if root else ""
            click.echo(f"  {str(rel).replace(chr(92), '/'):30s} {root_info:20s} {len(scene.nodes)} nodes")
