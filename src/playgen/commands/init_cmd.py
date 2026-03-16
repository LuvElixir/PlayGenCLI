"""playgen init - Initialize a Godot 4.x project from template."""

from __future__ import annotations

import json
from pathlib import Path

import click

from playgen.templates import AVAILABLE_TEMPLATES, create_project_from_template


@click.command("init")
@click.option("--name", "-n", default=None, help="Project name (defaults to directory name)")
@click.option(
    "--template", "-t",
    type=click.Choice(list(AVAILABLE_TEMPLATES.keys())),
    default="empty-2d",
    help="Project template to use",
)
@click.option("--list-templates", is_flag=True, help="List available templates and exit")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def init_cmd(ctx: click.Context, name: str | None, template: str, list_templates: bool, as_json: bool) -> None:
    """Initialize a new Godot 4.x project.

    Creates project structure with scenes, scripts, and configuration
    based on the selected template. Run from the target directory or
    use --project to specify path.
    """
    if list_templates:
        if as_json:
            click.echo(json.dumps(AVAILABLE_TEMPLATES, indent=2))
        else:
            click.echo("Available templates:")
            for key, desc in AVAILABLE_TEMPLATES.items():
                click.echo(f"  {key:20s} {desc}")
        return

    project_path: Path = ctx.obj["project_path"]
    project_name = name or project_path.name

    # Check if project already exists
    if (project_path / "project.godot").exists():
        if as_json:
            click.echo(json.dumps({"error": "project.godot already exists"}))
        else:
            click.echo(f"Error: project.godot already exists in {project_path}", err=True)
        ctx.exit(1)
        return

    created = create_project_from_template(project_path, project_name, template)

    if as_json:
        click.echo(json.dumps({
            "project_name": project_name,
            "template": template,
            "path": str(project_path),
            "created_files": created,
        }, indent=2))
    else:
        click.echo(f"Created Godot 4.x project: {project_name}")
        click.echo(f"Template: {template}")
        click.echo(f"Path: {project_path}")
        click.echo(f"Files created:")
        for f in created:
            click.echo(f"  {f}")
        click.echo(f"\nNext steps:")
        click.echo(f"  playgen run          # Run the project")
        click.echo(f"  playgen analyze      # See project structure")
        click.echo(f"  playgen doctor       # Check for issues")
