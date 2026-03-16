"""playgen snapshot - Project state snapshots for safe multi-step operations.

Solves a critical Agent reliability problem: when an Agent executes a sequence
of build/edit operations and something goes wrong mid-way, the project is left
in a dirty state that's hard to recover from.

Snapshots allow:
- Save project state before risky operations
- Restore to a known-good state after failures
- Compare current state to a snapshot (diff)
- List available snapshots

Implementation: file-copy based (not git-dependent), stored in .playgen/snapshots/
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from datetime import datetime

import click


SNAPSHOT_DIR = ".playgen/snapshots"

# Files/dirs to exclude from snapshots
EXCLUDE_PATTERNS = {
    ".playgen",
    ".godot",
    ".git",
    "__pycache__",
    ".import",
}

# File extensions to snapshot (Godot project files)
INCLUDE_EXTENSIONS = {
    ".tscn", ".tres", ".gd", ".gdshader", ".gdshaderinc",
    ".cfg", ".godot", ".import",
    ".png", ".jpg", ".jpeg", ".svg", ".webp",
    ".wav", ".ogg", ".mp3",
    ".ttf", ".otf",
    ".json", ".txt", ".md",
}


def _snapshot_path(project_path: Path, name: str) -> Path:
    return project_path / SNAPSHOT_DIR / name


def _should_include(rel_path: Path) -> bool:
    """Check if a file should be included in the snapshot."""
    parts = rel_path.parts
    for part in parts:
        if part in EXCLUDE_PATTERNS:
            return False
    # Include known extensions or extensionless files like project.godot
    ext = rel_path.suffix.lower()
    if ext in INCLUDE_EXTENSIONS or rel_path.name == "project.godot":
        return True
    return False


def save_snapshot(project_path: Path, name: str | None = None) -> dict:
    """Save current project state as a snapshot."""
    if name is None:
        name = datetime.now().strftime("snap_%Y%m%d_%H%M%S")

    snap_dir = _snapshot_path(project_path, name)
    if snap_dir.exists():
        return {"error": f"Snapshot '{name}' already exists"}

    snap_dir.mkdir(parents=True, exist_ok=True)

    files_copied = []
    for fpath in sorted(project_path.rglob("*")):
        if fpath.is_dir():
            continue
        try:
            rel = fpath.relative_to(project_path)
        except ValueError:
            continue
        if not _should_include(rel):
            continue

        dest = snap_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(fpath), str(dest))
        files_copied.append(str(rel.as_posix()))

    # Write metadata
    meta = {
        "name": name,
        "created": datetime.now().isoformat(),
        "file_count": len(files_copied),
        "files": files_copied,
    }
    (snap_dir / "_playgen_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    return {"name": name, "files": len(files_copied), "path": str(snap_dir)}


def restore_snapshot(project_path: Path, name: str) -> dict:
    """Restore project state from a snapshot."""
    snap_dir = _snapshot_path(project_path, name)
    if not snap_dir.exists():
        return {"error": f"Snapshot '{name}' not found"}

    meta_path = snap_dir / "_playgen_meta.json"
    if not meta_path.exists():
        return {"error": f"Invalid snapshot '{name}' (no metadata)"}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    files_restored = []

    for rel_str in meta.get("files", []):
        src = snap_dir / rel_str
        dest = project_path / rel_str
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            files_restored.append(rel_str)

    return {"name": name, "files_restored": len(files_restored)}


def list_snapshots(project_path: Path) -> list[dict]:
    """List all available snapshots."""
    snap_base = project_path / SNAPSHOT_DIR
    if not snap_base.exists():
        return []

    snapshots = []
    for d in sorted(snap_base.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "_playgen_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            snapshots.append({
                "name": meta.get("name", d.name),
                "created": meta.get("created", ""),
                "file_count": meta.get("file_count", 0),
            })
        else:
            snapshots.append({"name": d.name, "created": "", "file_count": 0})

    return snapshots


def diff_snapshot(project_path: Path, name: str) -> dict:
    """Compare current project state against a snapshot."""
    snap_dir = _snapshot_path(project_path, name)
    if not snap_dir.exists():
        return {"error": f"Snapshot '{name}' not found"}

    meta_path = snap_dir / "_playgen_meta.json"
    if not meta_path.exists():
        return {"error": f"Invalid snapshot '{name}'"}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    snap_files = set(meta.get("files", []))

    # Get current project files
    current_files: set[str] = set()
    for fpath in project_path.rglob("*"):
        if fpath.is_dir():
            continue
        try:
            rel = fpath.relative_to(project_path)
        except ValueError:
            continue
        if _should_include(rel):
            current_files.add(str(rel.as_posix()))

    added = sorted(current_files - snap_files)
    removed = sorted(snap_files - current_files)

    # Check modified files (compare content)
    modified = []
    for f in sorted(snap_files & current_files):
        snap_file = snap_dir / f
        curr_file = project_path / f
        if snap_file.exists() and curr_file.exists():
            try:
                if snap_file.read_bytes() != curr_file.read_bytes():
                    modified.append(f)
            except (OSError, IOError):
                pass

    return {
        "snapshot": name,
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": len(snap_files & current_files) - len(modified),
    }


def delete_snapshot(project_path: Path, name: str) -> dict:
    """Delete a snapshot."""
    snap_dir = _snapshot_path(project_path, name)
    if not snap_dir.exists():
        return {"error": f"Snapshot '{name}' not found"}
    shutil.rmtree(str(snap_dir))
    return {"deleted": name}


# --- CLI Commands ---

@click.group("snapshot")
def snapshot_cmd() -> None:
    """Save and restore project state snapshots.

    Enables safe multi-step operations by allowing rollback to
    known-good states when things go wrong.

    \b
    Workflow:
      playgen snapshot save before-refactor   # Save state
      playgen build complex_scene.json        # Make changes
      playgen run --check-only                # Verify
      playgen snapshot restore before-refactor  # Rollback if needed
      playgen snapshot list                   # See all snapshots
    """


@snapshot_cmd.command("save")
@click.argument("name", required=False)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_save(ctx: click.Context, name: str | None, as_json: bool) -> None:
    """Save current project state as a snapshot.

    If no name is given, an auto-generated timestamp name is used.
    """
    project_path: Path = ctx.obj["project_path"]
    result = save_snapshot(project_path, name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if "error" in result:
            click.echo(f"Error: {result['error']}", err=True)
            ctx.exit(1)
        else:
            click.echo(f"Snapshot saved: {result['name']} ({result['files']} files)")


@snapshot_cmd.command("restore")
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_restore(ctx: click.Context, name: str, as_json: bool) -> None:
    """Restore project state from a snapshot.

    Overwrites current project files with the snapshot versions.
    Files added after the snapshot was taken are NOT removed.
    """
    project_path: Path = ctx.obj["project_path"]
    result = restore_snapshot(project_path, name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if "error" in result:
            click.echo(f"Error: {result['error']}", err=True)
            ctx.exit(1)
        else:
            click.echo(f"Restored snapshot: {name} ({result['files_restored']} files)")


@snapshot_cmd.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_list(ctx: click.Context, as_json: bool) -> None:
    """List all available snapshots."""
    project_path: Path = ctx.obj["project_path"]
    snapshots = list_snapshots(project_path)

    if as_json:
        click.echo(json.dumps({"snapshots": snapshots}, indent=2))
    else:
        if not snapshots:
            click.echo("No snapshots found.")
        else:
            click.echo(f"Snapshots ({len(snapshots)}):")
            for s in snapshots:
                created = s.get("created", "unknown")
                if created and "T" in created:
                    created = created.split("T")[0] + " " + created.split("T")[1][:8]
                click.echo(f"  {s['name']} ({s['file_count']} files, {created})")


@snapshot_cmd.command("diff")
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_diff(ctx: click.Context, name: str, as_json: bool) -> None:
    """Show changes since a snapshot was taken."""
    project_path: Path = ctx.obj["project_path"]
    result = diff_snapshot(project_path, name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if "error" in result:
            click.echo(f"Error: {result['error']}", err=True)
            ctx.exit(1)
        else:
            click.echo(f"Changes since '{name}':")
            if result["added"]:
                click.echo(f"\n  Added ({len(result['added'])}):")
                for f in result["added"]:
                    click.echo(f"    + {f}")
            if result["removed"]:
                click.echo(f"\n  Removed ({len(result['removed'])}):")
                for f in result["removed"]:
                    click.echo(f"    - {f}")
            if result["modified"]:
                click.echo(f"\n  Modified ({len(result['modified'])}):")
                for f in result["modified"]:
                    click.echo(f"    ~ {f}")
            click.echo(f"\n  Unchanged: {result['unchanged']}")


@snapshot_cmd.command("delete")
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cmd_delete(ctx: click.Context, name: str, as_json: bool) -> None:
    """Delete a snapshot."""
    project_path: Path = ctx.obj["project_path"]
    result = delete_snapshot(project_path, name)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if "error" in result:
            click.echo(f"Error: {result['error']}", err=True)
            ctx.exit(1)
        else:
            click.echo(f"Deleted snapshot: {name}")
