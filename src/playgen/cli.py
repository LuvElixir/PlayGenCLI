"""PlayGen CLI - main entry point.

All commands support --json-output for machine-readable output,
making them suitable for AI agent consumption.
"""

from __future__ import annotations

from pathlib import Path

import click

from playgen import __version__
from playgen.commands.init_cmd import init_cmd
from playgen.commands.scene import scene_cmd
from playgen.commands.node import node_cmd
from playgen.commands.script import script_cmd
from playgen.commands.run import run_cmd
from playgen.commands.analyze import analyze_cmd
from playgen.commands.doctor import doctor_cmd
from playgen.commands.build import build_cmd
from playgen.commands.signal_cmd import signal_cmd
from playgen.commands.autoload_cmd import autoload_cmd
from playgen.commands.config_cmd import config_cmd
from playgen.commands.input_cmd import input_cmd
from playgen.commands.resource_cmd import resource_cmd
from playgen.commands.animation_cmd import animation_cmd
from playgen.commands.asset_cmd import asset_cmd
from playgen.commands.bridge_cmd import bridge_cmd
from playgen.commands.snapshot_cmd import snapshot_cmd


@click.group()
@click.option("--project", "-p", default=".", help="Godot project directory (default: current directory)")
@click.version_option(version=__version__, prog_name="playgen")
@click.pass_context
def main(ctx: click.Context, project: str) -> None:
    """PlayGen - Vibe game dev CLI for Godot 4.x.

    Agent execution layer for AI-driven game prototyping.
    All commands support --json-output for structured Agent consumption.

    \b
    Quick start:
      playgen init --template 2d-platformer   # Create a platformer project
      playgen build scene.json                # Build scene from JSON
      playgen run                              # Run the project
      playgen run --observe                    # Run with runtime telemetry
      playgen analyze                          # See what's in the project

    \b
    Asset pipeline:
      playgen asset import/attach/list         # Import & wire up assets

    \b
    Engine bridge (requires Godot):
      playgen bridge validate-scene/read-tree  # Engine-native validation
      playgen bridge validate-script           # GDScript validation
      playgen bridge class-props               # Class introspection

    \b
    Project management:
      playgen autoload add/remove/list         # Manage singletons
      playgen config set/get/list              # Project settings
      playgen input add/remove/list            # Input mappings
      playgen resource create/list             # .tres resource files
      playgen animation add/list               # Animations

    \b
    Safety:
      playgen snapshot save/restore/diff/list  # Project state snapshots
    """
    ctx.ensure_object(dict)
    ctx.obj["project_path"] = Path(project).resolve()


main.add_command(init_cmd)
main.add_command(scene_cmd)
main.add_command(node_cmd)
main.add_command(script_cmd)
main.add_command(run_cmd)
main.add_command(analyze_cmd)
main.add_command(doctor_cmd)
main.add_command(build_cmd)
main.add_command(signal_cmd)
main.add_command(autoload_cmd)
main.add_command(config_cmd)
main.add_command(input_cmd)
main.add_command(resource_cmd)
main.add_command(animation_cmd)
main.add_command(asset_cmd)
main.add_command(bridge_cmd)
main.add_command(snapshot_cmd)
