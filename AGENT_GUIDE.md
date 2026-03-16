# PlayGenCLI Agent Prompt Guide

How to use PlayGenCLI effectively as an AI Agent building Godot 4.x prototypes.

## Core Principle

PlayGenCLI is your Godot execution backend. You output structured commands, it handles all file format details, resource plumbing, and validation. You never need to write `.tscn` files directly.

## The One Command You Must Know

`playgen build` takes a single JSON and produces a complete, runnable Godot scene. This is your highest-leverage command — use it instead of chaining 20+ individual commands.

```json
{
  "scene": "main.tscn",
  "autoloads": {"GameManager": "game_manager.gd"},
  "config": {
    "display/window/size/viewport_width": 1152,
    "display/window/size/viewport_height": 648
  },
  "input_map": {
    "jump": ["space", "up"],
    "attack": ["mouse_left"],
    "move_left": ["a", "left"],
    "move_right": ["d", "right"]
  },
  "scripts": {
    "player.gd": {
      "template": "platformer-player",
      "vars": {"SPEED": "400.0", "JUMP_VELOCITY": "-500.0"}
    },
    "game_manager.gd": {"template": "game-manager"}
  },
  "root": {
    "name": "Main", "type": "Node2D",
    "children": [
      {
        "name": "Player", "type": "CharacterBody2D",
        "script": "player.gd",
        "shape": "RectangleShape2D:28,44",
        "collision_layer": [1],
        "collision_mask": [1, 2],
        "children": [
          {"name": "Sprite", "type": "Sprite2D", "texture": "player.png"},
          {"name": "Camera", "type": "Camera2D"}
        ]
      },
      {
        "name": "Floor", "type": "StaticBody2D",
        "properties": {"position": "Vector2(576, 600)"},
        "shape": "RectangleShape2D:1200,40",
        "collision_layer": [1],
        "children": [
          {"name": "Visual", "type": "ColorRect",
           "color": "Color(0.3, 0.3, 0.3, 1)",
           "size": [1200, 40]}
        ]
      },
      {"name": "ScoreLabel", "text": "Score: 0",
       "properties": {"position": "Vector2(20, 20)"}}
    ]
  },
  "connections": [
    {"signal": "body_entered", "from": "CoinArea", "to": ".", "method": "_on_coin_collected"}
  ]
}
```

Run it:
```bash
playgen build scene.json --json-output
# or pipe from stdin:
echo '{"scene":"main.tscn","root":{"name":"Main","type":"Node2D"}}' | playgen build --json-output -
```

## Build Shorthands

These eliminate the most common boilerplate. Use them instead of manually creating ext_resources and sub_resources.

| Shorthand | What it does | Example |
|-----------|-------------|---------|
| `"script"` | Creates ext_resource + attaches | `"script": "player.gd"` |
| `"texture"` | Creates Texture2D ext_resource | `"texture": "icon.png"` |
| `"audio"` | Creates AudioStream ext_resource | `"audio": "bgm.ogg"` |
| `"font"` | Creates FontFile ext_resource | `"font": "pixel.ttf"` |
| `"shape"` | Inline collision shape | `"shape": "RectangleShape2D:30,50"` |
| `"text"` | Sets text property | `"text": "Game Over"` |
| `"color"` | Sets color/modulate | `"color": "Color(1, 0, 0, 1)"` |
| `"size"` | Sets custom_minimum_size | `"size": [200, 100]` |
| `"collision_layer"` | Collision layer bitmask | `"collision_layer": [1, 3]` |
| `"collision_mask"` | Collision mask bitmask | `"collision_mask": [1, 2]` |
| `"instance"` | Instance sub-scene | `"instance": "enemy.tscn"` |
| `"groups"` | Add to groups | `"groups": ["enemies"]` |

### Type inference

If you omit `"type"`, build infers it from context:

| Shorthand present | Inferred type |
|-------------------|---------------|
| `"texture"` | `Sprite2D` |
| `"audio"` | `AudioStreamPlayer` |
| `"text"` | `Label` |
| `"font"` | `Label` |

Example — no `"type"` needed:
```json
{"name": "Title", "text": "My Game"}
{"name": "BGM", "audio": "music.ogg"}
{"name": "Icon", "texture": "player.png"}
```

### Auto-visual placeholders

Body types (`CharacterBody2D`, `Area2D`, `StaticBody2D`, `RigidBody2D`, etc.) without visual children automatically get a colored `Polygon2D` placeholder. This prevents the #1 failure mode: "scene runs but nothing visible on screen."

The placeholder is sized to match the collision shape if one is provided. Replace it with a proper `Sprite2D` + texture when assets are available.

### Inline shape syntax

```
"shape": "RectangleShape2D:width,height"
"shape": "CircleShape2D:radius"
"shape": "CapsuleShape2D:radius,height"
```

For body types (`CharacterBody2D`, `Area2D`, etc.), this auto-creates a `CollisionShape2D` child node — you don't need to create it manually.

### Collision layers

Accept either an integer bitmask or a list of 1-based layer numbers:

```json
"collision_layer": 5          // bitmask directly
"collision_layer": [1, 3]     // layers 1 and 3 → bitmask 5
"collision_mask": [1, 2, 3]   // layers 1-3 → bitmask 7
```

## Script Templates

Available via `"template"` key in the `scripts` section:

| Template | Use case |
|----------|----------|
| `platformer-player` | Side-scrolling movement + jump |
| `topdown-player` | 4-direction movement |
| `ui-controller` | Button/label UI management |
| `state-machine` | FSM pattern (idle/walk/attack) |
| `game-manager` | Global score/level/pause singleton |
| `inventory-manager` | Item add/remove/count |
| `dialogue-system` | Line-by-line dialogue display |
| `menu-controller` | Main menu with start/options/quit |
| `camera-controller` | Smooth follow + zoom + screen shake |

### Template variables

Override constants in templates with `"vars"`:

```json
"scripts": {
  "player.gd": {
    "template": "platformer-player",
    "vars": {"SPEED": "500.0", "JUMP_VELOCITY": "-600.0"}
  }
}
```

Available variables per template:
- `platformer-player`: `SPEED` (default 300.0), `JUMP_VELOCITY` (default -450.0)
- `topdown-player`: `SPEED` (default 200.0)
- `extends: CharacterBody2D`: `SPEED` (default 200.0)

If not using a template, you can write inline scripts:
```json
"scripts": {
  "enemy.gd": {
    "body": "extends CharacterBody2D\n\nfunc _physics_process(delta):\n\tpass\n"
  }
}
```

## Recommended Workflow

### 1. Initialize project
```bash
playgen init --template 2d-platformer
```

### 2. Build scenes with JSON
```bash
playgen build game.json --json-output --snapshot before_build
```

Always use `--json-output` so you can parse the result. Use `--snapshot` before complex builds for rollback safety.

### 3. Verify the result
```bash
# Structure check (fast, no Godot needed):
playgen analyze --check-visibility --json-output

# Engine validation (authoritative, needs Godot):
playgen build game.json --validate

# Visual verification (needs Godot):
playgen run --screenshot 60 --json-output

# Runtime behavior (needs Godot):
playgen run --observe --json-output --timeout 10
```

### 4. Iterate
```bash
# Modify individual nodes:
playgen node set main.tscn Player -P position "Vector2(100, 200)"

# Add new nodes:
playgen node add main.tscn Enemy CharacterBody2D --parent . --shape "RectangleShape2D:24,24"

# Connect signals:
playgen signal connect main.tscn body_entered Enemy . _on_enemy_hit
```

### 5. Recover from failures
```bash
playgen snapshot restore before_build
```

## Common Patterns

### Player with movement
```json
{
  "scene": "main.tscn",
  "scripts": {
    "player.gd": {"template": "platformer-player", "vars": {"SPEED": "350.0"}}
  },
  "root": {
    "name": "Main", "type": "Node2D",
    "children": [{
      "name": "Player", "type": "CharacterBody2D",
      "script": "player.gd",
      "shape": "RectangleShape2D:28,44",
      "children": [
        {"name": "Sprite", "type": "Sprite2D", "texture": "player.png"},
        {"name": "Camera", "type": "Camera2D"}
      ]
    }]
  }
}
```

### Collectible with signal
```json
{
  "name": "Coin", "type": "Area2D",
  "shape": "CircleShape2D:16",
  "groups": ["collectibles"],
  "children": [
    {"name": "Sprite", "type": "Sprite2D", "texture": "coin.png"}
  ]
}
```
Plus connection:
```json
"connections": [
  {"signal": "body_entered", "from": "Coin", "to": ".", "method": "_on_coin_collected"}
]
```

### HUD with labels
```json
{
  "name": "HUD", "type": "CanvasLayer",
  "children": [
    {"name": "ScoreLabel", "text": "Score: 0",
     "properties": {"position": "Vector2(20, 10)"}},
    {"name": "HealthLabel", "text": "HP: 100",
     "properties": {"position": "Vector2(20, 40)"}},
    {"name": "MessageLabel", "text": "",
     "properties": {"position": "Vector2(400, 300)", "visible": false}}
  ]
}
```

### Tilemap-style level with walls
```json
{
  "name": "Walls", "type": "Node2D",
  "children": [
    {"name": "Floor", "type": "StaticBody2D",
     "properties": {"position": "Vector2(576, 620)"},
     "shape": "RectangleShape2D:1200,40",
     "children": [{"name": "V", "type": "ColorRect", "color": "Color(0.3, 0.3, 0.3, 1)", "size": [1200, 40]}]},
    {"name": "WallLeft", "type": "StaticBody2D",
     "properties": {"position": "Vector2(0, 310)"},
     "shape": "RectangleShape2D:20,620",
     "children": [{"name": "V", "type": "ColorRect", "color": "Color(0.3, 0.3, 0.3, 1)", "size": [20, 620]}]}
  ]
}
```

### Game manager autoload
```json
{
  "autoloads": {"GameManager": "game_manager.gd"},
  "scripts": {"game_manager.gd": {"template": "game-manager"}}
}
```

## Critical Rules

1. **Always use `--json-output`** — Parse structured output, don't scrape text.
2. **Use `build` for new scenes** — One JSON = complete scene. Don't chain 20 `node add` commands.
3. **Use `node set` / `node add` for edits** — After initial build, modify with targeted commands.
4. **Check visibility after build** — The output tells you if nodes will be invisible. Fix before running.
5. **Body types need visual children** — `CharacterBody2D`, `Area2D`, etc. are invisible by themselves. Add `Sprite2D`, `Polygon2D`, or `ColorRect` children. Build auto-creates placeholders, but replace them with real visuals.
6. **Body types need collision shapes** — Use the `"shape"` shorthand. It auto-creates `CollisionShape2D` children for body types.
7. **Use `--snapshot` for safety** — Before complex multi-step operations, snapshot the project state.
8. **Verify visually** — Use `playgen run --screenshot 60` to capture what the game looks like. If the screenshot is black/empty, your nodes are invisible or off-screen.
9. **Check positions** — Nodes at `Vector2(0, 0)` stack on the top-left corner. Spread them out.
10. **Use templates with vars** — Don't write movement code from scratch. Use `platformer-player` or `topdown-player` with custom `SPEED` values.

## Command Quick Reference

```bash
# Project lifecycle
playgen init --template 2d-platformer
playgen build scene.json --json-output [--snapshot NAME] [--validate]
playgen analyze --check-visibility --json-output
playgen run --json-output [--observe] [--screenshot 60] [--timeout 10]
playgen doctor --json-output

# Node operations
playgen node add SCENE NAME TYPE --parent PARENT [-P key value] [--script file.gd] [--shape "RectangleShape2D:w,h"]
playgen node set SCENE NAME -P key value
playgen node remove SCENE NAME
playgen node list SCENE --json-output

# Scene operations
playgen scene create SCENE [--root-type Node2D]
playgen scene tree SCENE
playgen scene list --json-output

# Script operations
playgen script create FILE [--extends TYPE] [--template NAME]
playgen script attach SCENE NODE SCRIPT

# Signal operations
playgen signal connect SCENE SIGNAL FROM TO METHOD
playgen signal list SCENE --json-output

# Assets
playgen asset import FILE [--type image|audio|font]
playgen asset attach SCENE NODE ASSET
playgen asset list --json-output

# Project config
playgen autoload add NAME SCRIPT
playgen config set SECTION/KEY VALUE
playgen input add ACTION -k KEY [-m MOUSE] [-j JOYPAD]
playgen resource create FILE TYPE [--properties ...]
playgen animation add SCENE NODE ANIM [--preset bounce|fade|shake|...]

# Safety
playgen snapshot save NAME
playgen snapshot restore NAME
playgen snapshot diff NAME

# Engine bridge (requires Godot)
playgen bridge validate-scene SCENE
playgen bridge read-tree SCENE
playgen bridge validate-script SCRIPT
playgen bridge class-props TYPE
```

## Debugging Checklist

When something doesn't work:

1. **Nothing on screen?**
   - Run `playgen analyze --check-visibility` — are body nodes missing visual children?
   - Check positions — are nodes at (0,0) overlapping?
   - Run `playgen run --screenshot 60` — is the viewport capturing anything?

2. **Script errors?**
   - Run `playgen bridge validate-script FILE.gd` — syntax check
   - Check for autoload references — they don't load in headless validation

3. **Scene won't load?**
   - Run `playgen bridge validate-scene SCENE.tscn` — engine-native validation
   - Check `playgen analyze --json-output` for missing references

4. **Input not working?**
   - Check `playgen input list` — is the action mapped?
   - Verify script uses matching action names (`Input.is_action_pressed("action_name")`)

5. **Collisions not working?**
   - Check collision layers/masks — do they overlap?
   - Verify collision shapes exist (`playgen scene tree SCENE`)
   - Body types need `CollisionShape2D` children with shapes assigned
