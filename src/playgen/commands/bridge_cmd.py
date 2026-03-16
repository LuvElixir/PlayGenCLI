"""playgen bridge - Engine-native operations via Godot headless mode.

Provides access to Godot engine capabilities that cannot be reliably
achieved through text-file manipulation alone:

- Scene validation (does Godot actually accept this scene?)
- Scene tree reading (what does Godot see after instancing?)
- Resource validation (can Godot load these resources?)
- Script validation (does this GDScript parse correctly?)
- Class introspection (what properties does this node type have?)
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.bridge import (
    validate_scene,
    read_scene_tree,
    validate_resources,
    validate_script,
    read_project_info,
    get_class_properties,
    list_node_types,
)


@click.group("bridge")
def bridge_cmd() -> None:
    """Engine-native operations via Godot headless mode.

    Uses the actual Godot engine to validate, inspect, and query
    project state. More authoritative than text-only parsing.

    Requires Godot 4.x to be available (GODOT_PATH or in PATH).

    \b
    Examples:
      playgen bridge validate-scene main.tscn
      playgen bridge read-tree main.tscn
      playgen bridge validate-script player.gd
      playgen bridge class-props CharacterBody2D
    """


@bridge_cmd.command("validate-scene")
@click.argument("scene")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_validate_scene(ctx: click.Context, scene: str, as_json: bool) -> None:
    """Validate a scene file using the Godot engine.

    Loads the scene through Godot's resource loader to check if it's
    well-formed and all dependencies resolve correctly.
    """
    project_path: Path = ctx.obj["project_path"]
    result = validate_scene(project_path, scene)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            data = result.data
            click.echo(f"Scene valid: {scene}")
            click.echo(f"  Nodes: {data.get('node_count', 0)}")
            click.echo(f"  Connections: {data.get('connection_count', 0)}")
            for node in data.get("nodes", []):
                groups = f" [{', '.join(node['groups'])}]" if node.get("groups") else ""
                click.echo(f"    {node['path']} ({node['type']}){groups}")
        else:
            click.echo(f"Scene invalid: {result.error}", err=True)
            if result.godot_stderr:
                click.echo(f"  Godot output: {result.godot_stderr[:500]}", err=True)


@bridge_cmd.command("read-tree")
@click.argument("scene")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_read_tree(ctx: click.Context, scene: str, as_json: bool) -> None:
    """Read a scene's full instantiated tree from Godot.

    Instantiates the scene and traverses the node tree, capturing
    all node types, properties, and children. Shows what Godot
    actually sees, including inherited and instanced content.
    """
    project_path: Path = ctx.obj["project_path"]
    result = read_scene_tree(project_path, scene)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            _print_tree(result.data.get("tree", {}), indent=0)
        else:
            click.echo(f"Error: {result.error}", err=True)


def _print_tree(node: dict, indent: int) -> None:
    prefix = "  " * indent
    name = node.get("name", "?")
    cls = node.get("class", "?")
    click.echo(f"{prefix}{name} ({cls})")
    for child in node.get("children", []):
        _print_tree(child, indent + 1)


@bridge_cmd.command("validate-resources")
@click.argument("paths", nargs=-1, required=True)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_validate_resources(ctx: click.Context, paths: tuple[str, ...], as_json: bool) -> None:
    """Validate that resource files can be loaded by Godot.

    Checks if images, audio, scripts, scenes, and other resources
    are importable and loadable by the engine.
    """
    project_path: Path = ctx.obj["project_path"]
    normalized = []
    for p in paths:
        if not p.startswith("res://"):
            p = f"res://{p}"
        normalized.append(p)

    result = validate_resources(project_path, normalized)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            for res in result.data.get("resources", []):
                status = "OK" if res["valid"] else "FAIL"
                type_info = f" ({res['type']})" if res.get("type") else ""
                click.echo(f"  [{status}] {res['path']}{type_info}")
        else:
            click.echo(f"Error: {result.error}", err=True)


@bridge_cmd.command("validate-script")
@click.argument("script")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_validate_script(ctx: click.Context, script: str, as_json: bool) -> None:
    """Validate a GDScript file using the Godot parser.

    Loads the script through Godot to check syntax and type errors
    beyond what text analysis can catch.
    """
    project_path: Path = ctx.obj["project_path"]
    result = validate_script(project_path, script)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            data = result.data
            click.echo(f"Script valid: {script}")
            click.echo(f"  Base type: {data.get('base_type', 'unknown')}")
        else:
            click.echo(f"Script invalid: {result.error}", err=True)


@bridge_cmd.command("project-info")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_project_info(ctx: click.Context, as_json: bool) -> None:
    """Read project info from Godot's perspective.

    Shows project name, main scene, engine version, and renderer.
    """
    project_path: Path = ctx.obj["project_path"]
    result = read_project_info(project_path)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            data = result.data
            click.echo(f"Project: {data.get('name', 'unnamed')}")
            click.echo(f"  Main scene: {data.get('main_scene', 'none')}")
            click.echo(f"  Renderer: {data.get('renderer', 'unknown')}")
            ver = data.get("version", {})
            if ver:
                click.echo(f"  Godot: {ver.get('major', '?')}.{ver.get('minor', '?')}.{ver.get('patch', '?')}")
        else:
            click.echo(f"Error: {result.error}", err=True)


@bridge_cmd.command("class-props")
@click.argument("class_name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_class_props(ctx: click.Context, class_name: str, as_json: bool) -> None:
    """Show properties of a Godot node/resource class.

    Queries Godot's ClassDB for all editor-visible properties of a class.
    Useful for knowing what properties can be set on a node type.
    """
    project_path: Path = ctx.obj["project_path"]
    result = get_class_properties(project_path, class_name)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            props = result.data.get("properties", [])
            click.echo(f"{class_name} properties ({len(props)}):")
            for p in props:
                click.echo(f"  {p['name']}: {p['type_name']}")
        else:
            click.echo(f"Error: {result.error}", err=True)


@bridge_cmd.command("list-types")
@click.option("--base", "-b", default="Node", help="Base class to list inheritors of")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_list_types(ctx: click.Context, base: str, as_json: bool) -> None:
    """List all instantiable node types from Godot's ClassDB.

    Shows all concrete classes that inherit from the given base class.
    """
    project_path: Path = ctx.obj["project_path"]
    result = list_node_types(project_path, base)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            types = result.data.get("types", [])
            click.echo(f"Types inheriting from {base} ({len(types)}):")
            for t in types:
                click.echo(f"  {t}")
        else:
            click.echo(f"Error: {result.error}", err=True)
