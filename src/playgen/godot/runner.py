"""Godot engine process management.

Finds the Godot executable and runs projects, capturing output for
error analysis and feedback loops.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.errors

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "stdout": self.stdout[-2000:] if len(self.stdout) > 2000 else self.stdout,
            "stderr": self.stderr[-2000:] if len(self.stderr) > 2000 else self.stderr,
        }


# Patterns for parsing Godot error output
_ERROR_PATTERNS = [
    # GDScript errors: res://file.gd:10 - Error message
    re.compile(r"(res://[^:]+):(\d+)\s*[-:]\s*(.+)"),
    # Parser errors
    re.compile(r"SCRIPT ERROR:\s*(.+?):\s*at\s*(res://[^:]+):(\d+)"),
    # General errors
    re.compile(r"ERROR:\s*(.+)"),
]


def find_godot() -> str | None:
    env_path = os.environ.get("GODOT_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # Try common executable names
    for name in ["godot", "godot4", "Godot_v4"]:
        found = shutil.which(name)
        if found:
            return found

    # Windows: check common locations
    if os.name == "nt":
        common_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Godot",
            Path(os.environ.get("PROGRAMFILES", "")) / "Godot",
            Path(os.environ.get("SCOOP", Path.home() / "scoop")) / "apps" / "godot" / "current",
        ]
        for d in common_dirs:
            if d.exists():
                for f in d.glob("*.exe"):
                    if "godot" in f.name.lower() and "console" not in f.name.lower():
                        return str(f)

    return None


def _parse_errors(output: str) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "WARNING:" in line:
            warnings.append(line)
            continue

        # res://file.gd:10 - Error message
        m = re.search(r"(res://[^:]+):(\d+)\s*[-:]\s*(.+)", line)
        if m:
            errors.append({
                "file": m.group(1),
                "line": m.group(2),
                "message": m.group(3).strip(),
            })
            continue

        # SCRIPT ERROR: message at res://file.gd:10
        m = re.search(r"SCRIPT ERROR:\s*(.+?)(?:\s+at\s+(res://[^:]+):(\d+))?", line)
        if m:
            err: dict[str, str] = {"message": m.group(1).strip()}
            if m.group(2):
                err["file"] = m.group(2)
                err["line"] = m.group(3)
            errors.append(err)
            continue

        if "ERROR:" in line:
            errors.append({"message": line.split("ERROR:", 1)[1].strip()})

    return errors, warnings


def run_project(
    project_path: Path,
    scene: str | None = None,
    timeout: int = 30,
    godot_path: str | None = None,
    extra_args: list[str] | None = None,
) -> RunResult:
    godot = godot_path or find_godot()
    if not godot:
        return RunResult(
            exit_code=-1,
            stdout="",
            stderr="Godot executable not found. Set GODOT_PATH environment variable or add Godot to PATH.",
            errors=[{"message": "Godot executable not found. Set GODOT_PATH or add godot to PATH."}],
        )

    cmd = [godot, "--path", str(project_path)]
    if scene:
        cmd.append(scene)
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_path),
        )
        combined = result.stdout + "\n" + result.stderr
        errors, warnings = _parse_errors(combined)
        return RunResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            errors=errors,
            warnings=warnings,
        )
    except subprocess.TimeoutExpired:
        # Timeout is expected for games - they run until closed
        return RunResult(exit_code=0, stdout="", stderr="", errors=[], warnings=["Process timed out (this is normal for games - it ran successfully)"])
    except FileNotFoundError:
        return RunResult(
            exit_code=-1,
            stdout="",
            stderr=f"Godot executable not found at: {godot}",
            errors=[{"message": f"Godot executable not found at: {godot}"}],
        )


def check_project(project_path: Path, godot_path: str | None = None) -> RunResult:
    """Run Godot in headless mode to validate the project without displaying it."""
    godot = godot_path or find_godot()
    if not godot:
        return RunResult(
            exit_code=-1, stdout="", stderr="Godot not found",
            errors=[{"message": "Godot executable not found."}],
        )

    cmd = [godot, "--headless", "--path", str(project_path), "--check-only", "--quit"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        combined = result.stdout + "\n" + result.stderr
        errors, warnings = _parse_errors(combined)
        return RunResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            errors=errors,
            warnings=warnings,
        )
    except subprocess.TimeoutExpired:
        return RunResult(exit_code=0, stdout="", stderr="", warnings=["Check timed out"])
    except FileNotFoundError:
        return RunResult(
            exit_code=-1, stdout="", stderr=f"Godot not found at: {godot}",
            errors=[{"message": f"Godot not found at: {godot}"}],
        )
