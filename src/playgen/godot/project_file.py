"""Godot project.godot file parser and writer.

Uses a simple INI-like format with sections and key=value pairs.
config_version is at the top level (no section).
Supports multi-line values (e.g., input maps with braces).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GodotProject:
    config_version: int = 5
    sections: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, section: str, key: str, default: str = "") -> str:
        return self.sections.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: str) -> None:
        if section not in self.sections:
            self.sections[section] = {}
        self.sections[section][key] = value

    def delete(self, section: str, key: str) -> bool:
        """Delete a key from a section. Returns True if found."""
        if section in self.sections and key in self.sections[section]:
            del self.sections[section][key]
            return True
        return False

    @property
    def name(self) -> str:
        raw = self.get("application", "config/name", '"Untitled"')
        return raw.strip('"')

    @name.setter
    def name(self, value: str) -> None:
        self.set("application", "config/name", f'"{value}"')

    @property
    def main_scene(self) -> str:
        raw = self.get("application", "run/main_scene", '""')
        return raw.strip('"')

    @main_scene.setter
    def main_scene(self, value: str) -> None:
        self.set("application", "run/main_scene", f'"{value}"')

    @property
    def features(self) -> list[str]:
        raw = self.get("application", "config/features", "")
        if not raw:
            return []
        m = re.findall(r'"([^"]*)"', raw)
        return list(m)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "main_scene": self.main_scene,
            "features": self.features,
            "sections": {s: dict(kvs) for s, kvs in self.sections.items()},
        }


_SECTION_RE = re.compile(r"^\[(\w+)\]\s*$")
_KV_RE = re.compile(r"^([A-Za-z_][\w/\.]*)\s*=\s*(.*)")


def parse_project_file(content: str) -> GodotProject:
    proj = GodotProject()
    current_section: str | None = None
    lines = content.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith(";"):
            i += 1
            continue

        m = _SECTION_RE.match(stripped)
        if m:
            current_section = m.group(1)
            i += 1
            continue

        m = _KV_RE.match(stripped)
        if m:
            key, value = m.group(1), m.group(2)

            # Handle multi-line values: count braces/brackets
            open_braces = value.count("{") - value.count("}")
            open_brackets = value.count("[") - value.count("]")
            while (open_braces > 0 or open_brackets > 0) and i + 1 < n:
                i += 1
                value += "\n" + lines[i].rstrip()
                open_braces += lines[i].count("{") - lines[i].count("}")
                open_brackets += lines[i].count("[") - lines[i].count("]")

            if current_section is None:
                if key == "config_version":
                    proj.config_version = int(value)
            else:
                proj.set(current_section, key, value)
            i += 1
            continue

        i += 1

    return proj


def write_project_file(proj: GodotProject) -> str:
    lines = [
        "; Engine configuration file.",
        "; It's best edited using the editor UI and not directly,",
        "; since the parameters that go here are not all obvious.",
        ";",
        "; Format:",
        ";   [section] ; section goes first",
        ";   key=value ; assign values to keys",
        "",
        f"config_version={proj.config_version}",
        "",
    ]

    # Define preferred section order
    preferred = ["application", "autoload", "display", "input", "layer_names", "physics", "rendering"]
    sections = list(proj.sections.keys())
    ordered = [s for s in preferred if s in sections]
    ordered += [s for s in sections if s not in ordered]

    for section in ordered:
        kvs = proj.sections[section]
        if not kvs:
            continue
        lines.append(f"[{section}]")
        lines.append("")
        for k, v in kvs.items():
            lines.append(f"{k}={v}")
        lines.append("")

    return "\n".join(lines)


def load_project(path: Path) -> GodotProject:
    project_file = path / "project.godot"
    if not project_file.exists():
        raise FileNotFoundError(f"No project.godot found in {path}")
    return parse_project_file(project_file.read_text(encoding="utf-8"))


def save_project(proj: GodotProject, path: Path) -> None:
    project_file = path / "project.godot"
    project_file.write_text(write_project_file(proj), encoding="utf-8")
