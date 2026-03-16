"""playgen run - Run the Godot project and capture output.

With --observe, injects a telemetry autoload that captures runtime state
(node positions, collisions, scene changes, custom events) and provides
structured feedback to the Agent after execution.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from playgen.godot.runner import find_godot, run_project, check_project


@click.command("run")
@click.option("--scene", "-s", default=None, help="Specific scene to run (default: main scene)")
@click.option("--timeout", "-t", default=30, help="Timeout in seconds (default: 30)")
@click.option("--check-only", is_flag=True, help="Validate project without running (headless)")
@click.option("--debug-collisions", is_flag=True, help="Show collision shapes while running")
@click.option("--observe", is_flag=True, help="Inject runtime observer for structured telemetry")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def run_cmd(
    ctx: click.Context,
    scene: str | None,
    timeout: int,
    check_only: bool,
    debug_collisions: bool,
    observe: bool,
    as_json: bool,
) -> None:
    """Run the Godot project.

    Launches the project using the Godot engine, captures stdout/stderr,
    parses error messages, and returns structured results.

    With --observe, injects a telemetry autoload that captures:
    - Node positions (sampled every 30 frames)
    - Physics collision events
    - Scene tree changes (node added/removed)
    - Custom events from game scripts via PlayGenObserver.log_custom()

    Set GODOT_PATH environment variable to specify the Godot executable.

    \b
    Examples:
      playgen run                          # Run with default timeout
      playgen run --timeout 10             # Run for 10 seconds
      playgen run --observe --json-output  # Run with telemetry, get JSON
      playgen run --check-only             # Validate without running
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

    # Inject observer if requested
    telemetry_path = None
    if observe and not check_only:
        from playgen.godot.observe import inject_observer, get_default_telemetry_path
        inject_observer(project_path)
        telemetry_path = get_default_telemetry_path(project_path)
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        # Set env var so observer writes to our path
        os.environ["PLAYGEN_TELEMETRY_PATH"] = str(telemetry_path)
        if not as_json:
            click.echo("Runtime observer injected.")

    try:
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

        # Build output
        output = result.to_dict()

        # Parse telemetry if observer was active
        if observe and telemetry_path and not check_only:
            from playgen.godot.observe import parse_telemetry
            report = parse_telemetry(telemetry_path)
            output["telemetry"] = report.to_dict()

        if as_json:
            click.echo(json.dumps(output, indent=2))
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
                        loc = f" at {err['file']}"
                        if "line" in err:
                            loc += f":{err['line']}"
                    click.echo(f"  {err.get('message', 'Unknown error')}{loc}")

            if result.warnings:
                click.echo(f"\nWarnings ({len(result.warnings)}):")
                for w in result.warnings:
                    click.echo(f"  {w}")

            # Always show stderr when there are errors (gives more context)
            if result.stderr:
                stderr_lines = [l for l in result.stderr.strip().split("\n") if l.strip()]
                if stderr_lines:
                    click.echo(f"\nGodot output ({len(stderr_lines)} lines):")
                    for line in stderr_lines[:20]:
                        click.echo(f"  {line.rstrip()}")
                    if len(stderr_lines) > 20:
                        click.echo(f"  ... ({len(stderr_lines) - 20} more lines)")

            # Print telemetry summary
            if observe and telemetry_path and not check_only:
                from playgen.godot.observe import parse_telemetry
                report = parse_telemetry(telemetry_path)
                click.echo(f"\nRuntime telemetry: {report._summary()}")
                if report.node_positions:
                    click.echo("  Last known positions:")
                    for node_path, pos in report.node_positions.items():
                        click.echo(f"    {node_path}: {pos}")
                if report.collisions:
                    click.echo(f"  Collisions: {len(report.collisions)}")
                    for col in report.collisions[:5]:
                        d = col.get("data", {})
                        click.echo(f"    {d.get('body', '?')} -> {d.get('collider', '?')}")
                if report.custom_events:
                    click.echo(f"  Custom events: {len(report.custom_events)}")
                    for evt in report.custom_events[:5]:
                        click.echo(f"    [{evt.get('type', '?')}] {evt.get('data', {})}")

    finally:
        # Clean up observer if injected
        if observe and not check_only:
            from playgen.godot.observe import remove_observer
            remove_observer(project_path)
            os.environ.pop("PLAYGEN_TELEMETRY_PATH", None)
            if not as_json:
                click.echo("Runtime observer removed.")
