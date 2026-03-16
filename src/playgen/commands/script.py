"""playgen script - Script creation and attachment."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.tscn import parse_tscn, write_tscn
from playgen.templates import SCRIPT_TEMPLATES, EXTENDS_DEFAULTS


@click.group("script")
def script_cmd() -> None:
    """Script operations: create scripts and attach them to nodes."""
    pass


@script_cmd.command("create")
@click.argument("name")
@click.option("--extends", "-e", "extends_type", default="Node", help="Base class to extend (default: Node)")
@click.option(
    "--template", "-t",
    type=click.Choice(list(SCRIPT_TEMPLATES.keys())),
    default=None,
    help="Use a built-in script template",
)
@click.option("--list-templates", is_flag=True, help="List available script templates")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def script_create(
    ctx: click.Context,
    name: str,
    extends_type: str,
    template: str | None,
    list_templates: bool,
    as_json: bool,
) -> None:
    """Create a new GDScript file.

    NAME is the script filename (e.g., 'enemy.gd' or 'enemy').
    """
    if list_templates:
        if as_json:
            click.echo(json.dumps(list(SCRIPT_TEMPLATES.keys())))
        else:
            click.echo("Available script templates:")
            for key in SCRIPT_TEMPLATES:
                click.echo(f"  {key}")
        return

    project_path: Path = ctx.obj["project_path"]
    if not name.endswith(".gd"):
        name += ".gd"

    script_path = project_path / name
    if script_path.exists():
        if as_json:
            click.echo(json.dumps({"error": f"{name} already exists"}))
        else:
            click.echo(f"Error: {name} already exists", err=True)
        ctx.exit(1)
        return

    if template:
        content = SCRIPT_TEMPLATES[template]
    elif extends_type in EXTENDS_DEFAULTS:
        content = EXTENDS_DEFAULTS[extends_type]
    else:
        content = f"extends {extends_type}\n\n\nfunc _ready() -> void:\n\tpass\n\n\nfunc _process(_delta: float) -> void:\n\tpass\n"

    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(content, encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"created": name, "extends": extends_type, "template": template}))
    else:
        click.echo(f"Created script: {name}")


@script_cmd.command("attach")
@click.argument("scene")
@click.option("--node", "-n", required=True, help="Node name to attach script to")
@click.option("--script", "-s", "script_path", required=True, help="Script file path (e.g., player.gd)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def script_attach(ctx: click.Context, scene: str, node: str, script_path: str, as_json: bool) -> None:
    """Attach a script to a node in a scene.

    SCENE is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_file = project_path / scene
    if not scene_file.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Normalize script path to res:// format
    if not script_path.startswith("res://"):
        res_path = f"res://{script_path}"
    else:
        res_path = script_path

    # Warn if script file doesn't exist
    script_file_path = project_path / res_path.replace("res://", "")
    if not script_file_path.exists():
        warning = f"Warning: script file '{script_path}' does not exist. Create it with 'playgen script create'."
        if as_json:
            pass  # will include in output
        else:
            click.echo(warning, err=True)

    scene_obj = parse_tscn(scene_file.read_text(encoding="utf-8"))
    target = scene_obj.find_node(node)
    if not target:
        msg = f"Node '{node}' not found in {scene}"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    # Add ext_resource and set script property
    res = scene_obj.add_ext_resource("Script", res_path)
    target.properties["script"] = f'ExtResource("{res.id}")'

    scene_file.write_text(write_tscn(scene_obj), encoding="utf-8")

    result = {"attached": script_path, "to_node": node, "scene": scene}
    if not script_file_path.exists():
        result["warning"] = f"Script file '{script_path}' does not exist"
    if as_json:
        click.echo(json.dumps(result))
    else:
        click.echo(f"Attached {script_path} to node '{node}' in {scene}")


@script_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def script_list(ctx: click.Context, as_json: bool) -> None:
    """List all scripts in the project."""
    project_path: Path = ctx.obj["project_path"]

    scripts = sorted(project_path.rglob("*.gd"))
    scripts = [s for s in scripts if ".godot" not in s.parts and ".playgen" not in s.parts]

    if as_json:
        result = []
        for s in scripts:
            rel = str(s.relative_to(project_path)).replace("\\", "/")
            content = s.read_text(encoding="utf-8")
            extends = ""
            for line in content.split("\n"):
                if line.startswith("extends "):
                    extends = line.split(" ", 1)[1].strip()
                    break
            result.append({"path": rel, "res_path": f"res://{rel}", "extends": extends})
        click.echo(json.dumps(result, indent=2))
    else:
        if not scripts:
            click.echo("No scripts found.")
            return
        for s in scripts:
            rel = str(s.relative_to(project_path)).replace("\\", "/")
            content = s.read_text(encoding="utf-8")
            extends = ""
            for line in content.split("\n"):
                if line.startswith("extends "):
                    extends = line.split(" ", 1)[1].strip()
                    break
            click.echo(f"  {rel:30s} extends {extends}")
