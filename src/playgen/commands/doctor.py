"""playgen doctor - Diagnose and fix common project issues."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from playgen.godot.project_file import load_project, save_project
from playgen.godot.tscn import parse_tscn, write_tscn
from playgen.godot.runner import find_godot


@click.command("doctor")
@click.option("--fix", is_flag=True, help="Automatically fix issues where possible")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def doctor_cmd(ctx: click.Context, fix: bool, as_json: bool) -> None:
    """Diagnose and fix common project issues.

    Checks for missing files, broken references, configuration problems,
    and other issues that prevent the project from running correctly.
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

    issues: list[dict] = []
    fixed: list[str] = []

    proj = load_project(project_path)

    # Check 1: Godot executable
    godot = find_godot()
    if not godot:
        issues.append({
            "severity": "warning",
            "category": "environment",
            "message": "Godot executable not found. Set GODOT_PATH or add to PATH.",
            "fixable": False,
        })
    else:
        if not as_json:
            click.echo(f"[ok] Godot found: {godot}")

    # Check 2: Main scene exists
    main_scene = proj.main_scene
    if not main_scene:
        issues.append({
            "severity": "error",
            "category": "config",
            "message": "No main scene set in project.godot",
            "fixable": True,
        })
        if fix:
            scenes = list(project_path.rglob("*.tscn"))
            scenes = [s for s in scenes if ".godot" not in s.parts]
            if scenes:
                rel = str(scenes[0].relative_to(project_path)).replace("\\", "/")
                proj.main_scene = f"res://{rel}"
                save_project(proj, project_path)
                fixed.append(f"Set main scene to res://{rel}")
    else:
        # Check that main scene file exists
        scene_rel = main_scene.replace("res://", "")
        scene_file = project_path / scene_rel
        if not scene_file.exists():
            issues.append({
                "severity": "error",
                "category": "missing_file",
                "message": f"Main scene file not found: {main_scene}",
                "fixable": False,
            })
        else:
            if not as_json:
                click.echo(f"[ok] Main scene exists: {main_scene}")

    # Check 3: Script references in scenes
    scene_files = sorted(project_path.rglob("*.tscn"))
    scene_files = [s for s in scene_files if ".godot" not in s.parts]

    for sf in scene_files:
        scene_rel = str(sf.relative_to(project_path)).replace("\\", "/")
        try:
            scene = parse_tscn(sf.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append({
                "severity": "error",
                "category": "parse_error",
                "message": f"Failed to parse {scene_rel}: {e}",
                "fixable": False,
            })
            continue

        # Check ext_resource references
        for res in scene.ext_resources:
            res_file = project_path / res.path.replace("res://", "")
            if not res_file.exists():
                issues.append({
                    "severity": "error",
                    "category": "missing_file",
                    "message": f"Missing resource in {scene_rel}: {res.path} ({res.type})",
                    "fixable": False,
                })

    # Check 4: Script extends matches node type
    for sf in scene_files:
        scene_rel = str(sf.relative_to(project_path)).replace("\\", "/")
        try:
            scene = parse_tscn(sf.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in scene.nodes:
            script_prop = node.properties.get("script", "")
            if not script_prop:
                continue

            # Extract ext_resource id
            m = re.search(r'ExtResource\("([^"]*)"\)', script_prop)
            if not m:
                continue

            res_id = m.group(1)
            ext_res = None
            for r in scene.ext_resources:
                if r.id == res_id:
                    ext_res = r
                    break

            if not ext_res:
                continue

            script_file = project_path / ext_res.path.replace("res://", "")
            if not script_file.exists():
                continue

            content = script_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("extends "):
                    extends_type = line.split(" ", 1)[1].strip()
                    if extends_type != node.type and node.type:
                        issues.append({
                            "severity": "warning",
                            "category": "type_mismatch",
                            "message": (
                                f"Script {ext_res.path} extends {extends_type} "
                                f"but is attached to {node.name} ({node.type}) in {scene_rel}"
                            ),
                            "fixable": True,
                        })
                        if fix:
                            # Fix the script extends
                            new_content = content.replace(
                                f"extends {extends_type}",
                                f"extends {node.type}",
                                1,
                            )
                            script_file.write_text(new_content, encoding="utf-8")
                            fixed.append(f"Fixed {ext_res.path}: extends {extends_type} -> {node.type}")
                    break

    # Check 5: Empty scenes (no nodes)
    for sf in scene_files:
        scene_rel = str(sf.relative_to(project_path)).replace("\\", "/")
        try:
            scene = parse_tscn(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not scene.nodes:
            issues.append({
                "severity": "warning",
                "category": "empty_scene",
                "message": f"Scene {scene_rel} has no nodes",
                "fixable": False,
            })

    # Output
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    if as_json:
        click.echo(json.dumps({
            "issues": issues,
            "fixed": fixed,
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "fixed": len(fixed),
            },
        }, indent=2))
    else:
        if not issues:
            click.echo("\nNo issues found. Project looks good!")
        else:
            if errors:
                click.echo(f"\nErrors ({len(errors)}):")
                for e in errors:
                    click.echo(f"  [error] {e['message']}")
            if warnings:
                click.echo(f"\nWarnings ({len(warnings)}):")
                for w in warnings:
                    click.echo(f"  [warn]  {w['message']}")

        if fixed:
            click.echo(f"\nFixed ({len(fixed)}):")
            for f_msg in fixed:
                click.echo(f"  [fixed] {f_msg}")
        elif issues and not fix:
            fixable = [i for i in issues if i.get("fixable")]
            if fixable:
                click.echo(f"\n{len(fixable)} issue(s) can be auto-fixed. Run 'playgen doctor --fix'")
