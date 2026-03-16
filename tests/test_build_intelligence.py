"""Tests for build intelligence features (v0.7.0).

Covers: type inference, auto-visual placeholders, text/color/size shorthands,
collision_layer/mask, template variables.
"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from playgen.cli import main
from playgen.godot.tscn import parse_tscn


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="Test"\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def runner():
    return CliRunner()


def _build(runner, project, build_json: dict) -> tuple:
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


# ─── Type inference ───────────────────────────────────────────────────

class TestTypeInference:

    def test_texture_infers_sprite2d(self, runner, project):
        """Node with texture but no type → Sprite2D."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Icon", "texture": "icon.png"}
            ]}
        })
        icon = scene.find_node("Icon")
        assert icon.type == "Sprite2D"

    def test_audio_infers_audiostreamplayer(self, runner, project):
        """Node with audio but no type → AudioStreamPlayer."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "BGM", "audio": "music.ogg"}
            ]}
        })
        bgm = scene.find_node("BGM")
        assert bgm.type == "AudioStreamPlayer"

    def test_text_infers_label(self, runner, project):
        """Node with text but no type → Label."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Title", "text": "Hello World"}
            ]}
        })
        title = scene.find_node("Title")
        assert title.type == "Label"

    def test_explicit_type_overrides(self, runner, project):
        """Explicit type is always used even with shorthands."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Btn", "type": "Button", "text": "Click Me"}
            ]}
        })
        btn = scene.find_node("Btn")
        assert btn.type == "Button"


# ─── Auto-visual placeholders ─────────────────────────────────────────

class TestAutoVisual:

    def test_body_without_visual_gets_polygon(self, runner, project):
        """CharacterBody2D without visual → auto Polygon2D child."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D"}
            ]}
        })
        visual = scene.find_node("PlayerVisual")
        assert visual is not None
        assert visual.type == "Polygon2D"
        assert "color" in visual.properties
        assert "polygon" in visual.properties

    def test_body_with_visual_no_auto(self, runner, project):
        """CharacterBody2D with Sprite2D child → no auto-visual."""
        result, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D", "children": [
                    {"name": "Sprite", "type": "Sprite2D"}
                ]}
            ]}
        })
        data = json.loads(result.output)
        assert "auto_visuals" not in data
        # No PlayerVisual auto-created
        assert scene.find_node("PlayerVisual") is None

    def test_auto_visual_json_output(self, runner, project):
        """auto_visuals array in JSON output."""
        result, _ = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Enemy", "type": "Area2D"},
                {"name": "Wall", "type": "StaticBody2D"},
            ]}
        })
        data = json.loads(result.output)
        assert "auto_visuals" in data
        assert "Enemy" in data["auto_visuals"]
        assert "Wall" in data["auto_visuals"]

    def test_auto_visual_with_shape_uses_size(self, runner, project):
        """Auto-visual polygon scales to match the collision shape."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "shape": "RectangleShape2D:60,80"}
            ]}
        })
        visual = scene.find_node("PlayerVisual")
        assert visual is not None
        # Should use half the shape size: 30, 40
        assert "30" in visual.properties["polygon"]
        assert "40" in visual.properties["polygon"]

    def test_auto_visual_different_colors(self, runner, project):
        """Multiple body nodes get different placeholder colors."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "A", "type": "CharacterBody2D"},
                {"name": "B", "type": "CharacterBody2D"},
            ]}
        })
        a_visual = scene.find_node("AVisual")
        b_visual = scene.find_node("BVisual")
        assert a_visual.properties["color"] != b_visual.properties["color"]

    def test_instance_no_auto_visual(self, runner, project):
        """Instance nodes don't get auto-visual (they may contain visuals)."""
        result, _ = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "E1", "type": "CharacterBody2D", "instance": "enemy.tscn"}
            ]}
        })
        data = json.loads(result.output)
        assert "auto_visuals" not in data


# ─── Text shorthand ───────────────────────────────────────────────────

class TestTextShorthand:

    def test_label_text(self, runner, project):
        """text shorthand sets text property on Label."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Title", "type": "Label", "text": "Hello World"}
            ]}
        })
        title = scene.find_node("Title")
        assert title.properties["text"] == '"Hello World"'

    def test_button_text(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Btn", "type": "Button", "text": "Start"}
            ]}
        })
        btn = scene.find_node("Btn")
        assert btn.properties["text"] == '"Start"'


# ─── Color shorthand ──────────────────────────────────────────────────

class TestColorShorthand:

    def test_polygon_color(self, runner, project):
        """color shorthand on Polygon2D sets color property."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "P", "type": "Polygon2D",
                 "color": "Color(1, 0, 0, 1)"}
            ]}
        })
        p = scene.find_node("P")
        assert p.properties["color"] == "Color(1, 0, 0, 1)"

    def test_colorrect_color(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "BG", "type": "ColorRect",
                 "color": "Color(0.2, 0.2, 0.2, 1)"}
            ]}
        })
        bg = scene.find_node("BG")
        assert bg.properties["color"] == "Color(0.2, 0.2, 0.2, 1)"

    def test_other_node_modulate(self, runner, project):
        """color shorthand on non-Polygon/ColorRect sets modulate."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "S", "type": "Sprite2D",
                 "color": "Color(1, 0.5, 0, 1)"}
            ]}
        })
        s = scene.find_node("S")
        assert s.properties["modulate"] == "Color(1, 0.5, 0, 1)"


# ─── Size shorthand ───────────────────────────────────────────────────

class TestSizeShorthand:

    def test_size_list(self, runner, project):
        """size shorthand as [w, h] → custom_minimum_size."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Control", "children": [
                {"name": "Panel", "type": "Panel", "size": [200, 100]}
            ]}
        })
        panel = scene.find_node("Panel")
        assert panel.properties["custom_minimum_size"] == "Vector2(200, 100)"

    def test_size_string(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Control", "children": [
                {"name": "Panel", "type": "Panel",
                 "size": "Vector2(300, 150)"}
            ]}
        })
        panel = scene.find_node("Panel")
        assert panel.properties["custom_minimum_size"] == "Vector2(300, 150)"


# ─── Collision layer/mask ──────────────────────────────────────────────

class TestCollisionLayers:

    def test_collision_layer_int(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "collision_layer": 3}
            ]}
        })
        player = scene.find_node("Player")
        assert player.properties["collision_layer"] == "3"

    def test_collision_layer_list(self, runner, project):
        """Layer numbers [1, 3] → bitmask 5 (bit 0 + bit 2)."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "collision_layer": [1, 3]}
            ]}
        })
        player = scene.find_node("Player")
        assert player.properties["collision_layer"] == "5"

    def test_collision_mask_int(self, runner, project):
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "collision_mask": 6}
            ]}
        })
        player = scene.find_node("Player")
        assert player.properties["collision_mask"] == "6"

    def test_collision_mask_list(self, runner, project):
        """Mask [2, 4] → bitmask 10 (bit 1 + bit 3)."""
        _, scene = _build(runner, project, {
            "root": {"name": "Root", "type": "Node2D", "children": [
                {"name": "Player", "type": "CharacterBody2D",
                 "collision_mask": [2, 4]}
            ]}
        })
        player = scene.find_node("Player")
        assert player.properties["collision_mask"] == "10"


# ─── Template variables ───────────────────────────────────────────────

class TestTemplateVars:

    def test_platformer_custom_speed(self, runner, project):
        """Template vars override defaults in platformer-player template."""
        _build(runner, project, {
            "scripts": {
                "player.gd": {
                    "template": "platformer-player",
                    "vars": {"SPEED": "500.0", "JUMP_VELOCITY": "-600.0"}
                }
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "SPEED = 500.0" in gd
        assert "JUMP_VELOCITY = -600.0" in gd

    def test_platformer_default_speed(self, runner, project):
        """Without vars, platformer-player uses default speed values."""
        _build(runner, project, {
            "scripts": {
                "player.gd": {"template": "platformer-player"}
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "SPEED = 300.0" in gd
        assert "JUMP_VELOCITY = -450.0" in gd

    def test_topdown_custom_speed(self, runner, project):
        _build(runner, project, {
            "scripts": {
                "player.gd": {
                    "template": "topdown-player",
                    "vars": {"SPEED": "350.0"}
                }
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "SPEED = 350.0" in gd

    def test_extends_default_with_vars(self, runner, project):
        """extends-based templates also support vars."""
        _build(runner, project, {
            "scripts": {
                "player.gd": {
                    "extends": "CharacterBody2D",
                    "vars": {"SPEED": "400.0"}
                }
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "SPEED = 400.0" in gd

    def test_partial_vars(self, runner, project):
        """Providing some vars fills defaults for the rest."""
        _build(runner, project, {
            "scripts": {
                "player.gd": {
                    "template": "platformer-player",
                    "vars": {"SPEED": "999.0"}
                }
            },
            "root": {"name": "Root", "type": "Node2D"},
        })
        gd = (project / "player.gd").read_text(encoding="utf-8")
        assert "SPEED = 999.0" in gd
        assert "JUMP_VELOCITY = -450.0" in gd  # default


# ─── Combined features ────────────────────────────────────────────────

class TestBuildCombined:

    def test_full_build_with_intelligence(self, runner, project):
        """End-to-end build using multiple intelligence features."""
        result, scene = _build(runner, project, {
            "scene": "game.tscn",
            "scripts": {
                "player.gd": {
                    "template": "topdown-player",
                    "vars": {"SPEED": "250.0"}
                }
            },
            "root": {
                "name": "Main", "type": "Node2D",
                "children": [
                    {
                        "name": "Player", "type": "CharacterBody2D",
                        "script": "player.gd",
                        "shape": "RectangleShape2D:32,48",
                        "collision_layer": [1],
                        "collision_mask": [1, 2],
                        "children": [
                            {"name": "Sprite", "type": "Sprite2D"}
                        ]
                    },
                    {"name": "Title", "text": "My Game"},
                    {"name": "Icon", "texture": "icon.png"},
                    {"name": "Enemy", "type": "Area2D",
                     "collision_layer": [2]},
                ],
            },
        })
        data = json.loads(result.output)
        assert result.exit_code == 0
        assert data["node_count"] >= 6  # Root + Player + children + Title + Icon + Enemy

        # Player has collision layer/mask
        player = scene.find_node("Player")
        assert player.properties["collision_layer"] == "1"
        assert player.properties["collision_mask"] == "3"  # [1,2] = bit0+bit1 = 3

        # Player has no auto-visual (has Sprite child)
        assert "auto_visuals" not in data or "Player" not in data.get("auto_visuals", [])

        # Title inferred as Label
        title = scene.find_node("Title")
        assert title.type == "Label"

        # Icon inferred as Sprite2D
        icon = scene.find_node("Icon")
        assert icon.type == "Sprite2D"

        # Enemy got auto-visual
        assert "auto_visuals" in data
        assert "Enemy" in data["auto_visuals"]
