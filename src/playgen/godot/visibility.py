"""Visibility checker for Godot scenes.

Detects nodes that exist in the scene tree but will be invisible at runtime.
This is the #1 failure mode for Agent-built games: 20 commands succeed,
but nothing appears on screen because physics nodes have no visual children.

Rules:
- Physics nodes (CharacterBody2D, Area2D, etc.) without visual children → warning
- Nodes at default position Vector2(0,0) that are not root → hint
- Instance references to non-existent .tscn files → warning
- Script references to non-existent .gd files → warning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from playgen.godot.tscn import Scene, SceneNode, BODY_TYPES


# Node types that produce visible output
VISUAL_TYPES = {
    # 2D visual nodes
    "Sprite2D", "AnimatedSprite2D", "Polygon2D", "Line2D", "MeshInstance2D",
    "MultiMeshInstance2D", "CPUParticles2D", "GPUParticles2D",
    "TileMapLayer", "TileMap",
    "Label", "RichTextLabel", "TextureRect", "ColorRect", "NinePatchRect",
    "Button", "LinkButton", "TextureButton", "OptionButton", "MenuButton",
    "CheckBox", "CheckButton", "SpinBox", "HSlider", "VSlider",
    "ProgressBar", "TextureProgressBar",
    "Panel", "PanelContainer",
    "PointLight2D", "DirectionalLight2D",
    # 3D visual nodes
    "Sprite3D", "AnimatedSprite3D", "MeshInstance3D", "MultiMeshInstance3D",
    "CPUParticles3D", "GPUParticles3D", "CSGBox3D", "CSGSphere3D",
    "CSGCylinder3D", "CSGTorus3D", "CSGMesh3D", "CSGCombiner3D",
    "Label3D", "Decal",
    "OmniLight3D", "SpotLight3D", "DirectionalLight3D",
}

# Node types that are expected to be invisible (don't warn)
INVISIBLE_OK_TYPES = {
    "CollisionShape2D", "CollisionShape3D",
    "CollisionPolygon2D", "CollisionPolygon3D",
    "RayCast2D", "RayCast3D", "ShapeCast2D", "ShapeCast3D",
    "NavigationRegion2D", "NavigationRegion3D",
    "NavigationAgent2D", "NavigationAgent3D",
    "AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D",
    "Timer", "AnimationPlayer", "AnimationTree",
    "Camera2D", "Camera3D",
    "Node", "Node2D", "Node3D", "Control", "CanvasLayer",
    "RemoteTransform2D", "RemoteTransform3D",
    "Marker2D", "Marker3D",
}

# Types that should have visual children to be seen
NEEDS_VISUAL = BODY_TYPES | {
    "CharacterBody2D", "CharacterBody3D",
    "StaticBody2D", "StaticBody3D",
    "RigidBody2D", "RigidBody3D",
    "AnimatableBody2D", "AnimatableBody3D",
    "Area2D", "Area3D",
}


@dataclass
class VisibilityWarning:
    """A single visibility issue detected in a scene."""
    node_name: str
    node_type: str
    severity: str  # "warning" or "hint"
    message: str

    def to_dict(self) -> dict:
        return {
            "node": self.node_name,
            "type": self.node_type,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class VisibilityReport:
    """Result of a visibility check on a scene."""
    scene: str
    warnings: list[VisibilityWarning] = field(default_factory=list)
    node_count: int = 0
    visible_count: int = 0
    invisible_count: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> dict:
        return {
            "scene": self.scene,
            "node_count": self.node_count,
            "visible_count": self.visible_count,
            "invisible_count": self.invisible_count,
            "warnings": [w.to_dict() for w in self.warnings],
        }

    def summary(self) -> str:
        if not self.warnings:
            return f"All {self.node_count} nodes OK"
        warn_count = sum(1 for w in self.warnings if w.severity == "warning")
        hint_count = sum(1 for w in self.warnings if w.severity == "hint")
        parts = []
        if warn_count:
            parts.append(f"{warn_count} warning(s)")
        if hint_count:
            parts.append(f"{hint_count} hint(s)")
        return ", ".join(parts)


def check_visibility(scene: Scene, scene_name: str = "",
                     project_path: Path | None = None) -> VisibilityReport:
    """Check a scene for visibility issues.

    Args:
        scene: Parsed Scene object
        scene_name: Scene filename for reporting
        project_path: Project root for file existence checks
    """
    report = VisibilityReport(scene=scene_name)
    report.node_count = len(scene.nodes)

    root = scene.get_root()
    if not root:
        return report

    # Build parent→children map for efficient lookup
    children_map: dict[str, list[SceneNode]] = {}
    for node in scene.nodes:
        if node.parent is not None:
            parent_key = node.parent
            children_map.setdefault(parent_key, []).append(node)

    for node in scene.nodes:
        # Skip root
        if node.parent is None:
            continue

        # Instance nodes: type is empty, that's OK
        if node.instance_id:
            report.visible_count += 1
            # Check instance file exists
            if project_path:
                for ext in scene.ext_resources:
                    if ext.id == node.instance_id:
                        rel = ext.path.replace("res://", "")
                        if not (project_path / rel).exists():
                            report.warnings.append(VisibilityWarning(
                                node_name=node.name,
                                node_type=f"instance={ext.path}",
                                severity="warning",
                                message=f"Instance source '{ext.path}' does not exist",
                            ))
                        break
            continue

        node_type = node.type

        # Is this node itself visual?
        if node_type in VISUAL_TYPES:
            report.visible_count += 1
            continue

        # Is this a type that's expected to be invisible?
        if node_type in INVISIBLE_OK_TYPES:
            continue

        # Is this a physics/body type that needs visual children?
        if node_type in NEEDS_VISUAL:
            # Check if any descendant is a visual type
            node_path = scene.get_node_path(node)
            if _has_visual_descendant(scene, node, node_path, children_map):
                report.visible_count += 1
            else:
                report.invisible_count += 1
                report.warnings.append(VisibilityWarning(
                    node_name=node.name,
                    node_type=node_type,
                    severity="warning",
                    message=(
                        f"No visual child node (needs Sprite2D, Polygon2D, "
                        f"MeshInstance, Label, etc. to be visible on screen)"
                    ),
                ))
            continue

        # Unknown type — don't warn, could be custom
        report.visible_count += 1

    # Check for default positions (hint, not warning)
    for node in scene.nodes:
        if node.parent is None:
            continue
        pos = node.properties.get("position", "")
        if not pos:
            continue
        # Check if position is the default (0,0) — this is often a mistake
        if pos in ("Vector2(0, 0)", "Vector2(0,0)", "Vector2(0.0, 0.0)"):
            # Don't warn for UI nodes, collision shapes, or children of physics bodies
            if node.type not in INVISIBLE_OK_TYPES and node.type not in VISUAL_TYPES:
                report.warnings.append(VisibilityWarning(
                    node_name=node.name,
                    node_type=node.type,
                    severity="hint",
                    message="Position is Vector2(0, 0) — is this intentional?",
                ))

    # Check script file existence
    if project_path:
        for ext in scene.ext_resources:
            if ext.type == "Script":
                rel = ext.path.replace("res://", "")
                if not (project_path / rel).exists():
                    report.warnings.append(VisibilityWarning(
                        node_name="(ext_resource)",
                        node_type="Script",
                        severity="warning",
                        message=f"Script file '{ext.path}' does not exist",
                    ))

    return report


def _has_visual_descendant(scene: Scene, node: SceneNode,
                           node_path: str,
                           children_map: dict[str, list[SceneNode]]) -> bool:
    """Recursively check if a node has any visual descendant."""
    # Get children of this node
    children = children_map.get(node_path, [])
    # For root's direct children, also check parent="."
    if node.parent is None:
        children = children + children_map.get(".", [])

    for child in children:
        if child.type in VISUAL_TYPES:
            return True
        if child.instance_id:
            return True  # Instance could contain visual nodes
        # Recurse
        child_path = f"{node_path}/{child.name}" if node_path != "." else child.name
        if _has_visual_descendant(scene, child, child_path, children_map):
            return True
    return False
