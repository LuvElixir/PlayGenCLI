"""Tests for playgen.godot.project_file — project.godot parser/writer.

Critical: multi-line value handling (input maps with {}).
"""

import pytest
from playgen.godot.project_file import (
    parse_project_file,
    write_project_file,
    GodotProject,
)


MINIMAL_PROJECT = """\
; Engine configuration file.

config_version=5

[application]

config/name="Test Game"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.3", "GL Compatibility")
"""

PROJECT_WITH_AUTOLOADS = """\
config_version=5

[application]

config/name="My Game"

[autoload]

GameManager="*res://game_manager.gd"
AudioBus="*res://audio_bus.gd"
"""

PROJECT_WITH_INPUT_MAP = """\
config_version=5

[application]

config/name="Input Test"

[input]

jump={
"deadzone": 0.2,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":32,"location":0,"echo":false,"script":null)]
}
move_left={
"deadzone": 0.2,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":65,"location":0,"echo":false,"script":null)]
}
"""

PROJECT_WITH_DISPLAY = """\
config_version=5

[application]

config/name="Display Test"

[display]

window/size/viewport_width=1920
window/size/viewport_height=1080
window/stretch/mode="canvas_items"
"""


class TestParseProjectFile:

    def test_parse_minimal(self):
        proj = parse_project_file(MINIMAL_PROJECT)
        assert proj.config_version == 5
        assert proj.name == "Test Game"
        assert proj.main_scene == "res://main.tscn"

    def test_parse_features(self):
        proj = parse_project_file(MINIMAL_PROJECT)
        assert "4.3" in proj.features
        assert "GL Compatibility" in proj.features

    def test_parse_autoloads(self):
        proj = parse_project_file(PROJECT_WITH_AUTOLOADS)
        assert proj.get("autoload", "GameManager") == '"*res://game_manager.gd"'
        assert proj.get("autoload", "AudioBus") == '"*res://audio_bus.gd"'

    def test_parse_multi_line_input(self):
        """Critical: input maps use multi-line {} values."""
        proj = parse_project_file(PROJECT_WITH_INPUT_MAP)
        jump = proj.get("input", "jump")
        assert jump != ""
        assert '"deadzone": 0.2' in jump
        assert "InputEventKey" in jump
        # Must contain the full multi-line value including closing brace
        assert jump.endswith("}")

    def test_parse_display_settings(self):
        proj = parse_project_file(PROJECT_WITH_DISPLAY)
        assert proj.get("display", "window/size/viewport_width") == "1920"
        assert proj.get("display", "window/size/viewport_height") == "1080"

    def test_parse_comments_ignored(self):
        content = """\
; This is a comment
config_version=5

[application]

; Another comment
config/name="Test"
"""
        proj = parse_project_file(content)
        assert proj.name == "Test"

    def test_parse_empty_sections(self):
        """Sections without keys are not tracked (correct behavior)."""
        content = """\
config_version=5

[application]

config/name="Test"

[rendering]
"""
        proj = parse_project_file(content)
        assert "application" in proj.sections
        # rendering has no keys, so it's not in sections
        assert "rendering" not in proj.sections


class TestWriteProjectFile:

    def test_write_minimal(self):
        proj = GodotProject()
        proj.name = "Test"
        output = write_project_file(proj)
        assert "config_version=5" in output
        assert '[application]' in output
        assert 'config/name="Test"' in output

    def test_write_preserves_section_order(self):
        """Preferred sections should come first."""
        proj = GodotProject()
        proj.set("rendering", "a", "1")
        proj.set("application", "b", "2")
        proj.set("autoload", "c", "3")
        output = write_project_file(proj)
        app_pos = output.index("[application]")
        auto_pos = output.index("[autoload]")
        rend_pos = output.index("[rendering]")
        assert app_pos < auto_pos < rend_pos


class TestProjectFileRoundTrip:

    def _roundtrip(self, content: str) -> GodotProject:
        proj = parse_project_file(content)
        written = write_project_file(proj)
        return parse_project_file(written)

    def test_roundtrip_minimal(self):
        proj = self._roundtrip(MINIMAL_PROJECT)
        assert proj.name == "Test Game"
        assert proj.main_scene == "res://main.tscn"

    def test_roundtrip_autoloads(self):
        proj = self._roundtrip(PROJECT_WITH_AUTOLOADS)
        assert '"*res://game_manager.gd"' in proj.get("autoload", "GameManager")

    def test_roundtrip_multi_line_input(self):
        """Multi-line values must survive round-trip."""
        proj = self._roundtrip(PROJECT_WITH_INPUT_MAP)
        jump = proj.get("input", "jump")
        assert "InputEventKey" in jump
        assert '"deadzone": 0.2' in jump

    def test_roundtrip_display(self):
        proj = self._roundtrip(PROJECT_WITH_DISPLAY)
        assert proj.get("display", "window/size/viewport_width") == "1920"


class TestGodotProjectHelpers:

    def test_set_and_get(self):
        proj = GodotProject()
        proj.set("display", "window/size/viewport_width", "1280")
        assert proj.get("display", "window/size/viewport_width") == "1280"

    def test_delete(self):
        proj = GodotProject()
        proj.set("autoload", "GM", '"*res://gm.gd"')
        assert proj.delete("autoload", "GM") is True
        assert proj.get("autoload", "GM") == ""

    def test_delete_missing(self):
        proj = GodotProject()
        assert proj.delete("autoload", "Nonexistent") is False

    def test_remove_alias(self):
        proj = GodotProject()
        proj.set("autoload", "GM", '"*res://gm.gd"')
        assert proj.remove("autoload", "GM") is True

    def test_name_property(self):
        proj = GodotProject()
        proj.name = "My Game"
        assert proj.name == "My Game"
        assert proj.get("application", "config/name") == '"My Game"'

    def test_main_scene_property(self):
        proj = GodotProject()
        proj.main_scene = "res://main.tscn"
        assert proj.main_scene == "res://main.tscn"

    def test_to_dict(self):
        proj = parse_project_file(MINIMAL_PROJECT)
        d = proj.to_dict()
        assert d["name"] == "Test Game"
        assert "sections" in d
