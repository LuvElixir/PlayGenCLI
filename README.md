# PlayGen CLI

Vibe game dev CLI for Godot 4.x. Let non-game-developers go from idea to playable prototype through AI Agent collaboration.

## Install

```bash
pip install -e .
```

## Quick Start

```bash
playgen init --template 2d-platformer    # Create a platformer project
playgen run                              # Run the project
playgen analyze                          # See project structure
playgen doctor                           # Check for issues
```

## Commands

| Command | Description |
|---------|-------------|
| `playgen init` | Initialize Godot project (with templates: 2d-platformer, 2d-topdown, empty-2d, empty-3d) |
| `playgen build` | Build complete scene from JSON description — now with autoloads, config, input maps |
| `playgen analyze` | Show project state (scenes, scripts, resources, signals, sub-resources) |
| `playgen scene` | Scene operations: create, tree, list |
| `playgen node` | Node operations: add, remove, set, copy, list |
| `playgen script` | Script operations: create, attach, list |
| `playgen signal` | Signal operations: connect, list, remove |
| `playgen autoload` | Autoload/singleton management: add, remove, list |
| `playgen config` | Project settings: set, get, list (any project.godot entry) |
| `playgen input` | Input mapping: add, remove, list (keyboard, mouse, joypad) |
| `playgen resource` | Resource files: create, list (.tres — themes, shapes, materials) |
| `playgen animation` | Animation: add (with presets), list |
| `playgen run` | Run project via Godot CLI, capture output |
| `playgen doctor` | Diagnose and fix common issues |

All commands support `--json-output` for machine-readable output, making them suitable for any AI Agent.

## Key Features

- **`build` command**: Agent outputs one JSON, gets a complete runnable scene — now with autoloads, config, and input maps in a single call
- **Project management**: `autoload`, `config`, `input`, `resource` commands give full control over project.godot and .tres files
- **Animation system**: Create AnimationPlayer with presets (fade, bounce, pulse, shake, slide, spin) or custom tracks
- **Smart `node add`**: `--script`, `--shape`, `--instance` flags auto-handle ext_resource/sub_resource plumbing
- **`node set`**: Edit properties, attach scripts, add groups on existing nodes
- **`node copy`**: Duplicate nodes (with children) within a scene
- **Theme presets**: `resource create --preset dark` generates a complete dark UI theme
- **11 script templates**: platformer, topdown, ui-controller, state-machine, game-manager, inventory, dialogue, menu, camera-controller, and smart defaults for 14 extends types
- **Input mapping**: Add keyboard, mouse, joypad bindings with proper Godot 4.x event format
- **Signal management**: Connect, list, remove signal connections via CLI
- **Project analysis**: Full project state including signal connections, sub-resources, script-scene relationships

## Environment

- Requires Python 3.10+
- Targets Godot 4.x only
- Set `GODOT_PATH` env var or add Godot to PATH for `run`/`doctor` commands

---

## Changelog

### v0.4.0 — 2026-03-15

From "scene tool" to "project tool" — based on real-world evaluation building a complete game (Dungeon Meshi MVP). PlayGen now covers the full Godot project lifecycle.

**New commands:**
- `playgen autoload add/remove/list` — Manage autoload singletons (GameManager, AudioBus, etc.). Essential for any game beyond trivial complexity.
- `playgen config set/get/list` — Read/write any project.godot setting. Supports `section/key` format (e.g., `display/window/size/viewport_width`).
- `playgen input add/remove/list` — Input mapping with keyboard, mouse, and joypad support. Generates proper Godot 4.x InputEvent objects. (e.g., `playgen input add jump -k space -k up`)
- `playgen resource create/list` — Create .tres resource files (themes, shapes, materials, etc.). Includes theme presets (`--preset dark/light`).
- `playgen animation add/list` — Add AnimationPlayer with animation presets (fade_in, fade_out, bounce, pulse, shake, slide_in_left/right, spin) or custom value tracks.

**Enhanced commands:**
- `build` — Now supports `"autoloads"`, `"config"`, and `"input_map"` keys in JSON. One JSON can configure the entire project + build a scene.
- `node set` — Now supports `--script` flag to attach/change scripts on existing nodes.
- `node copy` — New subcommand to duplicate nodes (with children) within a scene.

**New script templates:**
- `ui-controller` — Control-based UI management with button handling
- `state-machine` — Finite state machine pattern (idle/walk/attack)
- `game-manager` — Global singleton for score, level, game state
- `inventory-manager` — Item management with add/remove/has/count
- `dialogue-system` — Sequential dialogue with speaker names
- `menu-controller` — Main menu with start/options/quit
- `camera-controller` — Camera2D with smooth follow, zoom, screen shake

**New extends defaults:** Timer, CanvasLayer, Sprite2D, AnimationPlayer

**Infrastructure:**
- `project_file.py` — Parser now handles multi-line values (required for input maps with `{...}` blocks).

### v0.3.0 — 2026-03-14

Three P0 fixes discovered during continued real-world testing with AbyssRunner.

**Fixes:**
- P0: `--shape` on body types (Area2D, CharacterBody2D, etc.) — Previously wrote `shape = SubResource(...)` directly on the body node, which is invalid. Now correctly auto-creates a `CollisionShape2D` (or `CollisionShape3D`) child node with the shape property. Applies to `node add` and `build` commands.
- P0: Groups round-trip loss — Groups like `groups=["keys", "collectibles"]` were lost during parse→modify→write because the `_NODE_RE` regex used lazy `(.*?)` matching, which truncated at the first `]` inside the groups array. Fixed with greedy `(.*)` matching.
- P0: String auto-quoting — Plain string property values (e.g., `key_id=red`) were written without quotes, causing Godot parse errors. Added `auto_quote_value()` that correctly distinguishes numbers, booleans, Godot constructors (Vector2, Color, etc.), and resource references from plain strings. Applied in `node add`, `node set`, and `build`.

**Enhancements:**
- `node add` / `node set` — New `--group` / `-g` flag to add nodes to groups.
- `build` command — Supports `"groups"` array on node definitions.
- `scene tree` — Now displays groups in tree output (e.g., `[groups: keys, collectibles]`).
- Full 2D + 3D body type support: Area2D/3D, CharacterBody2D/3D, StaticBody2D/3D, RigidBody2D/3D, AnimatableBody2D/3D.

### v0.2.0 — 2026-03-14

Based on real-world feedback from building a complete game (AbyssRunner) with v0.1.

**New commands:**
- `playgen build` — Build complete scene from JSON description via file or stdin. One JSON input produces a full scene with nodes, sub-resources, ext_resources, scripts, and signal connections. This is the highest-leverage command for Agent-driven development.
- `playgen signal connect/list/remove` — Full signal connection management.
- `playgen node set` — Edit properties on existing nodes without delete+recreate.

**Enhanced commands:**
- `node add` — New `--script`, `--shape`, `--instance` flags. `--script player.gd` auto-creates ext_resource declaration and sets the reference. `--shape RectangleShape2D:28,44` auto-creates SubResource. `--instance coin.tscn` instances a sub-scene.
- `script create` — Smart templates by extends type. `--extends CharacterBody2D` generates physics movement+jump code. `--extends Area2D` generates body_entered signal handler. No more empty `pass` stubs.
- `analyze` — Now includes signal connections, sub-resource counts and details in both human-readable and JSON output.

**Fixes:**
- P0: SubResource system — CLI can now create and reference SubResources (collision shapes, etc.)
- P0: Script auto-mounting — `node add --script` and `script attach` both properly handle ext_resource declarations
- P0: Signal connections — Full CRUD via `playgen signal`
- P1: Batch operations — `playgen build` replaces 20+ sequential commands with one JSON input
- P1: Scene instancing — Supported via `node add --instance` and `build` command
- P1: Node property editing — `node set` command
- P2: Enhanced analyze output — Signals, sub-resources, connection details

### v0.1.0 — 2026-03-14

Initial release.

- Project initialization with templates (2d-platformer, 2d-topdown, empty-2d, empty-3d)
- Scene operations (create, tree, list)
- Node operations (add, remove, list)
- Script operations (create, attach, list)
- Project analysis with scene/script/resource relationships
- Godot project runner with error capture and parsing
- Doctor command for diagnosing and fixing common issues
- All commands support `--json-output` for AI Agent consumption
- Godot 4.x text file format parser/writer (.tscn, project.godot)
