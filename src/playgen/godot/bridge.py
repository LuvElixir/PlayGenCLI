"""Engine-Native Bridge for Godot 4.x.

Provides a structured communication channel between PlayGenCLI and the
Godot engine running in headless mode. Uses EditorScript / @tool scripts
to perform operations that are unsafe or impractical via pure text manipulation:

- Scene tree authority reads (what Godot actually sees)
- Resource validation (does this resource load correctly?)
- TileMap data editing
- Scene inheritance / instancing verification
- Import system triggers

Communication: PlayGenCLI writes a JSON command file, invokes Godot headless
with a bridge script, and reads the JSON result file.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from playgen.godot.runner import find_godot


# The GDScript bridge that runs inside Godot headless mode
BRIDGE_SCRIPT = r'''@tool
extends SceneTree

## PlayGen Engine Bridge - runs inside Godot headless mode.
## Reads a command JSON, executes it, writes result JSON.

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var cmd_file := ""
	var result_file := ""
	for i in range(args.size()):
		if args[i] == "--cmd" and i + 1 < args.size():
			cmd_file = args[i + 1]
		elif args[i] == "--result" and i + 1 < args.size():
			result_file = args[i + 1]

	if cmd_file == "" or result_file == "":
		_write_result(result_file, {"error": "Missing --cmd or --result args"})
		quit(1)
		return

	var cmd_text := FileAccess.get_file_as_string(cmd_file)
	if cmd_text == "":
		_write_result(result_file, {"error": "Cannot read command file"})
		quit(1)
		return

	var json := JSON.new()
	var err := json.parse(cmd_text)
	if err != OK:
		_write_result(result_file, {"error": "Invalid JSON: " + json.get_error_message()})
		quit(1)
		return

	var cmd: Dictionary = json.data
	var action: String = cmd.get("action", "")
	var result := {}

	match action:
		"validate_scene":
			result = _validate_scene(cmd)
		"read_scene_tree":
			result = _read_scene_tree(cmd)
		"validate_resources":
			result = _validate_resources(cmd)
		"read_project_info":
			result = _read_project_info()
		"validate_script":
			result = _validate_script(cmd)
		"list_node_types":
			result = _list_node_types(cmd)
		"get_class_properties":
			result = _get_class_properties(cmd)
		_:
			result = {"error": "Unknown action: " + action}

	_write_result(result_file, result)
	quit(0)


func _validate_scene(cmd: Dictionary) -> Dictionary:
	var scene_path: String = cmd.get("scene", "")
	if scene_path == "":
		return {"error": "Missing 'scene' parameter"}

	if not ResourceLoader.exists(scene_path):
		return {"valid": false, "error": "Scene file not found: " + scene_path}

	var scene := ResourceLoader.load(scene_path) as PackedScene
	if scene == null:
		return {"valid": false, "error": "Failed to load scene: " + scene_path}

	var state := scene.get_state()
	var nodes := []
	for i in range(state.get_node_count()):
		var node_info := {
			"name": state.get_node_name(i),
			"type": state.get_node_type(i) as String,
			"path": state.get_node_path(i) as String,
			"property_count": state.get_node_property_count(i),
		}
		var groups := state.get_node_groups(i)
		if groups.size() > 0:
			node_info["groups"] = []
			for g in groups:
				node_info["groups"].append(str(g))
		nodes.append(node_info)

	return {
		"valid": true,
		"scene": scene_path,
		"node_count": state.get_node_count(),
		"nodes": nodes,
		"connection_count": state.get_connection_count(),
	}


func _read_scene_tree(cmd: Dictionary) -> Dictionary:
	var scene_path: String = cmd.get("scene", "")
	if scene_path == "":
		return {"error": "Missing 'scene' parameter"}

	var scene := ResourceLoader.load(scene_path) as PackedScene
	if scene == null:
		return {"error": "Failed to load scene: " + scene_path}

	var instance := scene.instantiate()
	if instance == null:
		return {"error": "Failed to instantiate scene"}

	var tree := _serialize_node(instance)
	instance.queue_free()
	return {"scene": scene_path, "tree": tree}


func _serialize_node(node: Node) -> Dictionary:
	var result := {
		"name": node.name as String,
		"class": node.get_class(),
	}

	# Get relevant properties
	var props := {}
	for prop in node.get_property_list():
		var name: String = prop["name"]
		var usage: int = prop["usage"]
		# Only include user-set / storage properties
		if usage & PROPERTY_USAGE_STORAGE:
			var val = node.get(name)
			if val != null and name != "script":
				props[name] = _serialize_value(val)
	if props.size() > 0:
		result["properties"] = props

	# Get children
	var children := []
	for child in node.get_children():
		children.append(_serialize_node(child))
	if children.size() > 0:
		result["children"] = children

	return result


func _serialize_value(val) -> String:
	if val is Vector2:
		return "Vector2(%s, %s)" % [val.x, val.y]
	elif val is Vector3:
		return "Vector3(%s, %s, %s)" % [val.x, val.y, val.z]
	elif val is Color:
		return "Color(%s, %s, %s, %s)" % [val.r, val.g, val.b, val.a]
	elif val is Rect2:
		return "Rect2(%s, %s, %s, %s)" % [val.position.x, val.position.y, val.size.x, val.size.y]
	elif val is Resource:
		return val.resource_path if val.resource_path != "" else str(val)
	else:
		return str(val)


func _validate_resources(cmd: Dictionary) -> Dictionary:
	var paths: Array = cmd.get("paths", [])
	var results := []
	for p in paths:
		var path: String = p as String
		var valid := ResourceLoader.exists(path)
		var info := {"path": path, "valid": valid}
		if valid:
			var res := ResourceLoader.load(path)
			if res != null:
				info["type"] = res.get_class()
		results.append(info)
	return {"resources": results}


func _read_project_info() -> Dictionary:
	return {
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"version": Engine.get_version_info(),
		"renderer": ProjectSettings.get_setting("rendering/renderer/rendering_method", ""),
	}


func _validate_script(cmd: Dictionary) -> Dictionary:
	var script_path: String = cmd.get("script", "")
	if script_path == "":
		return {"error": "Missing 'script' parameter"}

	if not ResourceLoader.exists(script_path):
		return {"valid": false, "error": "Script file not found"}

	var script := ResourceLoader.load(script_path) as Script
	if script == null:
		return {"valid": false, "error": "Failed to load script"}

	return {
		"valid": script.can_instantiate(),
		"script": script_path,
		"base_type": script.get_instance_base_type(),
	}


func _list_node_types(cmd: Dictionary) -> Dictionary:
	var base: String = cmd.get("base", "Node")
	var types := ClassDB.get_inheriters_from_class(base)
	var result := []
	for t in types:
		if ClassDB.can_instantiate(t):
			result.append(t as String)
	result.sort()
	return {"base": base, "types": result}


func _get_class_properties(cmd: Dictionary) -> Dictionary:
	var class_name: String = cmd.get("class_name", "")
	if class_name == "" or not ClassDB.class_exists(class_name):
		return {"error": "Unknown class: " + class_name}

	var props := []
	for prop in ClassDB.class_get_property_list(class_name):
		var name: String = prop["name"]
		var type_id: int = prop["type"]
		var usage: int = prop["usage"]
		if usage & PROPERTY_USAGE_EDITOR:
			props.append({
				"name": name,
				"type": type_id,
				"type_name": _type_name(type_id),
			})
	return {"class": class_name, "properties": props}


func _type_name(type_id: int) -> String:
	match type_id:
		TYPE_BOOL: return "bool"
		TYPE_INT: return "int"
		TYPE_FLOAT: return "float"
		TYPE_STRING: return "String"
		TYPE_VECTOR2: return "Vector2"
		TYPE_VECTOR3: return "Vector3"
		TYPE_COLOR: return "Color"
		TYPE_NODE_PATH: return "NodePath"
		TYPE_RID: return "RID"
		TYPE_OBJECT: return "Object"
		TYPE_DICTIONARY: return "Dictionary"
		TYPE_ARRAY: return "Array"
		_: return "Variant"


func _write_result(path: String, data: Dictionary) -> void:
	if path == "":
		return
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(data, "\t"))
		file.close()
'''


@dataclass
class BridgeResult:
    """Result from an engine bridge operation."""
    success: bool
    data: dict
    error: str = ""
    godot_stderr: str = ""

    def to_dict(self) -> dict:
        result: dict = {"success": self.success}
        if self.success:
            result.update(self.data)
        else:
            result["error"] = self.error
            if self.godot_stderr:
                result["godot_stderr"] = self.godot_stderr[:2000]
        return result


def _ensure_bridge_script(project_path: Path) -> Path:
    """Write the bridge GDScript to the project's .playgen/ directory."""
    bridge_dir = project_path / ".playgen"
    bridge_dir.mkdir(exist_ok=True)
    script_path = bridge_dir / "bridge.gd"
    script_path.write_text(BRIDGE_SCRIPT, encoding="utf-8")

    # Ensure .playgen/ is in .gdignore so Godot doesn't import it as game content
    gdignore = bridge_dir / ".gdignore"
    if not gdignore.exists():
        gdignore.write_text("", encoding="utf-8")

    return script_path


def run_bridge(
    project_path: Path,
    action: str,
    params: dict | None = None,
    godot_path: str | None = None,
    timeout: int = 30,
) -> BridgeResult:
    """Execute a bridge command in Godot headless mode.

    Writes a command JSON, runs Godot with the bridge script, reads the result.
    """
    godot = godot_path or find_godot()
    if not godot:
        return BridgeResult(
            success=False, data={},
            error="Godot executable not found. Set GODOT_PATH or add godot to PATH.",
        )

    bridge_script = _ensure_bridge_script(project_path)

    # Write command file
    cmd_data = {"action": action}
    if params:
        cmd_data.update(params)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(project_path / ".playgen"),
        delete=False, encoding="utf-8",
    ) as cmd_file:
        json.dump(cmd_data, cmd_file)
        cmd_path = cmd_file.name

    result_path = cmd_path.replace(".json", "_result.json")

    try:
        cmd = [
            godot, "--headless",
            "--path", str(project_path),
            "--script", str(bridge_script),
            "--", "--cmd", cmd_path, "--result", result_path,
        ]

        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(project_path),
        )

        # Read result
        result_file = Path(result_path)
        if result_file.exists():
            result_data = json.loads(result_file.read_text(encoding="utf-8"))
            if "error" in result_data:
                return BridgeResult(
                    success=False, data=result_data,
                    error=result_data["error"],
                    godot_stderr=proc.stderr,
                )
            return BridgeResult(success=True, data=result_data)
        else:
            return BridgeResult(
                success=False, data={},
                error="Bridge script did not produce output",
                godot_stderr=proc.stderr,
            )

    except subprocess.TimeoutExpired:
        return BridgeResult(success=False, data={}, error=f"Bridge timed out after {timeout}s")
    except FileNotFoundError:
        return BridgeResult(success=False, data={}, error=f"Godot not found at: {godot}")
    except json.JSONDecodeError as e:
        return BridgeResult(success=False, data={}, error=f"Invalid result JSON: {e}")
    finally:
        # Cleanup temp files
        for f in [cmd_path, result_path]:
            try:
                os.unlink(f)
            except OSError:
                pass


def validate_scene(project_path: Path, scene: str, **kwargs) -> BridgeResult:
    """Validate a scene file using the Godot engine."""
    if not scene.startswith("res://"):
        scene = f"res://{scene}"
    return run_bridge(project_path, "validate_scene", {"scene": scene}, **kwargs)


def read_scene_tree(project_path: Path, scene: str, **kwargs) -> BridgeResult:
    """Read a scene's instantiated tree from Godot's perspective."""
    if not scene.startswith("res://"):
        scene = f"res://{scene}"
    return run_bridge(project_path, "read_scene_tree", {"scene": scene}, **kwargs)


def validate_resources(project_path: Path, paths: list[str], **kwargs) -> BridgeResult:
    """Validate that a list of resource paths can be loaded by Godot."""
    return run_bridge(project_path, "validate_resources", {"paths": paths}, **kwargs)


def validate_script(project_path: Path, script: str, **kwargs) -> BridgeResult:
    """Validate a GDScript file using the Godot parser."""
    if not script.startswith("res://"):
        script = f"res://{script}"
    return run_bridge(project_path, "validate_script", {"script": script}, **kwargs)


def read_project_info(project_path: Path, **kwargs) -> BridgeResult:
    """Read project info from Godot's perspective."""
    return run_bridge(project_path, "read_project_info", **kwargs)


def get_class_properties(project_path: Path, class_name: str, **kwargs) -> BridgeResult:
    """Get all editor-visible properties for a Godot class."""
    return run_bridge(project_path, "get_class_properties", {"class_name": class_name}, **kwargs)


def list_node_types(project_path: Path, base: str = "Node", **kwargs) -> BridgeResult:
    """List all instantiable node types inheriting from a base class."""
    return run_bridge(project_path, "list_node_types", {"base": base}, **kwargs)
