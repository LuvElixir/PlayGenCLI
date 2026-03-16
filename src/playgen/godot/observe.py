"""Runtime observation system for Godot projects.

Injects a telemetry autoload into the project that captures structured
runtime state during execution. After the run, PlayGenCLI reads back
the telemetry data to provide the Agent with actionable observations.

Captures:
- Frame-by-frame node positions (sampled)
- Physics collision events
- Signal emissions (user-defined)
- Script errors and print() output
- Scene tree changes (node add/remove)
- Custom telemetry from game scripts via PlayGenTelemetry.log()

This solves the critical "run then blind" problem: after `playgen run`,
the Agent gets structured runtime data, not just stdout text.
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field

from playgen.godot.project_file import load_project, save_project


OBSERVER_SCRIPT = r'''extends Node

## PlayGen Runtime Observer - auto-injected telemetry for Agent feedback.
## Captures runtime state and writes structured JSON on exit.

var _log_path: String = ""
var _events: Array[Dictionary] = []
var _frame_count: int = 0
var _sample_interval: int = 30  # Sample every N frames
var _tracked_nodes: Array[String] = []
var _start_time: float = 0.0
var _max_events: int = 5000

func _ready() -> void:
	_log_path = OS.get_environment("PLAYGEN_TELEMETRY_PATH")
	if _log_path == "":
		_log_path = "user://playgen_telemetry.json"

	_start_time = Time.get_ticks_msec() / 1000.0

	# Track all physics bodies and key nodes
	_discover_tracked_nodes(get_tree().root)

	# Connect to tree signals
	get_tree().node_added.connect(_on_node_added)
	get_tree().node_removed.connect(_on_node_removed)

	_log_event("session_start", {
		"scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		"tracked_nodes": _tracked_nodes.duplicate(),
	})


func _process(_delta: float) -> void:
	_frame_count += 1
	if _frame_count % _sample_interval != 0:
		return
	if _events.size() >= _max_events:
		return

	# Sample positions of tracked nodes
	var snapshot := {}
	for path in _tracked_nodes:
		var node := get_node_or_null(NodePath(path))
		if node == null:
			continue
		if node is Node2D:
			snapshot[path] = {
				"position": [node.global_position.x, node.global_position.y],
				"rotation": node.rotation,
				"visible": node.visible,
			}
		elif node is Node3D:
			snapshot[path] = {
				"position": [node.global_position.x, node.global_position.y, node.global_position.z],
				"rotation": [node.rotation.x, node.rotation.y, node.rotation.z],
				"visible": node.visible,
			}
		elif node is Control:
			snapshot[path] = {
				"position": [node.global_position.x, node.global_position.y],
				"size": [node.size.x, node.size.y],
				"visible": node.visible,
			}

	if snapshot.size() > 0:
		_log_event("frame_sample", {"frame": _frame_count, "nodes": snapshot})


func _physics_process(_delta: float) -> void:
	# Check for collisions on physics bodies
	for path in _tracked_nodes:
		var node := get_node_or_null(NodePath(path))
		if node == null:
			continue
		if node is CharacterBody2D:
			if node.is_on_floor():
				pass  # Normal state, don't spam
			if node.get_slide_collision_count() > 0:
				for i in range(node.get_slide_collision_count()):
					var col := node.get_slide_collision(i)
					if col:
						_log_event("collision", {
							"body": path,
							"collider": col.get_collider().name if col.get_collider() else "unknown",
							"normal": [col.get_normal().x, col.get_normal().y],
						})


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		_write_telemetry()


func _discover_tracked_nodes(node: Node, depth: int = 0) -> void:
	if depth > 10:
		return
	if node is Node2D or node is Node3D or node is Control:
		var path := str(node.get_path())
		if path != "/root" and path != "/root/PlayGenObserver":
			_tracked_nodes.append(path)
	for child in node.get_children():
		_discover_tracked_nodes(child, depth + 1)


func _on_node_added(node: Node) -> void:
	if _events.size() >= _max_events:
		return
	if node.name == "PlayGenObserver":
		return
	_log_event("node_added", {
		"name": node.name as String,
		"class": node.get_class(),
		"parent": str(node.get_parent().get_path()) if node.get_parent() else "",
	})
	# Auto-track new physics/visual nodes
	if node is Node2D or node is Node3D:
		call_deferred("_track_new_node", node)


func _track_new_node(node: Node) -> void:
	if node and is_instance_valid(node):
		var path := str(node.get_path())
		if path not in _tracked_nodes:
			_tracked_nodes.append(path)


func _on_node_removed(node: Node) -> void:
	if _events.size() >= _max_events:
		return
	if node.name == "PlayGenObserver":
		return
	_log_event("node_removed", {
		"name": node.name as String,
		"class": node.get_class(),
	})


## Public API for game scripts to log custom telemetry.
## Usage: PlayGenObserver.log_custom("player_died", {"cause": "fall"})
func log_custom(event_type: String, data: Dictionary = {}) -> void:
	_log_event("custom:" + event_type, data)


func _log_event(event_type: String, data: Dictionary) -> void:
	if _events.size() >= _max_events:
		return
	var elapsed := (Time.get_ticks_msec() / 1000.0) - _start_time
	_events.append({
		"t": snappedf(elapsed, 0.01),
		"type": event_type,
		"data": data,
	})


func _write_telemetry() -> void:
	_log_event("session_end", {
		"total_frames": _frame_count,
		"total_events": _events.size(),
	})

	var summary := {
		"version": 1,
		"total_frames": _frame_count,
		"duration": snappedf((Time.get_ticks_msec() / 1000.0) - _start_time, 0.01),
		"tracked_nodes": _tracked_nodes,
		"event_count": _events.size(),
		"events": _events,
	}

	var file := FileAccess.open(_log_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(summary, "\t"))
		file.close()
'''


OBSERVER_SCRIPT_NAME = "playgen_observer.gd"
OBSERVER_AUTOLOAD_NAME = "PlayGenObserver"


def inject_observer(project_path: Path) -> Path:
    """Inject the runtime observer autoload into the project.

    Returns the path to the observer script.
    """
    script_path = project_path / OBSERVER_SCRIPT_NAME
    script_path.write_text(OBSERVER_SCRIPT, encoding="utf-8")

    # Add as autoload
    try:
        proj = load_project(project_path)
        proj.set("autoload", OBSERVER_AUTOLOAD_NAME,
                 f'"*res://{OBSERVER_SCRIPT_NAME}"')
        save_project(proj, project_path)
    except FileNotFoundError:
        pass  # No project.godot yet

    return script_path


def remove_observer(project_path: Path) -> None:
    """Remove the runtime observer from the project."""
    script_path = project_path / OBSERVER_SCRIPT_NAME
    if script_path.exists():
        script_path.unlink()

    try:
        proj = load_project(project_path)
        proj.remove("autoload", OBSERVER_AUTOLOAD_NAME)
        save_project(proj, project_path)
    except (FileNotFoundError, KeyError):
        pass


def get_default_telemetry_path(project_path: Path) -> Path:
    """Get the default telemetry output path."""
    return project_path / ".playgen" / "telemetry.json"


@dataclass
class TelemetryReport:
    """Structured analysis of runtime telemetry data."""
    duration: float = 0.0
    total_frames: int = 0
    tracked_nodes: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    collisions: list[dict] = field(default_factory=list)
    scene_changes: list[dict] = field(default_factory=list)
    custom_events: list[dict] = field(default_factory=list)
    node_positions: dict[str, list[float]] = field(default_factory=dict)  # last known

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "total_frames": self.total_frames,
            "tracked_nodes": self.tracked_nodes,
            "event_count": len(self.events),
            "collision_count": len(self.collisions),
            "scene_changes": len(self.scene_changes),
            "custom_events": self.custom_events,
            "last_positions": self.node_positions,
            "errors": self.errors,
            "summary": self._summary(),
        }

    def _summary(self) -> str:
        parts = [f"Ran {self.duration:.1f}s, {self.total_frames} frames"]
        if self.tracked_nodes:
            parts.append(f"tracked {len(self.tracked_nodes)} nodes")
        if self.collisions:
            parts.append(f"{len(self.collisions)} collisions")
        if self.scene_changes:
            parts.append(f"{len(self.scene_changes)} tree changes")
        if self.custom_events:
            parts.append(f"{len(self.custom_events)} custom events")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


def parse_telemetry(telemetry_path: Path) -> TelemetryReport:
    """Parse telemetry JSON into a structured report."""
    report = TelemetryReport()

    if not telemetry_path.exists():
        report.errors.append("No telemetry file found")
        return report

    try:
        data = json.loads(telemetry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        report.errors.append(f"Invalid telemetry JSON: {e}")
        return report

    report.duration = data.get("duration", 0.0)
    report.total_frames = data.get("total_frames", 0)
    report.tracked_nodes = data.get("tracked_nodes", [])
    report.events = data.get("events", [])

    # Classify events
    for event in report.events:
        etype = event.get("type", "")
        edata = event.get("data", {})

        if etype == "collision":
            report.collisions.append(event)
        elif etype in ("node_added", "node_removed"):
            report.scene_changes.append(event)
        elif etype.startswith("custom:"):
            report.custom_events.append(event)
        elif etype == "frame_sample":
            # Track last known positions
            for node_path, node_data in edata.get("nodes", {}).items():
                if "position" in node_data:
                    report.node_positions[node_path] = node_data["position"]

    return report
