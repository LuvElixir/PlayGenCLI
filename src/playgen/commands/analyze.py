"""playgen analyze - Analyze project state for agent consumption."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.project_file import load_project
from playgen.godot.tscn import parse_tscn


@click.command("analyze")
@click.option("--scene", "-s", default=None, help="Analyze a specific scene in detail")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def analyze_cmd(ctx: click.Context, scene: str | None, as_json: bool) -> None:
    """Analyze the current Godot project.

    Shows project configuration, scenes, scripts, and their relationships.
    Use --json for machine-readable output suitable for AI agents.
    """
    project_path: Path = ctx.obj["project_path"]

    if not (project_path / "project.godot").exists():
        msg = "No project.godot found. Run 'playgen init' first."
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    if scene:
        _analyze_scene(project_path, scene, as_json)
    else:
        _analyze_project(project_path, as_json)


def _analyze_project(project_path: Path, as_json: bool) -> None:
    proj = load_project(project_path)

    # Collect scenes
    scene_files = sorted(project_path.rglob("*.tscn"))
    scene_files = [s for s in scene_files if ".godot" not in s.parts]

    scenes_info = []
    for sf in scene_files:
        rel = str(sf.relative_to(project_path)).replace("\\", "/")
        scene_obj = parse_tscn(sf.read_text(encoding="utf-8"))
        root = scene_obj.get_root()

        # Find scripts used in this scene
        scripts_used = []
        for r in scene_obj.ext_resources:
            if r.type == "Script":
                scripts_used.append(r.path)

        # Collect signal connections
        connections_list = [
            {"signal": c.signal_name, "from": c.from_node, "to": c.to_node, "method": c.method}
            for c in scene_obj.connections
        ]

        # Collect sub-resources
        sub_resources_list = [
            {"type": r.type, "id": r.id, "properties": r.properties}
            for r in scene_obj.sub_resources
        ]

        scenes_info.append({
            "path": rel,
            "res_path": f"res://{rel}",
            "root_type": root.type if root else "",
            "node_count": len(scene_obj.nodes),
            "scripts": scripts_used,
            "connections": connections_list,
            "sub_resources": sub_resources_list,
        })

    # Collect scripts
    script_files = sorted(project_path.rglob("*.gd"))
    script_files = [s for s in script_files if ".godot" not in s.parts]

    scripts_info = []
    for sf in script_files:
        rel = str(sf.relative_to(project_path)).replace("\\", "/")
        content = sf.read_text(encoding="utf-8")
        extends = ""
        for line in content.split("\n"):
            if line.startswith("extends "):
                extends = line.split(" ", 1)[1].strip()
                break

        # Find which scenes use this script
        res_path = f"res://{rel}"
        used_in = [
            si["path"] for si in scenes_info
            if res_path in si["scripts"]
        ]

        scripts_info.append({
            "path": rel,
            "res_path": res_path,
            "extends": extends,
            "used_in_scenes": used_in,
            "lines": len(content.split("\n")),
        })

    # Collect other resources
    resource_files = sorted(project_path.rglob("*.tres"))
    resource_files = [r for r in resource_files if ".godot" not in r.parts]
    resources_info = [
        {"path": str(r.relative_to(project_path)).replace("\\", "/")}
        for r in resource_files
    ]

    result = {
        "project_name": proj.name,
        "main_scene": proj.main_scene,
        "features": proj.features,
        "scenes": scenes_info,
        "scripts": scripts_info,
        "resources": resources_info,
        "summary": {
            "total_scenes": len(scenes_info),
            "total_scripts": len(scripts_info),
            "total_resources": len(resources_info),
            "total_connections": sum(len(si["connections"]) for si in scenes_info),
            "total_sub_resources": sum(len(si["sub_resources"]) for si in scenes_info),
        },
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Project: {proj.name}")
        click.echo(f"Main scene: {proj.main_scene}")
        click.echo(f"Features: {', '.join(proj.features)}")
        click.echo()

        click.echo(f"Scenes ({len(scenes_info)}):")
        for si in scenes_info:
            conn_count = len(si["connections"])
            sub_count = len(si["sub_resources"])
            click.echo(f"  {si['path']:30s} root={si['root_type']:15s} {si['node_count']} nodes, {sub_count} sub-resources, {conn_count} connections")
            for script in si["scripts"]:
                click.echo(f"    script: {script}")
            for conn in si["connections"]:
                click.echo(f"    signal: {conn['from']}.{conn['signal']} -> {conn['to']}.{conn['method']}()")

        click.echo(f"\nScripts ({len(scripts_info)}):")
        for si in scripts_info:
            used = f"  used in: {', '.join(si['used_in_scenes'])}" if si["used_in_scenes"] else "  (unused)"
            click.echo(f"  {si['path']:30s} extends {si['extends']:20s}{used}")

        if resources_info:
            click.echo(f"\nResources ({len(resources_info)}):")
            for ri in resources_info:
                click.echo(f"  {ri['path']}")


def _analyze_scene(project_path: Path, scene_name: str, as_json: bool) -> None:
    if not scene_name.endswith(".tscn"):
        scene_name += ".tscn"

    scene_path = project_path / scene_name
    if not scene_path.exists():
        msg = f"{scene_name} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        return

    scene = parse_tscn(scene_path.read_text(encoding="utf-8"))

    result = {
        "path": scene_name,
        "tree": scene.to_dict(),
        "ext_resources": [{"type": r.type, "path": r.path, "id": r.id} for r in scene.ext_resources],
        "sub_resources": [{"type": r.type, "id": r.id, "properties": r.properties} for r in scene.sub_resources],
        "connections": [
            {"signal": c.signal_name, "from": c.from_node, "to": c.to_node, "method": c.method}
            for c in scene.connections
        ],
        "node_count": len(scene.nodes),
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Scene: {scene_name}")
        click.echo(f"Nodes: {len(scene.nodes)}")
        click.echo(f"External resources: {len(scene.ext_resources)}")
        click.echo(f"Sub resources: {len(scene.sub_resources)}")
        click.echo(f"Connections: {len(scene.connections)}")
        click.echo()

        click.echo("Node tree:")
        # Reuse scene tree printing from scene command
        from playgen.commands.scene import _print_tree
        _print_tree(scene)

        if scene.ext_resources:
            click.echo(f"\nExternal resources:")
            for r in scene.ext_resources:
                click.echo(f"  [{r.id}] {r.type}: {r.path}")

        if scene.sub_resources:
            click.echo(f"\nSub resources:")
            for r in scene.sub_resources:
                props_str = ", ".join(f"{k}={v}" for k, v in r.properties.items())
                click.echo(f"  [{r.id}] {r.type}: {props_str}")

        if scene.connections:
            click.echo(f"\nSignal connections:")
            for c in scene.connections:
                click.echo(f"  {c.from_node}.{c.signal_name} -> {c.to_node}.{c.method}()")
