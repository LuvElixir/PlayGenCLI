"""playgen autoload - Manage Godot autoload (singleton) entries."""

from __future__ import annotations

import json

import click

from playgen.godot.project_file import load_project, save_project


@click.group("autoload")
def autoload_cmd() -> None:
    """Manage autoloads (global singletons): add, remove, list.

    Autoloads are scripts that Godot loads as singletons at startup,
    accessible from any scene. Essential for game managers, global state, etc.
    """
    pass


@autoload_cmd.command("add")
@click.argument("name")
@click.argument("script")
@click.option("--disabled", is_flag=True, help="Register but don't enable the autoload")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def autoload_add(ctx: click.Context, name: str, script: str, disabled: bool, as_json: bool) -> None:
    """Register a script as an autoload singleton.

    NAME is the autoload name (e.g., GameManager).
    SCRIPT is the script path (e.g., game_manager.gd).

    \b
    Examples:
      playgen autoload add GameManager game_manager.gd
      playgen autoload add AudioBus audio/audio_bus.gd
      playgen autoload add SaveSystem save_system.gd --disabled
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    if not script.startswith("res://"):
        script = f"res://{script}"

    # Autoload format: Name="*res://path.gd" (* = enabled)
    prefix = "" if disabled else "*"
    proj.set("autoload", name, f'"{prefix}{script}"')
    save_project(proj, project_path)

    if as_json:
        click.echo(json.dumps({"added": name, "script": script, "enabled": not disabled}))
    else:
        status = "disabled" if disabled else "enabled"
        click.echo(f"Autoload added: {name} -> {script} [{status}]")


@autoload_cmd.command("remove")
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def autoload_remove(ctx: click.Context, name: str, as_json: bool) -> None:
    """Remove an autoload entry.

    NAME is the autoload name to remove.
    """
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    autoloads = proj.sections.get("autoload", {})
    if name not in autoloads:
        msg = f"Autoload '{name}' not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    del proj.sections["autoload"][name]
    save_project(proj, project_path)

    if as_json:
        click.echo(json.dumps({"removed": name}))
    else:
        click.echo(f"Autoload removed: {name}")


@autoload_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def autoload_list(ctx: click.Context, as_json: bool) -> None:
    """List all autoload entries."""
    project_path = ctx.obj["project_path"]
    proj = load_project(project_path)

    autoloads = proj.sections.get("autoload", {})

    if as_json:
        entries = []
        for name, value in autoloads.items():
            raw = value.strip('"')
            enabled = raw.startswith("*")
            path = raw.lstrip("*")
            entries.append({"name": name, "script": path, "enabled": enabled})
        click.echo(json.dumps(entries, indent=2))
    else:
        if not autoloads:
            click.echo("No autoloads configured.")
            return
        for name, value in autoloads.items():
            raw = value.strip('"')
            enabled = raw.startswith("*")
            path = raw.lstrip("*")
            status = "enabled" if enabled else "disabled"
            click.echo(f"  {name:25s} {path:40s} [{status}]")
