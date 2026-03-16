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
##
## Compatible with Godot 4.3+ (including 4.6.x).
## Variable names avoid shadowing built-in class names.

func _init() -> void:
	var user_args: PackedStringArray = OS.get_cmdline_user_args()
	var cmd_file_path: String = ""
	var result_file_path: String = ""
	for i in range(user_args.size()):
		if user_args[i] == "--cmd" and i + 1 < user_args.size():
			cmd_file_path = user_args[i + 1]
		elif user_args[i] == "--result" and i + 1 < user_args.size():
			result_file_path = user_args[i + 1]

	if cmd_file_path == "" or result_file_path == "":
		_write_result(result_file_path, {"error": "Missing --cmd or --result args"})
		quit(1)
		return

	var cmd_text: String = FileAccess.get_file_as_string(cmd_file_path)
	if cmd_text == "":
		_write_result(result_file_path, {"error": "Cannot read command file"})
		quit(1)
		return

	var json_parser: JSON = JSON.new()
	var parse_err: int = json_parser.parse(cmd_text)
	if parse_err != OK:
		_write_result(result_file_path, {"error": "Invalid JSON: " + json_parser.get_error_message()})
		quit(1)
		return

	var cmd: Dictionary = json_parser.data
	var action: String = cmd.get("action", "")
	var out: Dictionary = {}

	match action:
		"validate_scene":
			out = _validate_scene(cmd)
		"read_scene_tree":
			out = _read_scene_tree(cmd)
		"validate_resources":
			out = _validate_resources(cmd)
		"read_project_info":
			out = _read_project_info()
		"validate_script":
			out = _validate_script(cmd)
		"list_node_types":
			out = _list_node_types(cmd)
		"get_class_properties":
			out = _get_class_properties(cmd)
		_:
			out = {"error": "Unknown action: " + action}

	_write_result(result_file_path, out)
	quit(0)


func _validate_scene(cmd: Dictionary) -> Dictionary:
	var spath: String = cmd.get("scene", "")
	if spath == "":
		return {"error": "Missing 'scene' parameter"}

	if not ResourceLoader.exists(spath):
		return {"valid": false, "error": "Scene file not found: " + spath}

	var packed: PackedScene = ResourceLoader.load(spath) as PackedScene
	if packed == null:
		return {"valid": false, "error": "Failed to load scene: " + spath}

	var state: SceneState = packed.get_state()
	var node_list: Array = []
	for i in range(state.get_node_count()):
		var node_info: Dictionary = {
			"name": state.get_node_name(i),
			"type": StringName(state.get_node_type(i)),
			"path": String(state.get_node_path(i)),
			"property_count": state.get_node_property_count(i),
		}
		var grp: PackedStringArray = state.get_node_groups(i)
		if grp.size() > 0:
			var grp_arr: Array = []
			for g in grp:
				grp_arr.append(String(g))
			node_info["groups"] = grp_arr
		node_list.append(node_info)

	return {
		"valid": true,
		"scene": spath,
		"node_count": state.get_node_count(),
		"nodes": node_list,
		"connection_count": state.get_connection_count(),
	}


func _read_scene_tree(cmd: Dictionary) -> Dictionary:
	var spath: String = cmd.get("scene", "")
	if spath == "":
		return {"error": "Missing 'scene' parameter"}

	var packed: PackedScene = ResourceLoader.load(spath) as PackedScene
	if packed == null:
		return {"error": "Failed to load scene: " + spath}

	var inst: Node = packed.instantiate()
	if inst == null:
		return {"error": "Failed to instantiate scene"}

	var tree_data: Dictionary = _serialize_node(inst)
	inst.queue_free()
	return {"scene": spath, "tree": tree_data}


func _serialize_node(nd: Node) -> Dictionary:
	var d: Dictionary = {
		"name": String(nd.name),
		"class": nd.get_class(),
	}

	# Get relevant properties
	var prop_dict: Dictionary = {}
	for prop in nd.get_property_list():
		var pname: String = prop["name"]
		var pusage: int = prop["usage"]
		if pusage & PROPERTY_USAGE_STORAGE:
			var pval: Variant = nd.get(pname)
			if pval != null and pname != "script":
				prop_dict[pname] = _serialize_value(pval)
	if prop_dict.size() > 0:
		d["properties"] = prop_dict

	# Get children
	var child_arr: Array = []
	for child in nd.get_children():
		child_arr.append(_serialize_node(child))
	if child_arr.size() > 0:
		d["children"] = child_arr

	return d


func _serialize_value(val: Variant) -> String:
	if val is Vector2:
		return "Vector2(%s, %s)" % [val.x, val.y]
	elif val is Vector3:
		return "Vector3(%s, %s, %s)" % [val.x, val.y, val.z]
	elif val is Color:
		return "Color(%s, %s, %s, %s)" % [val.r, val.g, val.b, val.a]
	elif val is Rect2:
		return "Rect2(%s, %s, %s, %s)" % [val.position.x, val.position.y, val.size.x, val.size.y]
	elif val is Resource:
		if val.resource_path != "":
			return val.resource_path
		return str(val)
	return str(val)


func _validate_resources(cmd: Dictionary) -> Dictionary:
	var paths: Array = cmd.get("paths", [])
	var res_list: Array = []
	for p in paths:
		var rpath: String = String(p)
		var is_valid: bool = ResourceLoader.exists(rpath)
		var info: Dictionary = {"path": rpath, "valid": is_valid}
		if is_valid:
			var loaded: Resource = ResourceLoader.load(rpath)
			if loaded != null:
				info["type"] = loaded.get_class()
		res_list.append(info)
	return {"resources": res_list}


func _read_project_info() -> Dictionary:
	return {
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"version": Engine.get_version_info(),
		"renderer": ProjectSettings.get_setting("rendering/renderer/rendering_method", ""),
	}


func _validate_script(cmd: Dictionary) -> Dictionary:
	var spath: String = cmd.get("script", "")
	if spath == "":
		return {"error": "Missing 'script' parameter"}

	if not ResourceLoader.exists(spath):
		return {"valid": false, "error": "Script file not found"}

	var loaded_script: Script = ResourceLoader.load(spath) as Script
	if loaded_script == null:
		return {"valid": false, "error": "Failed to load script"}

	return {
		"valid": loaded_script.can_instantiate(),
		"script": spath,
		"base_type": loaded_script.get_instance_base_type(),
	}


func _list_node_types(cmd: Dictionary) -> Dictionary:
	var base_class: String = cmd.get("base", "Node")
	var type_list: PackedStringArray = ClassDB.get_inheriters_from_class(base_class)
	var out_list: Array = []
	for t in type_list:
		if ClassDB.can_instantiate(t):
			out_list.append(String(t))
	out_list.sort()
	return {"base": base_class, "types": out_list}


func _get_class_properties(cmd: Dictionary) -> Dictionary:
	var cname: String = cmd.get("class_name", "")
	if cname == "" or not ClassDB.class_exists(cname):
		return {"error": "Unknown class: " + cname}

	var prop_list: Array = []
	for prop in ClassDB.class_get_property_list(cname):
		var pname: String = prop["name"]
		var ptype: int = prop["type"]
		var pusage: int = prop["usage"]
		if pusage & PROPERTY_USAGE_EDITOR:
			prop_list.append({
				"name": pname,
				"type": ptype,
				"type_name": _type_name(ptype),
			})
	return {"class": cname, "properties": prop_list}


func _type_name(tid: int) -> String:
	match tid:
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


func _write_result(fpath: String, data: Dictionary) -> void:
	if fpath == "":
		return
	var f: FileAccess = FileAccess.open(fpath, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "\t"))
		f.close()
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
    """Validate a GDScript file using the Godot parser.

    Also checks for autoload references that won't be available in headless mode.
    """
    if not script.startswith("res://"):
        script = f"res://{script}"

    result = run_bridge(project_path, "validate_script", {"script": script}, **kwargs)

    # Post-validation: check for autoload dependencies
    if result.success:
        warnings = _check_autoload_refs(project_path, script)
        if warnings:
            result.data["autoload_warnings"] = warnings

    return result


def _check_autoload_refs(project_path: Path, res_path: str) -> list[str]:
    """Check if a script references autoload singletons.

    Autoloads are globals in Godot but aren't loaded in headless bridge mode,
    so validate-script may give false positives. Warn the user.
    """
    # Get script file path
    rel = res_path.replace("res://", "")
    script_file = project_path / rel
    if not script_file.exists():
        return []

    # Get autoload names from project.godot
    try:
        from playgen.godot.project_file import load_project
        proj = load_project(project_path)
        autoloads = set(proj.sections.get("autoload", {}).keys())
    except Exception:
        return []

    if not autoloads:
        return []

    # Scan script source for autoload references
    source = script_file.read_text(encoding="utf-8")
    found: list[str] = []
    for name in autoloads:
        # Look for the autoload name used as an identifier (not in comments/strings)
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if name in stripped:
                found.append(name)
                break

    if found:
        return [
            f"Script references autoload(s): {', '.join(sorted(found))}. "
            "These are not loaded in headless validation mode — "
            "validation result may be a false positive."
        ]
    return []


def read_project_info(project_path: Path, **kwargs) -> BridgeResult:
    """Read project info from Godot's perspective."""
    return run_bridge(project_path, "read_project_info", **kwargs)


def get_class_properties(project_path: Path, class_name: str, **kwargs) -> BridgeResult:
    """Get all editor-visible properties for a Godot class."""
    return run_bridge(project_path, "get_class_properties", {"class_name": class_name}, **kwargs)


def list_node_types(project_path: Path, base: str = "Node", **kwargs) -> BridgeResult:
    """List all instantiable node types inheriting from a base class."""
    return run_bridge(project_path, "list_node_types", {"base": base}, **kwargs)
