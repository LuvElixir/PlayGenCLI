"""Tests for playgen.godot.visibility — invisible node detection.

This is the core defense against the #1 Agent failure mode:
"20 commands succeed but nothing appears on screen."
"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from playgen.cli import main
from playgen.godot.tscn import Scene, write_tscn
from playgen.godot.visibility import check_visibility, VISUAL_TYPES, NEEDS_VISUAL


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


# ─── Core visibility detection ──────────────────────────────────────────

class TestVisibilityChecker:
    def test_body_without_visual_warns(self):
        """CharacterBody2D without Sprite2D/Polygon2D → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy", "CharacterBody2D", parent=".")
        scene.add_node("EnemyCol", "CollisionShape2D", parent="Enemy")

        report = check_visibility(scene, "test.tscn")
        assert report.has_issues
        warnings = [w for w in report.warnings if w.node_name == "Enemy"]
        assert len(warnings) == 1
        assert "visual" in warnings[0].message.lower()

    def test_body_with_sprite_ok(self):
        """CharacterBody2D with Sprite2D child → no warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        scene.add_node("PlayerSprite", "Sprite2D", parent="Player")
        scene.add_node("PlayerCol", "CollisionShape2D", parent="Player")

        report = check_visibility(scene, "test.tscn")
        body_warnings = [w for w in report.warnings if w.node_name == "Player"]
        assert len(body_warnings) == 0

    def test_body_with_polygon_ok(self):
        """CharacterBody2D with Polygon2D child → no warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        scene.add_node("PlayerVisual", "Polygon2D", parent="Player")

        report = check_visibility(scene, "test.tscn")
        body_warnings = [w for w in report.warnings if w.node_name == "Player"]
        assert len(body_warnings) == 0

    def test_area2d_without_visual_warns(self):
        """Area2D without visual child → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Trigger", "Area2D", parent=".")
        scene.add_node("TriggerCol", "CollisionShape2D", parent="Trigger")

        report = check_visibility(scene, "test.tscn")
        assert any(w.node_name == "Trigger" for w in report.warnings)

    def test_staticbody_without_visual_warns(self):
        """StaticBody2D without visual child → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Wall", "StaticBody2D", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert any(w.node_name == "Wall" for w in report.warnings)

    def test_rigidbody_without_visual_warns(self):
        """RigidBody2D without visual child → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Ball", "RigidBody2D", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert any(w.node_name == "Ball" for w in report.warnings)

    def test_instance_node_ok(self):
        """Instance nodes don't warn (they may contain visual children internally)."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        ext = scene.add_ext_resource("PackedScene", "res://enemy.tscn")
        node = scene.add_node("Enemy1", "", parent=".")
        node.instance_id = ext.id

        report = check_visibility(scene, "test.tscn")
        assert not any(w.node_name == "Enemy1" and w.severity == "warning"
                       for w in report.warnings)

    def test_visual_node_ok(self):
        """Pure visual nodes (Sprite2D, Label) don't warn."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("MySprite", "Sprite2D", parent=".")
        scene.add_node("MyLabel", "Label", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert not report.has_issues

    def test_invisible_ok_types(self):
        """Timer, Camera2D, AudioStreamPlayer, etc. don't warn."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Timer", "Timer", parent=".")
        scene.add_node("Camera", "Camera2D", parent=".")
        scene.add_node("Audio", "AudioStreamPlayer", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert not report.has_issues

    def test_nested_visual_child(self):
        """Body with visual grandchild (nested) → no warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        scene.add_node("Visuals", "Node2D", parent="Player")
        scene.add_node("Sprite", "Sprite2D", parent="Player/Visuals")

        report = check_visibility(scene, "test.tscn")
        body_warnings = [w for w in report.warnings if w.node_name == "Player"]
        assert len(body_warnings) == 0

    def test_multiple_invisible_nodes(self):
        """Multiple invisible body nodes → multiple warnings."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy1", "CharacterBody2D", parent=".")
        scene.add_node("Enemy2", "CharacterBody2D", parent=".")
        scene.add_node("Enemy3", "CharacterBody2D", parent=".")

        report = check_visibility(scene, "test.tscn")
        body_warnings = [w for w in report.warnings if w.severity == "warning"]
        assert len(body_warnings) == 3

    def test_3d_body_without_visual_warns(self):
        """CharacterBody3D without MeshInstance3D → warning."""
        scene = Scene()
        scene.add_node("Main", "Node3D")
        scene.add_node("Player3D", "CharacterBody3D", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert any(w.node_name == "Player3D" for w in report.warnings)

    def test_3d_body_with_mesh_ok(self):
        """CharacterBody3D with MeshInstance3D → no warning."""
        scene = Scene()
        scene.add_node("Main", "Node3D")
        scene.add_node("Player3D", "CharacterBody3D", parent=".")
        scene.add_node("Mesh", "MeshInstance3D", parent="Player3D")

        report = check_visibility(scene, "test.tscn")
        body_warnings = [w for w in report.warnings if w.node_name == "Player3D"]
        assert len(body_warnings) == 0


# ─── File existence checks ──────────────────────────────────────────────

class TestFileExistenceChecks:
    def test_missing_script_warns(self, project):
        """Missing script file → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_ext_resource("Script", "res://nonexistent.gd")

        report = check_visibility(scene, "test.tscn", project)
        assert any("nonexistent.gd" in w.message for w in report.warnings)

    def test_existing_script_no_warn(self, project):
        """Existing script file → no warning."""
        (project / "player.gd").write_text("extends Node\n", encoding="utf-8")
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_ext_resource("Script", "res://player.gd")

        report = check_visibility(scene, "test.tscn", project)
        assert not any("player.gd" in w.message for w in report.warnings)

    def test_missing_instance_warns(self, project):
        """Instance referencing non-existent .tscn → warning."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        ext = scene.add_ext_resource("PackedScene", "res://missing.tscn")
        node = scene.add_node("Enemy1", "", parent=".")
        node.instance_id = ext.id

        report = check_visibility(scene, "test.tscn", project)
        assert any("missing.tscn" in w.message for w in report.warnings)


# ─── Report structure ───────────────────────────────────────────────────

class TestVisibilityReport:
    def test_summary_no_issues(self):
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Sprite", "Sprite2D", parent=".")

        report = check_visibility(scene, "test.tscn")
        assert "OK" in report.summary()

    def test_to_dict(self):
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy", "CharacterBody2D", parent=".")

        report = check_visibility(scene, "test.tscn")
        d = report.to_dict()
        assert "warnings" in d
        assert d["scene"] == "test.tscn"
        assert d["invisible_count"] >= 1


# ─── Integration with analyze ───────────────────────────────────────────

class TestAnalyzeVisibility:
    def test_analyze_check_visibility(self, project, runner):
        """analyze --check-visibility should show warnings."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project), "analyze", "--check-visibility",
        ])
        assert result.exit_code == 0
        assert "Visibility" in result.output
        assert "Enemy" in result.output

    def test_analyze_check_visibility_json(self, project, runner):
        """analyze --check-visibility --json-output includes warnings."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project), "analyze", "--check-visibility",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "visibility_warnings" in data
        assert len(data["visibility_warnings"]) > 0

    def test_analyze_no_visibility_flag(self, project, runner):
        """analyze without --check-visibility should not include warnings."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Enemy", "CharacterBody2D", parent=".")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project), "analyze", "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "visibility_warnings" not in data

    def test_analyze_scene_check_visibility(self, project, runner):
        """analyze --scene X --check-visibility works."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Ghost", "Area2D", parent=".")
        (project / "level.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project), "analyze", "-s", "level",
            "--check-visibility",
        ])
        assert result.exit_code == 0
        assert "Ghost" in result.output

    def test_analyze_all_ok(self, project, runner):
        """analyze --check-visibility with clean scene says OK."""
        scene = Scene()
        scene.add_node("Main", "Node2D")
        scene.add_node("Player", "CharacterBody2D", parent=".")
        scene.add_node("Visual", "Polygon2D", parent="Player")
        (project / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")

        result = runner.invoke(main, [
            "--project", str(project), "analyze", "--check-visibility",
        ])
        assert result.exit_code == 0
        assert "all nodes OK" in result.output


# ─── Integration with build ─────────────────────────────────────────────

class TestBuildVisibility:
    def test_build_auto_visual_placeholder(self, project, runner):
        """build should auto-create visual placeholder for body nodes."""
        desc = json.dumps({
            "scene": "test.tscn",
            "root": {
                "name": "Main", "type": "Node2D",
                "children": [
                    {"name": "Enemy", "type": "CharacterBody2D"},
                ],
            },
        })
        result = runner.invoke(main, ["--project", str(project), "build", "-"], input=desc)
        assert result.exit_code == 0
        assert "Enemy" in result.output
        assert "placeholder" in result.output.lower()

    def test_build_auto_visual_json(self, project, runner):
        """build --json-output includes auto_visuals for body nodes."""
        desc = json.dumps({
            "scene": "test.tscn",
            "root": {
                "name": "Main", "type": "Node2D",
                "children": [
                    {"name": "Ghost", "type": "Area2D"},
                ],
            },
        })
        result = runner.invoke(main, [
            "--project", str(project), "build", "--json-output", "-",
        ], input=desc)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "auto_visuals" in data
        assert "Ghost" in data["auto_visuals"]
        # No visibility_warnings because auto-visual fixed it
        assert "visibility_warnings" not in data

    def test_build_no_warn_with_visual(self, project, runner):
        """build with visual children → no visibility warnings."""
        desc = json.dumps({
            "scene": "test.tscn",
            "root": {
                "name": "Main", "type": "Node2D",
                "children": [
                    {
                        "name": "Player", "type": "CharacterBody2D",
                        "children": [
                            {"name": "Visual", "type": "Polygon2D"},
                        ],
                    },
                ],
            },
        })
        result = runner.invoke(main, [
            "--project", str(project), "build", "--json-output", "-",
        ], input=desc)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "visibility_warnings" not in data


# ─── Screenshot (unit tests, no Godot) ──────────────────────────────────

class TestScreenshotSetup:
    def test_inject_creates_script(self, project):
        """inject_screenshot creates the capture script."""
        from playgen.godot.observe import inject_screenshot, remove_screenshot
        from playgen.godot.observe import SCREENSHOT_SCRIPT_NAME

        inject_screenshot(project, frames=30)
        assert (project / SCREENSHOT_SCRIPT_NAME).exists()

        # Verify autoload was added to project.godot
        content = (project / "project.godot").read_text()
        assert "PlayGenScreenshot" in content

        # Cleanup
        remove_screenshot(project)
        assert not (project / SCREENSHOT_SCRIPT_NAME).exists()

        # Verify autoload was removed
        content = (project / "project.godot").read_text()
        assert "PlayGenScreenshot" not in content

    def test_screenshot_script_has_capture(self, project):
        """Screenshot script contains viewport capture logic."""
        from playgen.godot.observe import SCREENSHOT_SCRIPT

        assert "get_viewport" in SCREENSHOT_SCRIPT
        assert "save_png" in SCREENSHOT_SCRIPT
        assert "get_tree().quit()" in SCREENSHOT_SCRIPT
