"""playgen signal - Signal connection operations."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.tscn import Connection, parse_tscn, write_tscn


@click.group("signal")
def signal_cmd() -> None:
    """Signal operations: connect, list, and remove signal connections."""
    pass


@signal_cmd.command("connect")
@click.argument("scene")
@click.option("--from", "-f", "from_node", required=True, help="Source node emitting the signal")
@click.option("--signal", "-s", "signal_name", required=True, help="Signal name (e.g., body_entered)")
@click.option("--to", "-t", "to_node", required=True, help="Target node receiving the signal")
@click.option("--method", "-m", required=True, help="Method to call on target node")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def signal_connect(
    ctx: click.Context,
    scene: str,
    from_node: str,
    signal_name: str,
    to_node: str,
    method: str,
    as_json: bool,
) -> None:
    """Connect a signal between two nodes.

    SCENE is the scene filename (e.g., 'main.tscn').

    \b
    Example:
      playgen signal connect main --from Coin --signal body_entered \\
        --to GameManager --method _on_coin_collected
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        _err(f"{scene} not found", as_json, ctx)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))

    # Check for duplicate
    for c in scene_obj.connections:
        if c.signal_name == signal_name and c.from_node == from_node and c.to_node == to_node and c.method == method:
            msg = f"Connection already exists: {from_node}.{signal_name} -> {to_node}.{method}()"
            if as_json:
                click.echo(json.dumps({"warning": msg}))
            else:
                click.echo(f"Warning: {msg}")
            return

    scene_obj.connections.append(Connection(
        signal_name=signal_name,
        from_node=from_node,
        to_node=to_node,
        method=method,
    ))

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({
            "connected": True,
            "signal": signal_name,
            "from": from_node,
            "to": to_node,
            "method": method,
            "scene": scene,
        }))
    else:
        click.echo(f"Connected: {from_node}.{signal_name} -> {to_node}.{method}()")


@signal_cmd.command("list")
@click.argument("scene")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def signal_list(ctx: click.Context, scene: str, as_json: bool) -> None:
    """List all signal connections in a scene.

    SCENE is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        _err(f"{scene} not found", as_json, ctx)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))

    if as_json:
        result = [
            {
                "signal": c.signal_name,
                "from": c.from_node,
                "to": c.to_node,
                "method": c.method,
            }
            for c in scene_obj.connections
        ]
        click.echo(json.dumps(result, indent=2))
    else:
        if not scene_obj.connections:
            click.echo("No signal connections.")
            return
        click.echo(f"Signal connections ({len(scene_obj.connections)}):")
        for c in scene_obj.connections:
            click.echo(f"  {c.from_node}.{c.signal_name} -> {c.to_node}.{c.method}()")


@signal_cmd.command("remove")
@click.argument("scene")
@click.option("--from", "-f", "from_node", required=True, help="Source node")
@click.option("--signal", "-s", "signal_name", required=True, help="Signal name")
@click.option("--to", "-t", "to_node", default=None, help="Target node (if omitted, removes all connections for this signal)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def signal_remove(
    ctx: click.Context,
    scene: str,
    from_node: str,
    signal_name: str,
    to_node: str | None,
    as_json: bool,
) -> None:
    """Remove signal connection(s) from a scene.

    SCENE is the scene filename (e.g., 'main.tscn').
    """
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"

    scene_path = project_path / scene
    if not scene_path.exists():
        _err(f"{scene} not found", as_json, ctx)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))

    before = len(scene_obj.connections)
    scene_obj.connections = [
        c for c in scene_obj.connections
        if not (
            c.signal_name == signal_name
            and c.from_node == from_node
            and (to_node is None or c.to_node == to_node)
        )
    ]
    removed = before - len(scene_obj.connections)

    if removed == 0:
        msg = f"No matching connection found for {from_node}.{signal_name}"
        if as_json:
            click.echo(json.dumps({"warning": msg, "removed": 0}))
        else:
            click.echo(f"Warning: {msg}")
        return

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({"removed": removed, "scene": scene}))
    else:
        click.echo(f"Removed {removed} connection(s)")


def _err(msg: str, as_json: bool, ctx: click.Context) -> None:
    if as_json:
        click.echo(json.dumps({"error": msg}))
    else:
        click.echo(f"Error: {msg}", err=True)
    ctx.exit(1)
