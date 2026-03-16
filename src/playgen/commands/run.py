"""playgen run - Run the Godot project and capture output."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.godot.runner import find_godot, run_project, check_project


@click.command("run")
@click.option("--scene", "-s", default=None, help="Specific scene to run (default: main scene)")
@click.option("--timeout", "-t", default=30, help="Timeout in seconds (default: 30)")
@click.option("--check-only", is_flag=True, help="Validate project without running (headless)")
@click.option("--debug-collisions", is_flag=True, help="Show collision shapes while running")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def run_cmd(
    ctx: click.Context,
    scene: str | None,
    timeout: int,
    check_only: bool,
    debug_collisions: bool,
    as_json: bool,
) -> None:
    """Run the Godot project.

    Launches the project using the Godot engine, captures stdout/stderr,
    parses error messages, and returns structured results.

    Set GODOT_PATH environment variable to specify the Godot executable.
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

    # Check Godot availability
    godot = find_godot()
    if not godot:
        msg = (
            "Godot executable not found.\n"
            "Options:\n"
            "  1. Set GODOT_PATH environment variable to the Godot executable\n"
            "  2. Add Godot to your system PATH\n"
            "  3. Download Godot from https://godotengine.org/download"
        )
        if as_json:
            click.echo(json.dumps({"error": "Godot executable not found", "help": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    if not as_json:
        click.echo(f"Using Godot: {godot}")

    if check_only:
        result = check_project(project_path, godot_path=godot)
    else:
        extra_args = []
        if debug_collisions:
            extra_args.append("--debug-collisions")
        result = run_project(
            project_path,
            scene=scene,
            timeout=timeout,
            godot_path=godot,
            extra_args=extra_args,
        )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            click.echo("Project ran successfully.")
        else:
            click.echo("Project encountered issues:")

        if result.errors:
            click.echo(f"\nErrors ({len(result.errors)}):")
            for err in result.errors:
                loc = ""
                if "file" in err:
                    loc = f"  {err['file']}"
                    if "line" in err:
                        loc += f":{err['line']}"
                click.echo(f"  {err['message']}{loc}")

        if result.warnings:
            click.echo(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings:
                click.echo(f"  {w}")

        if result.stderr and not result.errors:
            click.echo(f"\nStderr output:\n{result.stderr[:1000]}")
