"""Tests for playgen.commands.build — JSON → scene generation.

Covers: type coercion, script body writing, shape handling,
asset shorthands, project configuration.
"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from playgen.cli import main
from playgen.godot.tscn import parse_tscn, auto_quote_value


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


def _build(runner, project, build_json: dict) -> tuple:
    """Run build and return (result, parsed_scene_if_exists)."""
    json_str = json.dumps(build_json)
    result = runner.invoke(
        main,
        ["--project", str(project), "build", "--json-output", "-"],
        input=json_str,
    )
    scene_path = project / build_json.get("scene", "main.tscn")
    scene = None
    if scene_path.exists():
        scene = parse_tscn(scene_path.read_text(encoding="utf-8"))
    return result, scene


# ─── Type coercion (P0 #4 fix) ──────────────────────────────────────

class TestBuildTypeCoercion:

    def test_bool_true(self, runner, project):
        """JSON true → "true" in .tscn"""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Timer", "type": "Timer", "properties": {
                    "autostart": True
                }}
            ]}
        })
        timer = scene.find_node("Timer")
        assert timer.properties["autostart"] == "true"

    def test_bool_false(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Timer", "type": "Timer", "properties": {
                    "one_shot": False
                }}
            ]}
        })
        timer = scene.find_node("Timer")
        assert timer.properties["one_shot"] == "false"

    def test_int_value(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Timer", "type": "Timer", "properties": {
                    "process_priority": 10
                }}
            ]}
        })
        timer = scene.find_node("Timer")
        assert timer.properties["process_priority"] == "10"

    def test_float_value(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Timer", "type": "Timer", "properties": {
                    "wait_time": 3.5
                }}
            ]}
        })
        timer = scene.find_node("Timer")
        assert timer.properties["wait_time"] == "3.5"

    def test_string_value_gets_quoted(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Label", "type": "Label", "properties": {
                    "text": "Hello World"
                }}
            ]}
        })
        label = scene.find_node("Label")
        assert label.properties["text"] == '"Hello World"'

    def test_constructor_not_quoted(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Sprite", "type": "Sprite2D", "properties": {
                    "position": "Vector2(100, 200)"
                }}
            ]}
        })
        sprite = scene.find_node("Sprite")
        assert sprite.properties["position"] == "Vector2(100, 200)"

    def test_mixed_types(self, runner, project):
        """Multiple properties with different JSON types."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Node", "type": "Node2D", "properties": {
                    "z_index": 5,
                    "visible": True,
                    "rotation": 1.57,
                    "position": "Vector2(0, 0)",
                }}
            ]}
        })
        node = scene.find_node("Node")
        assert node.properties["z_index"] == "5"
        assert node.properties["visible"] == "true"
        assert node.properties["rotation"] == "1.57"
        assert node.properties["position"] == "Vector2(0, 0)"


# ─── Script body writing (P0 #1 fix) ────────────────────────────────

class TestBuildScripts:

    def test_script_body_key(self, runner, project):
        """scripts.body must write content to .gd file."""
        script_content = 'extends Node2D\n\nfunc _ready():\n\tprint("hello")\n'
        _build(runner, project, {
            "scripts": {
                "main.gd": {"body": script_content}
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "main.gd").read_text(encoding="utf-8")
        assert 'print("hello")' in gd

    def test_script_content_key(self, runner, project):
        """scripts.content must also work."""
        script_content = 'extends Node\n\nfunc _process(d):\n\tpass\n'
        _build(runner, project, {
            "scripts": {
                "logic.gd": {"content": script_content}
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "logic.gd").read_text(encoding="utf-8")
        assert "func _process" in gd

    def test_script_inline_string(self, runner, project):
        """scripts value can be a plain string."""
        _build(runner, project, {
            "scripts": {
                "simple.gd": "extends Sprite2D\n"
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "simple.gd").read_text(encoding="utf-8")
        assert gd.startswith("extends Sprite2D")

    def test_script_template(self, runner, project):
        """scripts with template key uses built-in template."""
        _build(runner, project, {
            "scripts": {
                "player.gd": {"template": "platformer-player"}
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "CharacterBody2D" in gd
        assert "move_and_slide" in gd

    def test_script_extends_default(self, runner, project):
        """scripts with just extends uses smart default."""
        _build(runner, project, {
            "scripts": {
                "area.gd": {"extends": "Area2D"}
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "area.gd").read_text(encoding="utf-8")
        assert "extends Area2D" in gd
        assert "body_entered" in gd  # Smart default should include signal

    def test_script_body_takes_priority_over_template(self, runner, project):
        """If both body and template are specified, body wins."""
        _build(runner, project, {
            "scripts": {
                "custom.gd": {
                    "template": "platformer-player",
                    "body": "extends Node\n\nfunc custom():\n\tpass\n"
                }
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "custom.gd").read_text(encoding="utf-8")
        assert "func custom" in gd
        assert "move_and_slide" not in gd  # template NOT used


# ─── Shape handling ──────────────────────────────────────────────────

class TestBuildShapes:

    def test_body_type_gets_collision_child(self, runner, project):
        """Body types must get CollisionShape2D child, not shape property."""
        _, scene = _build(runner, project, {
            "resources": [{"id": "player_shape", "type": "RectangleShape2D",
                          "properties": {"size": "Vector2(28, 44)"}}],
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D", "shape": "player_shape"}
            ]}
        })
        player = scene.find_node("Player")
        assert "shape" not in player.properties  # NOT on the body node
        # Collision child must exist
        collision = scene.find_node("PlayerCollision")
        assert collision is not None
        assert collision.type == "CollisionShape2D"
        assert "SubResource" in collision.properties["shape"]

    def test_inline_shape(self, runner, project):
        """Inline shape syntax: 'RectangleShape2D:30,50'."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "shape": "RectangleShape2D:30,50"}
            ]}
        })
        assert len(scene.sub_resources) == 1
        assert scene.sub_resources[0].type == "RectangleShape2D"
        assert scene.sub_resources[0].properties["size"] == "Vector2(30, 50)"

    def test_circle_shape(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Enemy", "type": "Area2D",
                 "shape": "CircleShape2D:32"}
            ]}
        })
        assert scene.sub_resources[0].type == "CircleShape2D"
        assert scene.sub_resources[0].properties["radius"] == "32"

    def test_3d_body_gets_3d_collision(self, runner, project):
        _, scene = _build(runner, project, {
            "resources": [{"id": "box", "type": "BoxShape3D",
                          "properties": {"size": "Vector3(1, 1, 1)"}}],
            "root": {"name": "Root", "type": "Node3D", "children": [
                {"name": "Body", "type": "CharacterBody3D", "shape": "box"}
            ]}
        })
        collision = scene.find_node("BodyCollision")
        assert collision.type == "CollisionShape3D"


# ─── Asset shorthands ────────────────────────────────────────────────

class TestBuildAssetShorthands:

    def test_texture_shorthand(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Sprite", "type": "Sprite2D", "texture": "icon.png"}
            ]}
        })
        sprite = scene.find_node("Sprite")
        assert "texture" in sprite.properties
        assert "ExtResource" in sprite.properties["texture"]
        assert any(r.path == "res://icon.png" for r in scene.ext_resources)

    def test_audio_shorthand(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "BGM", "type": "AudioStreamPlayer", "audio": "music.ogg"}
            ]}
        })
        bgm = scene.find_node("BGM")
        assert "stream" in bgm.properties
        assert any(r.type == "AudioStream" for r in scene.ext_resources)

    def test_font_shorthand(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Title", "type": "Label", "font": "arial.ttf"}
            ]}
        })
        title = scene.find_node("Title")
        assert "theme_override_fonts/font" in title.properties
        assert any(r.type == "FontFile" for r in scene.ext_resources)

    def test_script_shorthand(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D", "script": "player.gd"}
            ]}
        })
        player = scene.find_node("Player")
        assert "script" in player.properties
        assert any(r.path == "res://player.gd" for r in scene.ext_resources)


# ─── Connections ─────────────────────────────────────────────────────

class TestBuildConnections:

    def test_connections(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Button", "type": "Button"}
            ]},
            "connections": [
                {"signal": "pressed", "from": "Button", "to": ".", "method": "_on_pressed"}
            ]
        })
        assert len(scene.connections) == 1
        assert scene.connections[0].signal_name == "pressed"


# ─── Node tree structure ─────────────────────────────────────────────

class TestBuildNodeTree:

    def test_nested_children(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "A", "type": "Node2D", "children": [
                    {"name": "B", "type": "Sprite2D", "children": [
                        {"name": "C", "type": "Node"}
                    ]}
                ]}
            ]}
        })
        assert len(scene.nodes) == 4
        a = scene.find_node("A")
        assert a.parent == "."
        b = scene.find_node("B")
        assert b.parent == "A"
        c = scene.find_node("C")
        assert c.parent == "A/B"

    def test_groups(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Coin", "type": "Area2D", "groups": ["collectibles", "shiny"]}
            ]}
        })
        coin = scene.find_node("Coin")
        assert coin.groups == ["collectibles", "shiny"]

    def test_instance(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Coin", "instance": "coin.tscn"}
            ]}
        })
        coin = scene.find_node("Coin")
        assert coin.instance_id is not None
        assert any(r.path == "res://coin.tscn" for r in scene.ext_resources)


# ─── Project configuration via build ─────────────────────────────────

class TestBuildConfig:

    def test_autoloads(self, runner, project):
        from playgen.godot.project_file import load_project
        _build(runner, project, {
            "autoloads": {"GameManager": "gm.gd"},
            "root": {"name": "Root", "type": "Node2D"},
        })
        proj = load_project(project)
        assert '"*res://gm.gd"' in proj.get("autoload", "GameManager")

    def test_config_values_quoted(self, runner, project):
        """Config string values must be auto-quoted (P0 #3)."""
        from playgen.godot.project_file import load_project
        _build(runner, project, {
            "config": {"application/config/name": "My Game"},
            "root": {"name": "Root", "type": "Node2D"},
        })
        proj = load_project(project)
        raw = proj.get("application", "config/name")
        assert raw == '"My Game"'

    def test_config_numeric_not_quoted(self, runner, project):
        from playgen.godot.project_file import load_project
        _build(runner, project, {
            "config": {"display/window/size/viewport_width": 1920},
            "root": {"name": "Root", "type": "Node2D"},
        })
        proj = load_project(project)
        assert proj.get("display", "window/size/viewport_width") == "1920"


# ─── Output format ──────────────────────────────────────────────────

class TestBuildOutput:

    def test_json_output_has_created_files(self, runner, project):
        result, _ = _build(runner, project, {
            "scripts": {"test.gd": "extends Node\n"},
            "root": {"name": "Root", "type": "Node2D"},
        })
        data = json.loads(result.output)
        assert "test.gd" in data["created_files"]
        assert "main.tscn" in data["created_files"]

    def test_json_output_has_counts(self, runner, project):
        result, _ = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "A", "type": "Node"},
                {"name": "B", "type": "Node"},
            ]},
        })
        data = json.loads(result.output)
        assert data["node_count"] == 3
