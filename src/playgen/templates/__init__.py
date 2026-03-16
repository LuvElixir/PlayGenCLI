"""Project, scene, and script templates for common game patterns.

All templates generate valid Godot 4.x files that can be opened in the editor
and run immediately. No external assets required - uses Polygon2D for visuals.
"""

from __future__ import annotations

from pathlib import Path

from playgen.godot.tscn import Scene, write_tscn
from playgen.godot.project_file import GodotProject, write_project_file


# ---------------------------------------------------------------------------
# GDScript templates
# ---------------------------------------------------------------------------

PLAYER_PLATFORMER_2D = '''\
extends CharacterBody2D

const SPEED = 300.0
const JUMP_VELOCITY = -450.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")

func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta

\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = JUMP_VELOCITY

\tvar direction := Input.get_axis("ui_left", "ui_right")
\tif direction:
\t\tvelocity.x = direction * SPEED
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, SPEED)

\tmove_and_slide()
'''

PLAYER_TOPDOWN_2D = '''\
extends CharacterBody2D

const SPEED = 200.0

func _physics_process(_delta: float) -> void:
\tvar input_dir := Vector2(
\t\tInput.get_axis("ui_left", "ui_right"),
\t\tInput.get_axis("ui_up", "ui_down"),
\t)
\tvelocity = input_dir.normalized() * SPEED
\tmove_and_slide()
'''

UI_CONTROLLER = '''\
extends Control

@onready var start_button: Button = get_node("StartButton")
@onready var settings_button: Button = get_node("SettingsButton")
@onready var status_label: Label = get_node("StatusLabel")
@onready var score_label: Label = get_node("ScoreLabel")

var score: int = 0

func _ready() -> void:
\tstart_button.pressed.connect(_on_start_pressed)
\tsettings_button.pressed.connect(_on_settings_pressed)
\t_update_score_display()

func _on_start_pressed() -> void:
\tstatus_label.text = "Game started!"

func _on_settings_pressed() -> void:
\tstatus_label.text = "Settings opened"

func set_score(value: int) -> void:
\tscore = value
\t_update_score_display()

func _update_score_display() -> void:
\tscore_label.text = "Score: %d" % score

func show_message(text: String) -> void:
\tstatus_label.text = text
'''

STATE_MACHINE = '''\
extends Node

signal state_changed(old_state: String, new_state: String)

@export var initial_state: String = "idle"

var current_state: String = ""
var previous_state: String = ""
var states: Dictionary = {}

func _ready() -> void:
\t_register_states()
\tif initial_state != "":
\t\ttransition_to(initial_state)

func _register_states() -> void:
\tstates = {
\t\t"idle": {
\t\t\t"enter": _enter_idle,
\t\t\t"exit": _exit_idle,
\t\t\t"update": _update_idle,
\t\t},
\t\t"walk": {
\t\t\t"enter": _enter_walk,
\t\t\t"exit": _exit_walk,
\t\t\t"update": _update_walk,
\t\t},
\t\t"attack": {
\t\t\t"enter": _enter_attack,
\t\t\t"exit": _exit_attack,
\t\t\t"update": _update_attack,
\t\t},
\t}

func _process(delta: float) -> void:
\tif current_state != "" and states.has(current_state):
\t\tvar state_data: Dictionary = states[current_state]
\t\tif state_data.has("update"):
\t\t\tstate_data["update"].call(delta)

func transition_to(new_state: String) -> void:
\tif not states.has(new_state):
\t\tpush_warning("State '%s' does not exist" % new_state)
\t\treturn
\tif new_state == current_state:
\t\treturn
\tif current_state != "" and states.has(current_state):
\t\tvar old_data: Dictionary = states[current_state]
\t\tif old_data.has("exit"):
\t\t\told_data["exit"].call()
\tprevious_state = current_state
\tcurrent_state = new_state
\tvar new_data: Dictionary = states[current_state]
\tif new_data.has("enter"):
\t\tnew_data["enter"].call()
\tstate_changed.emit(previous_state, current_state)

# --- Idle state ---
func _enter_idle() -> void:
\tpass

func _exit_idle() -> void:
\tpass

func _update_idle(_delta: float) -> void:
\tpass

# --- Walk state ---
func _enter_walk() -> void:
\tpass

func _exit_walk() -> void:
\tpass

func _update_walk(_delta: float) -> void:
\tpass

# --- Attack state ---
func _enter_attack() -> void:
\tpass

func _exit_attack() -> void:
\tpass

func _update_attack(_delta: float) -> void:
\tpass
'''

GAME_MANAGER = '''\
extends Node

signal score_changed(new_score: int)
signal level_changed(new_level: int)
signal game_started()
signal game_ended()
signal game_paused(is_paused: bool)

var score: int = 0
var high_score: int = 0
var level: int = 1
var game_over: bool = false
var paused: bool = false

func _ready() -> void:
\tprocess_mode = Node.PROCESS_MODE_ALWAYS

func start_game() -> void:
\tscore = 0
\tlevel = 1
\tgame_over = false
\tpaused = false
\tget_tree().paused = false
\tscore_changed.emit(score)
\tlevel_changed.emit(level)
\tgame_started.emit()

func end_game() -> void:
\tgame_over = true
\tif score > high_score:
\t\thigh_score = score
\tgame_ended.emit()

func toggle_pause() -> void:
\tif game_over:
\t\treturn
\tpaused = not paused
\tget_tree().paused = paused
\tgame_paused.emit(paused)

func add_score(points: int) -> void:
\tif game_over:
\t\treturn
\tscore += points
\tscore_changed.emit(score)

func set_level(new_level: int) -> void:
\tlevel = new_level
\tlevel_changed.emit(level)

func next_level() -> void:
\tset_level(level + 1)

func restart() -> void:
\tstart_game()
'''

INVENTORY_MANAGER = '''\
extends Node

signal inventory_changed(item_name: String, new_count: int)
signal item_added(item_name: String, amount: int)
signal item_removed(item_name: String, amount: int)

var items: Dictionary = {}
var max_stack_size: int = 99

func add_item(item_name: String, amount: int = 1) -> bool:
\tif amount <= 0:
\t\treturn false
\tif items.has(item_name):
\t\tvar new_count: int = mini(items[item_name] + amount, max_stack_size)
\t\titems[item_name] = new_count
\telse:
\t\titems[item_name] = mini(amount, max_stack_size)
\titem_added.emit(item_name, amount)
\tinventory_changed.emit(item_name, items[item_name])
\treturn true

func remove_item(item_name: String, amount: int = 1) -> bool:
\tif amount <= 0:
\t\treturn false
\tif not items.has(item_name):
\t\treturn false
\tif items[item_name] < amount:
\t\treturn false
\titems[item_name] -= amount
\tif items[item_name] <= 0:
\t\titems.erase(item_name)
\t\titem_removed.emit(item_name, amount)
\t\tinventory_changed.emit(item_name, 0)
\telse:
\t\titem_removed.emit(item_name, amount)
\t\tinventory_changed.emit(item_name, items[item_name])
\treturn true

func has_item(item_name: String, amount: int = 1) -> bool:
\tif not items.has(item_name):
\t\treturn false
\treturn items[item_name] >= amount

func get_count(item_name: String) -> int:
\tif not items.has(item_name):
\t\treturn 0
\treturn items[item_name]

func get_all_items() -> Dictionary:
\treturn items.duplicate()

func clear_inventory() -> void:
\tvar old_items := items.duplicate()
\titems.clear()
\tfor item_name in old_items:
\t\tinventory_changed.emit(item_name, 0)
'''

DIALOGUE_SYSTEM = '''\
extends Control

signal dialogue_started()
signal dialogue_finished()
signal line_shown(line_index: int, text: String)

@onready var dialogue_label: Label = get_node("DialogueLabel")
@onready var name_label: Label = get_node("NameLabel")

var dialogue_lines: Array[String] = []
var speaker_name: String = ""
var current_line: int = -1
var is_active: bool = false

func _ready() -> void:
\tvisible = false

func _input(event: InputEvent) -> void:
\tif not is_active:
\t\treturn
\tif event.is_action_pressed("ui_accept"):
\t\tadvance()

func start_dialogue(lines: Array[String], speaker: String = "") -> void:
\tif lines.is_empty():
\t\treturn
\tdialogue_lines = lines
\tspeaker_name = speaker
\tcurrent_line = -1
\tis_active = true
\tvisible = true
\tif name_label:
\t\tname_label.text = speaker_name
\tdialogue_started.emit()
\tadvance()

func advance() -> void:
\tcurrent_line += 1
\tif current_line >= dialogue_lines.size():
\t\tend_dialogue()
\t\treturn
\tvar text: String = dialogue_lines[current_line]
\tif dialogue_label:
\t\tdialogue_label.text = text
\tline_shown.emit(current_line, text)

func end_dialogue() -> void:
\tis_active = false
\tvisible = false
\tdialogue_lines.clear()
\tcurrent_line = -1
\tdialogue_finished.emit()

func is_dialogue_active() -> bool:
\treturn is_active
'''

MENU_CONTROLLER = '''\
extends Control

signal start_pressed()
signal options_pressed()
signal quit_pressed()

@onready var start_button: Button = get_node("VBoxContainer/StartButton")
@onready var options_button: Button = get_node("VBoxContainer/OptionsButton")
@onready var quit_button: Button = get_node("VBoxContainer/QuitButton")
@onready var title_label: Label = get_node("TitleLabel")

@export var game_scene_path: String = "res://main.tscn"
@export var options_scene_path: String = ""

func _ready() -> void:
\tstart_button.pressed.connect(_on_start_pressed)
\toptions_button.pressed.connect(_on_options_pressed)
\tquit_button.pressed.connect(_on_quit_pressed)

func _on_start_pressed() -> void:
\tstart_pressed.emit()
\tif game_scene_path != "":
\t\tget_tree().change_scene_to_file(game_scene_path)

func _on_options_pressed() -> void:
\toptions_pressed.emit()
\tif options_scene_path != "":
\t\tget_tree().change_scene_to_file(options_scene_path)

func _on_quit_pressed() -> void:
\tquit_pressed.emit()
\tget_tree().quit()

func set_title(text: String) -> void:
\tif title_label:
\t\ttitle_label.text = text
'''

CAMERA_CONTROLLER = '''\
extends Camera2D

signal shake_finished()

@export var follow_target: NodePath = ""
@export var follow_speed: float = 5.0
@export var follow_offset: Vector2 = Vector2.ZERO

@export var zoom_speed: float = 2.0
@export var min_zoom: float = 0.5
@export var max_zoom: float = 3.0

var _target_node: Node2D = null
var _shake_intensity: float = 0.0
var _shake_duration: float = 0.0
var _shake_timer: float = 0.0
var _target_zoom: Vector2 = Vector2.ONE

func _ready() -> void:
\tif follow_target != "":
\t\t_target_node = get_node_or_null(follow_target)
\t_target_zoom = zoom

func _process(delta: float) -> void:
\t_process_follow(delta)
\t_process_shake(delta)
\t_process_zoom(delta)

func _process_follow(delta: float) -> void:
\tif _target_node == null:
\t\treturn
\tvar target_pos: Vector2 = _target_node.global_position + follow_offset
\tglobal_position = global_position.lerp(target_pos, follow_speed * delta)

func _process_shake(delta: float) -> void:
\tif _shake_timer <= 0.0:
\t\treturn
\t_shake_timer -= delta
\tvar shake_amount: float = _shake_intensity * (_shake_timer / _shake_duration)
\toffset = Vector2(
\t\trandf_range(-shake_amount, shake_amount),
\t\trandf_range(-shake_amount, shake_amount),
\t)
\tif _shake_timer <= 0.0:
\t\toffset = Vector2.ZERO
\t\tshake_finished.emit()

func _process_zoom(delta: float) -> void:
\tzoom = zoom.lerp(_target_zoom, zoom_speed * delta)

func set_follow_target(target: Node2D) -> void:
\t_target_node = target

func screen_shake(intensity: float = 10.0, duration: float = 0.3) -> void:
\t_shake_intensity = intensity
\t_shake_duration = duration
\t_shake_timer = duration

func zoom_to(target: float) -> void:
\ttarget = clampf(target, min_zoom, max_zoom)
\t_target_zoom = Vector2(target, target)

func zoom_in(amount: float = 0.1) -> void:
\tzoom_to(_target_zoom.x + amount)

func zoom_out(amount: float = 0.1) -> void:
\tzoom_to(_target_zoom.x - amount)

func snap_to_target() -> void:
\tif _target_node == null:
\t\treturn
\tglobal_position = _target_node.global_position + follow_offset
'''

SCRIPT_TEMPLATES: dict[str, str] = {
    "platformer-player": PLAYER_PLATFORMER_2D,
    "topdown-player": PLAYER_TOPDOWN_2D,
    "ui-controller": UI_CONTROLLER,
    "state-machine": STATE_MACHINE,
    "game-manager": GAME_MANAGER,
    "inventory-manager": INVENTORY_MANAGER,
    "dialogue-system": DIALOGUE_SYSTEM,
    "menu-controller": MENU_CONTROLLER,
    "camera-controller": CAMERA_CONTROLLER,
}


# ---------------------------------------------------------------------------
# Smart defaults by extends type (used by script create and build)
# ---------------------------------------------------------------------------

EXTENDS_DEFAULTS: dict[str, str] = {
    "CharacterBody2D": '''\
extends CharacterBody2D

const SPEED = 300.0
const JUMP_VELOCITY = -400.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")

func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta

\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = JUMP_VELOCITY

\tvar direction := Input.get_axis("ui_left", "ui_right")
\tif direction:
\t\tvelocity.x = direction * SPEED
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, SPEED)

\tmove_and_slide()
''',
    "CharacterBody3D": '''\
extends CharacterBody3D

const SPEED = 5.0
const JUMP_VELOCITY = 4.5

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")

func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity.y -= gravity * delta

\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = JUMP_VELOCITY

\tvar input_dir := Vector2(
\t\tInput.get_axis("ui_left", "ui_right"),
\t\tInput.get_axis("ui_up", "ui_down"),
\t)
\tvar direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
\tif direction:
\t\tvelocity.x = direction.x * SPEED
\t\tvelocity.z = direction.z * SPEED
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, SPEED)
\t\tvelocity.z = move_toward(velocity.z, 0, SPEED)

\tmove_and_slide()
''',
    "Area2D": '''\
extends Area2D

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)

func _on_body_entered(body: Node2D) -> void:
\tpass
''',
    "Area3D": '''\
extends Area3D

func _ready() -> void:
\tbody_entered.connect(_on_body_entered)

func _on_body_entered(body: Node3D) -> void:
\tpass
''',
    "RigidBody2D": '''\
extends RigidBody2D

func _ready() -> void:
\tpass

func _physics_process(_delta: float) -> void:
\tpass
''',
    "StaticBody2D": '''\
extends StaticBody2D

func _ready() -> void:
\tpass
''',
    "Node2D": '''\
extends Node2D

func _ready() -> void:
\tpass

func _process(_delta: float) -> void:
\tpass
''',
    "Node3D": '''\
extends Node3D

func _ready() -> void:
\tpass

func _process(_delta: float) -> void:
\tpass
''',
    "Control": '''\
extends Control

func _ready() -> void:
\tpass
''',
    "Node": '''\
extends Node

func _ready() -> void:
\tpass

func _process(_delta: float) -> void:
\tpass
''',
    "Timer": '''\
extends Timer

signal timer_triggered()

@export var auto_start_timer: bool = true

func _ready() -> void:
\ttimeout.connect(_on_timeout)
\tif auto_start_timer:
\t\tstart()

func _on_timeout() -> void:
\ttimer_triggered.emit()
''',
    "CanvasLayer": '''\
extends CanvasLayer

@onready var health_label: Label = get_node("HealthLabel")
@onready var score_label: Label = get_node("ScoreLabel")
@onready var message_label: Label = get_node("MessageLabel")

func _ready() -> void:
\t_hide_message()

func update_health(value: int) -> void:
\tif health_label:
\t\thealth_label.text = "HP: %d" % value

func update_score(value: int) -> void:
\tif score_label:
\t\tscore_label.text = "Score: %d" % value

func show_message(text: String, duration: float = 2.0) -> void:
\tif message_label:
\t\tmessage_label.text = text
\t\tmessage_label.visible = true
\t\tget_tree().create_timer(duration).timeout.connect(_hide_message)

func _hide_message() -> void:
\tif message_label:
\t\tmessage_label.visible = false
''',
    "Sprite2D": '''\
extends Sprite2D

@export var rotation_speed: float = 0.0
@export var bob_amplitude: float = 0.0
@export var bob_speed: float = 2.0

var _start_position: Vector2 = Vector2.ZERO
var _time: float = 0.0

func _ready() -> void:
\t_start_position = position

func _process(delta: float) -> void:
\t_time += delta
\tif rotation_speed != 0.0:
\t\trotation += rotation_speed * delta
\tif bob_amplitude != 0.0:
\t\tposition.y = _start_position.y + sin(_time * bob_speed) * bob_amplitude
''',
    "AnimationPlayer": '''\
extends AnimationPlayer

signal animation_cycle_finished(anim_name: String)

@export var default_animation: String = ""
@export var auto_play_default: bool = true

func _ready() -> void:
\tanimation_finished.connect(_on_animation_finished)
\tif auto_play_default and default_animation != "":
\t\tplay(default_animation)

func _on_animation_finished(anim_name: String) -> void:
\tanimation_cycle_finished.emit(anim_name)

func play_if_not_playing(anim_name: String) -> void:
\tif current_animation != anim_name:
\t\tplay(anim_name)

func play_backwards_anim(anim_name: String) -> void:
\tplay_backwards(anim_name)
''',
}


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------

def build_platformer_scene() -> Scene:
    """Build a complete 2D platformer scene with player, floor, and platforms."""
    scene = Scene()

    # External resource: player script
    script_res = scene.add_ext_resource("Script", "res://player.gd")

    # Sub resources: collision shapes
    player_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(36, 56)"})
    floor_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(1200, 40)"})
    plat1_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(250, 20)"})
    plat2_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(200, 20)"})
    plat3_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(180, 20)"})

    # Root
    scene.add_node("Main", "Node2D")

    # Player
    scene.add_node("Player", "CharacterBody2D", parent=".", properties={
        "position": "Vector2(576, 400)",
        "script": f'ExtResource("{script_res.id}")',
    })
    scene.add_node("PlayerVisual", "Polygon2D", parent="Player", properties={
        "color": "Color(0.25, 0.6, 1, 1)",
        "polygon": "PackedVector2Array(-18, -28, 18, -28, 18, 28, -18, 28)",
    })
    scene.add_node("CollisionShape2D", "CollisionShape2D", parent="Player", properties={
        "shape": f'SubResource("{player_shape.id}")',
    })
    scene.add_node("Camera2D", "Camera2D", parent="Player")

    # Floor
    scene.add_node("Floor", "StaticBody2D", parent=".", properties={
        "position": "Vector2(576, 620)",
    })
    scene.add_node("FloorVisual", "Polygon2D", parent="Floor", properties={
        "color": "Color(0.35, 0.35, 0.35, 1)",
        "polygon": "PackedVector2Array(-600, -20, 600, -20, 600, 20, -600, 20)",
    })
    scene.add_node("FloorCollision", "CollisionShape2D", parent="Floor", properties={
        "shape": f'SubResource("{floor_shape.id}")',
    })

    # Platform 1
    scene.add_node("Platform1", "StaticBody2D", parent=".", properties={
        "position": "Vector2(300, 480)",
    })
    scene.add_node("Plat1Visual", "Polygon2D", parent="Platform1", properties={
        "color": "Color(0.45, 0.45, 0.45, 1)",
        "polygon": "PackedVector2Array(-125, -10, 125, -10, 125, 10, -125, 10)",
    })
    scene.add_node("Plat1Collision", "CollisionShape2D", parent="Platform1", properties={
        "shape": f'SubResource("{plat1_shape.id}")',
    })

    # Platform 2
    scene.add_node("Platform2", "StaticBody2D", parent=".", properties={
        "position": "Vector2(800, 380)",
    })
    scene.add_node("Plat2Visual", "Polygon2D", parent="Platform2", properties={
        "color": "Color(0.45, 0.45, 0.45, 1)",
        "polygon": "PackedVector2Array(-100, -10, 100, -10, 100, 10, -100, 10)",
    })
    scene.add_node("Plat2Collision", "CollisionShape2D", parent="Platform2", properties={
        "shape": f'SubResource("{plat2_shape.id}")',
    })

    # Platform 3
    scene.add_node("Platform3", "StaticBody2D", parent=".", properties={
        "position": "Vector2(480, 280)",
    })
    scene.add_node("Plat3Visual", "Polygon2D", parent="Platform3", properties={
        "color": "Color(0.5, 0.5, 0.5, 1)",
        "polygon": "PackedVector2Array(-90, -10, 90, -10, 90, 10, -90, 10)",
    })
    scene.add_node("Plat3Collision", "CollisionShape2D", parent="Platform3", properties={
        "shape": f'SubResource("{plat3_shape.id}")',
    })

    return scene


def build_topdown_scene() -> Scene:
    """Build a simple 2D top-down scene with player and boundary walls."""
    scene = Scene()

    script_res = scene.add_ext_resource("Script", "res://player.gd")

    player_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(32, 32)"})
    wall_h_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(1160, 20)"})
    wall_v_shape = scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(20, 660)"})

    # Root
    scene.add_node("Main", "Node2D")

    # Player
    scene.add_node("Player", "CharacterBody2D", parent=".", properties={
        "position": "Vector2(576, 324)",
        "script": f'ExtResource("{script_res.id}")',
    })
    scene.add_node("PlayerVisual", "Polygon2D", parent="Player", properties={
        "color": "Color(0.25, 0.6, 1, 1)",
        "polygon": "PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)",
    })
    scene.add_node("CollisionShape2D", "CollisionShape2D", parent="Player", properties={
        "shape": f'SubResource("{player_shape.id}")',
    })
    scene.add_node("Camera2D", "Camera2D", parent="Player")

    # Walls
    wall_color = "Color(0.35, 0.35, 0.35, 1)"
    for name, pos, shape, poly in [
        ("WallTop", "Vector2(576, 0)", wall_h_shape, "PackedVector2Array(-580, -10, 580, -10, 580, 10, -580, 10)"),
        ("WallBottom", "Vector2(576, 648)", wall_h_shape, "PackedVector2Array(-580, -10, 580, -10, 580, 10, -580, 10)"),
        ("WallLeft", "Vector2(0, 324)", wall_v_shape, "PackedVector2Array(-10, -330, 10, -330, 10, 330, -10, 330)"),
        ("WallRight", "Vector2(1152, 324)", wall_v_shape, "PackedVector2Array(-10, -330, 10, -330, 10, 330, -10, 330)"),
    ]:
        scene.add_node(name, "StaticBody2D", parent=".", properties={"position": pos})
        scene.add_node(f"{name}Visual", "Polygon2D", parent=name, properties={
            "color": wall_color,
            "polygon": poly,
        })
        scene.add_node(f"{name}Collision", "CollisionShape2D", parent=name, properties={
            "shape": f'SubResource("{shape.id}")',
        })

    return scene


def build_empty_2d_scene() -> Scene:
    scene = Scene()
    scene.add_node("Main", "Node2D")
    return scene


def build_empty_3d_scene() -> Scene:
    scene = Scene()
    scene.add_node("Main", "Node3D")
    return scene


# ---------------------------------------------------------------------------
# Project templates
# ---------------------------------------------------------------------------

AVAILABLE_TEMPLATES = {
    "2d-platformer": "2D platformer with player movement, jump, and platforms",
    "2d-topdown": "2D top-down with player movement and boundary walls",
    "empty-2d": "Empty 2D project with a Node2D root",
    "empty-3d": "Empty 3D project with a Node3D root",
}


def create_project_from_template(
    path: Path,
    name: str,
    template: str = "empty-2d",
) -> list[str]:
    """Create a full Godot 4.x project from template. Returns list of created files."""
    path.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    # project.godot
    proj = GodotProject()
    proj.name = name
    proj.main_scene = "res://main.tscn"
    proj.set("application", "config/features", 'PackedStringArray("4.4", "GL Compatibility")')
    proj.set("rendering", "renderer/rendering_method", '"gl_compatibility"')
    proj.set("rendering", "renderer/rendering_method.mobile", '"gl_compatibility"')

    # Set viewport size
    proj.set("display", "window/size/viewport_width", "1152")
    proj.set("display", "window/size/viewport_height", "648")

    (path / "project.godot").write_text(write_project_file(proj), encoding="utf-8")
    created.append("project.godot")

    # Scene and scripts based on template
    if template == "2d-platformer":
        scene = build_platformer_scene()
        (path / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")
        (path / "player.gd").write_text(PLAYER_PLATFORMER_2D, encoding="utf-8")
        created.extend(["main.tscn", "player.gd"])

    elif template == "2d-topdown":
        scene = build_topdown_scene()
        (path / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")
        (path / "player.gd").write_text(PLAYER_TOPDOWN_2D, encoding="utf-8")
        created.extend(["main.tscn", "player.gd"])

    elif template == "empty-2d":
        scene = build_empty_2d_scene()
        (path / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")
        created.append("main.tscn")

    elif template == "empty-3d":
        scene = build_empty_3d_scene()
        (path / "main.tscn").write_text(write_tscn(scene), encoding="utf-8")
        created.append("main.tscn")

    else:
        raise ValueError(f"Unknown template: {template}. Available: {', '.join(AVAILABLE_TEMPLATES)}")

    # .gitignore for Godot
    gitignore = path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Godot\n.godot/\n*.import\nexport_presets.cfg\n",
            encoding="utf-8",
        )
        created.append(".gitignore")

    return created
