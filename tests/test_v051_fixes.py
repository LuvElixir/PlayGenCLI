"""Tests for v0.5.2 fixes — Shadow Harvest feedback.

Covers: P0-1 (build error output), P0-2 (mouse/joypad input),
P0-3 (autoload warnings), P1-2 (template fix), P1-4 (node path),
P1-5 (instance display), P1-6 (script attach warning),
P1-8 (analyze autoload).
"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from playgen.cli import main
from playgen.godot.tscn import Scene, parse_tscn, write_tscn


@pytest.fixture
def project(tmp_path):
    """Create a minimal Godot project."""
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="Test"\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def runner():
    return CliRunner()


# ─── P0-1: build error output ───────────────────────────────────────────

class TestBuildErrorOutput:
    def test_invalid_json_text_mode(self, project, runner):
        """Build with bad JSON should output error to stdout (not just stderr)."""
        bad_json = "{invalid json"
        result = runner.invoke(main, ["--project", str(project), "build", "-"], input=bad_json)
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_invalid_json_json_mode(self, project, runner):
        """Build with bad JSON in --json-output mode should output JSON error."""
        bad_json = "{invalid json"
        result = runner.invoke(main, ["--project", str(project), "build", "--json-output", "-"], input=bad_json)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data

    def test_missing_root_text_mode(self, project, runner):
        """Build with missing root node should output error to stdout."""
        desc = json.dumps({"scene": "test.tscn"})
        result = runner.invoke(main, ["--project", str(project), "build", "-"], input=desc)
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_success_outputs_summary(self, project, runner):
        """Successful build should always output a summary."""
        desc = json.dumps({
            "scene": "test.tscn",
            "root": {"name": "Main", "type": "Node2D"},
        })
        result = runner.invoke(main, ["--project", str(project), "build", "-"], input=desc)
        assert result.exit_code == 0
        assert "Built scene successfully" in result.output


# ─── P0-2: mouse/joypad input ───────────────────────────────────────────

class TestInputMouseJoypad:
    def test_mouse_option(self, project, runner):
        """--mouse/-m adds mouse input events."""
        result = runner.invoke(main, [
            "--project", str(project), "input", "add", "shoot", "-m", "left",
        ])
        assert result.exit_code == 0
        assert "mouse_left" in result.output

    def test_joypad_option(self, project, runner):
        """--joypad/-j adds joypad input events."""
        result = runner.invoke(main, [
            "--project", str(project), "input", "add", "jump", "-j", "a",
        ])
        assert result.exit_code == 0
        assert "joypad_a" in result.output

    def test_mixed_bindings(self, project, runner):
        """Can mix -k, -m, -j in one command."""
        result = runner.invoke(main, [
            "--project", str(project), "input", "add", "attack",
            "-k", "z", "-m", "left", "-j", "x",
        ])
        assert result.exit_code == 0
        assert "z" in result.output
        assert "mouse_left" in result.output
        assert "joypad_x" in result.output

    def test_no_bindings_error(self, project, runner):
        """input add without any binding options should error."""
        result = runner.invoke(main, [
            "--project", str(project), "input", "add", "fire",
        ])
        assert result.exit_code != 0

    def test_mouse_event_in_project(self, project, runner):
        """Mouse binding should produce InputEventMouseButton in project.godot."""
        runner.invoke(main, [
            "--project", str(project), "input", "add", "click", "-m", "left",
        ])
        content = (project / "project.godot").read_text()
        assert "InputEventMouseButton" in content

    def test_joypad_event_in_project(self, project, runner):
        """Joypad binding should produce InputEventJoypadButton in project.godot."""
        runner.invoke(main, [
            "--project", str(project), "input", "add", "action", "-j", "a",
        ])
        content = (project / "project.godot").read_text()
        assert "InputEventJoypadButton" in content

    def test_key_still_works(self, project, runner):
        """The original -k option should continue to work."""
        result = runner.invoke(main, [
            "--project", str(project), "input", "add", "jump", "-k", "space",
        ])
        assert result.exit_code == 0
        content = (project / "project.godot").read_text()
        assert "InputEventKey" in content


# ─── P0-3: autoload awareness ───────────────────────────────────────────

class TestAutoloadWarnings:
    def test_check_autoload_refs(self, project):
        """_check_autoload_refs should detect autoload references in scripts."""
        from playgen.godot.bridge import _check_autoload_refs

        # Set up autoload in project.godot
        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Test"\n\n'
            '[autoload]\n\nGameManager="*res://game_manager.gd"\n',
            encoding="utf-8",
        )
        # Create a script that references GameManager
        (project / "player.gd").write_text(
            'extends CharacterBody2D\n\nfunc _ready():\n\tGameManager.start_game()\n',
            encoding="utf-8",
        )
        warnings = _check_autoload_refs(project, "res://player.gd")
        assert len(warnings) == 1
        assert "GameManager" in warnings[0]

    def test_no_autoload_no_warning(self, project):
        """No warnings when no autoloads configured."""
        from playgen.godot.bridge import _check_autoload_refs

        (project / "player.gd").write_text(
            'extends CharacterBody2D\n\nfunc _ready():\n\tpass\n',
            encoding="utf-8",
        )
        warnings = _check_autoload_refs(project, "res://player.gd")
        assert len(warnings) == 0

    def test_no_warning_when_not_referenced(self, project):
        """No warning when autoload exists but isn't referenced in script."""
        from playgen.godot.bridge import _check_autoload_refs

        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Test"\n\n'
            '[autoload]\n\nGameManager="*res://game_manager.gd"\n',
            encoding="utf-8",
        )
        (project / "player.gd").write_text(
            'extends CharacterBody2D\n\nfunc _ready():\n\tpass\n',
            encoding="utf-8",
        )
        warnings = _check_autoload_refs(project, "res://player.gd")
        assert len(warnings) == 0


# ─── P1-2: CharacterBody2D template ─────────────────────────────────────

class TestCharacterBody2DTemplate:
    def test_no_gravity_in_default(self):
        """CharacterBody2D default template should not include gravity."""
        from playgen.templates import EXTENDS_DEFAULTS
        template = EXTENDS_DEFAULTS["CharacterBody2D"]
        assert "gravity" not in template
        assert "JUMP_VELOCITY" not in template

    def test_has_move_and_slide(self):
        """CharacterBody2D default template should include move_and_slide."""
        from playgen.templates import EXTENDS_DEFAULTS
        template = EXTENDS_DEFAULTS["CharacterBody2D"]
        assert "move_and_slide" in template

    def test_platformer_template_still_exists(self):
        """Platformer template should still be available explicitly."""
        from playgen.templates import SCRIPT_TEMPLATES
        assert "platformer-player" in SCRIPT_TEMPLATES
        template = SCRIPT_TEMPLATES["platformer-player"]
        assert "gravity" in template
        assert "JUMP_VELOCITY" in template


# ─── P1-4: find_node with paths ─────────────────────────────────────────

class TestFindNodePath:
    def test_find_by_name(self):
        """find_node still works with simple name."""
        scene = Scene()
        scene.add_node("Root", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        assert scene.find_node("Player") is not None

    def test_find_by_path(self):
        """find_node supports path format like 'HUD/HealthLabel'."""
        scene = Scene()
        scene.add_node("Root", "Node2D")
        scene.add_node("HUD", "CanvasLayer", parent=".")
        scene.add_node("HealthLabel", "Label", parent="HUD")

        node = scene.find_node("HUD/HealthLabel")
        assert node is not None
        assert node.name == "HealthLabel"

    def test_find_path_not_found(self):
        """find_node returns None for non-existent path."""
        scene = Scene()
        scene.add_node("Root", "Node2D")
        scene.add_node("HUD", "CanvasLayer", parent=".")

        assert scene.find_node("HUD/NonExistent") is None

    def test_find_disambiguates_same_name(self):
        """find_node with path disambiguates nodes with same name."""
        scene = Scene()
        scene.add_node("Root", "Node2D")
        scene.add_node("Panel", "Control", parent=".")
        scene.add_node("Label", "Label", parent="Panel")
        scene.add_node("HUD", "CanvasLayer", parent=".")
        scene.add_node("Label", "Label", parent="HUD")

        node = scene.find_node("HUD/Label")
        assert node is not None
        assert node.parent == "HUD"


# ─── P1-5: instance type in scene tree ──────────────────────────────────

class TestInstanceDisplay:
    def test_instance_shows_source(self, project, runner):
        """scene tree should show instance source path, not empty ()."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        ext = scene.add_ext_resource("PackedScene", "res://enemy.tscn")
        node = scene.add_node("Enemy1", "", parent=".")
        node.instance_id = ext.id
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, ["--project", str(project), "scene", "tree", "main"])
        assert result.exit_code == 0
        assert "instance=" in result.output
        assert "enemy.tscn" in result.output
        assert "Enemy1 ()" not in result.output


# ─── P1-6: script attach missing file warning ───────────────────────────

class TestScriptAttachWarning:
    def test_warns_missing_script(self, project, runner):
        """script attach should warn when script file doesn't exist."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project),
            "script", "attach", "main", "-n", "Player", "-s", "nonexistent.gd",
        ])
        # Should still succeed (attach works) but warn
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_warns_missing_script_json(self, project, runner):
        """script attach in JSON mode includes warning for missing script."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project),
            "script", "attach", "main", "-n", "Player", "-s", "nonexistent.gd",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "warning" in data

    def test_no_warning_existing_script(self, project, runner):
        """No warning when script file exists."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")
        (project / "player.gd").write_text("extends CharacterBody2D\n", encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project),
            "script", "attach", "main", "-n", "Player", "-s", "player.gd",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "warning" not in data


# ─── P1-8: analyze recognizes autoloads ──────────────────────────────────

class TestAnalyzeAutoloads:
    def test_autoload_script_not_unused(self, project, runner):
        """analyze should mark autoloaded scripts as (autoload: Name), not (unused)."""
        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Test"\n\n'
            '[autoload]\n\nGameManager="*res://game_manager.gd"\n',
            encoding="utf-8",
        )
        (project / "game_manager.gd").write_text(
            "extends Node\n\nfunc _ready():\n\tpass\n",
            encoding="utf-8",
        )
        result = runner.invoke(main, ["--project", str(project), "analyze"])
        assert result.exit_code == 0
        assert "(autoload: GameManager)" in result.output
        assert "(unused)" not in result.output

    def test_autoload_in_json(self, project, runner):
        """analyze --json-output includes autoload key."""
        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Test"\n\n'
            '[autoload]\n\nMyGlobal="*res://my_global.gd"\n',
            encoding="utf-8",
        )
        (project / "my_global.gd").write_text("extends Node\n", encoding="utf-8")

        result = runner.invoke(main, ["--project", str(project), "analyze", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        script = next(s for s in data["scripts"] if s["path"] == "my_global.gd")
        assert script["autoload"] == "MyGlobal"


# ─── P2-1: scene create shows root name ─────────────────────────────────

class TestSceneCreateOutput:
    def test_shows_root_name(self, project, runner):
        """scene create should output the root node name."""
        result = runner.invoke(main, [
            "--project", str(project), "scene", "create", "light_orb.tscn", "-r", "Area2D",
        ])
        assert result.exit_code == 0
        assert "LightOrb" in result.output

    def test_json_includes_root_name(self, project, runner):
        """scene create --json-output should include root_name."""
        result = runner.invoke(main, [
            "--project", str(project), "scene", "create", "my_enemy.tscn",
            "-r", "CharacterBody2D", "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["root_name"] == "MyEnemy"
