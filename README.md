# PlayGen CLI

Agent execution layer for Godot 4.x. AI Agents go from idea to playable prototype through structured CLI commands with full JSON I/O.

## Install

```bash
pip install -e .
```

## Quick Start

```bash
playgen init --template 2d-platformer    # Create a platformer project
playgen build scene.json                 # Build scene from JSON
playgen run --observe                    # Run with runtime telemetry
playgen analyze                          # See project structure
playgen doctor                           # Check for issues
```

## Commands

| Command | Description |
|---------|-------------|
| **Scene Operations** | |
| `playgen init` | Initialize Godot project (templates: 2d-platformer, 2d-topdown, empty-2d, empty-3d) |
| `playgen build` | Build complete scene from JSON — with autoloads, config, input maps, --snapshot, --validate |
| `playgen analyze` | Show project state (scenes, scripts, resources, signals, sub-resources) |
| `playgen scene` | Scene operations: create, tree, list |
| `playgen node` | Node operations: add, remove, set, copy, list |
| `playgen script` | Script operations: create, attach, list |
| `playgen signal` | Signal operations: connect, list, remove |
| **Asset Pipeline** | |
| `playgen asset import` | Copy images/audio/fonts into project |
| `playgen asset attach` | Wire asset to scene node (auto ext_resource + property) |
| `playgen asset list` | List all project assets by type |
| **Engine Bridge** | |
| `playgen bridge validate-scene` | Validate scene via Godot engine (authoritative) |
| `playgen bridge read-tree` | Read instantiated scene tree from Godot's perspective |
| `playgen bridge validate-script` | Validate GDScript syntax via Godot parser |
| `playgen bridge validate-resources` | Check if resources can be loaded |
| `playgen bridge class-props` | Inspect node type properties from ClassDB |
| `playgen bridge list-types` | List available node types |
| `playgen bridge project-info` | Read project info from engine |
| **Project Management** | |
| `playgen autoload` | Autoload/singleton management: add, remove, list |
| `playgen config` | Project settings: set, get, list |
| `playgen input` | Input mapping: add, remove, list (keyboard, mouse, joypad) |
| `playgen resource` | Resource files: create, list (.tres — themes, shapes, materials) |
| `playgen animation` | Animation: add (with presets), list |
| **Safety & Recovery** | |
| `playgen snapshot save` | Save project state before risky operations |
| `playgen snapshot restore` | Rollback to saved state after failures |
| `playgen snapshot diff` | Compare current state to snapshot |
| `playgen snapshot list` | List available snapshots |
| `playgen snapshot delete` | Remove a snapshot |
| **System** | |
| `playgen run` | Run project via Godot CLI, capture output |
| `playgen run --observe` | Run with runtime telemetry (positions, collisions, events) |
| `playgen run --screenshot N` | Capture screenshot after N frames |
| `playgen doctor` | Diagnose and fix common issues |

All commands support `--json-output` for machine-readable output, making them suitable for any AI Agent.

## Architecture

PlayGenCLI uses a **hybrid execution model**:

- **Text layer** (fast, no Godot needed): scene creation/editing, script generation, project.godot config, signal connections — covers most prototype operations
- **Engine bridge** (authoritative, needs Godot): scene validation, tree reading, script validation, resource checks, class introspection, runtime observation — covers operations where text manipulation is unreliable

## Key Features

- **Asset pipeline**: `asset import` + `asset attach` lets Agents wire images, audio, and fonts into scenes without manual editor interaction
- **Engine-native bridge**: Godot headless mode provides authoritative validation and introspection beyond text parsing
- **Visibility checking**: `build` auto-detects invisible nodes (physics bodies without visual children) — the #1 cause of "commands succeed but nothing on screen"
- **Screenshot capture**: `run --screenshot 60` captures the viewport after 60 frames — Agent or human can verify visual result
- **Runtime observation**: `run --observe` injects telemetry autoload that captures node positions, collisions, scene changes, and custom events — structured JSON feedback for the Agent
- **Snapshot/rollback**: `snapshot save/restore` enables safe multi-step operations with rollback on failure
- **`build` command**: Agent outputs one JSON, gets a complete runnable scene — with `--snapshot` safety net and `--validate` engine check
- **Project management**: `autoload`, `config`, `input`, `resource` commands give full control over project.godot and .tres files
- **Animation system**: Create AnimationPlayer with presets (fade, bounce, pulse, shake, slide, spin) or custom tracks
- **Smart `node add`**: `--script`, `--shape`, `--instance` flags auto-handle ext_resource/sub_resource plumbing
- **11 script templates**: platformer, topdown, ui-controller, state-machine, game-manager, inventory, dialogue, menu, camera-controller, and smart defaults for 14 extends types

## Environment

- Requires Python 3.10+
- Targets Godot 4.x only
- Set `GODOT_PATH` env var or add Godot to PATH for `run`, `bridge`, and `doctor` commands

---

## Changelog

### v0.6.0 — 2026-03-16

**Closing the feedback loop** — the #1 Agent failure mode is "20 commands succeed but nothing appears on screen." v0.6.0 adds visibility detection and screenshot capture to let Agents verify their work.

**Visibility check** (`analyze --check-visibility` + auto in `build`):
- Detects physics nodes (CharacterBody2D, Area2D, etc.) without visual children (Sprite2D, Polygon2D, MeshInstance, etc.)
- `build` now **automatically warns** about invisible nodes in every build output — Agent gets immediate feedback
- Checks instance file existence and script file existence
- Covers 2D + 3D: Sprite2D, AnimatedSprite2D, Polygon2D, MeshInstance3D, CSG shapes, Labels, UI controls, etc.
- Example: `[!!] Enemy (CharacterBody2D) — No visual child node (needs Sprite2D, Polygon2D, ...)`

**Screenshot capture** (`run --screenshot N`):
- `playgen run --screenshot 60` — runs the game, captures viewport after 60 frames, saves PNG
- Can combine with `--observe` for screenshot + telemetry
- Autoload injection/cleanup pattern (same as observer)
- Agent or human can inspect the screenshot to verify visual result

### v0.5.2 — 2026-03-16

Bug fixes and improvements based on Shadow Harvest (2D action roguelike) real-world testing feedback.

**P0 Fixes:**
- **build always outputs error info** — `build` with invalid JSON now outputs error to stdout (not just stderr), so Agents always see failure info. Exit code is reliably non-zero on errors.
- **input add supports mouse/joypad** — New `--mouse/-m` and `--joypad/-j` options: `playgen input add shoot -m left -j x`. Mouse names: left, right, middle, wheel_up, wheel_down. Joypad names: a, b, x, y, lb, rb, start, select.
- **validate-script warns about autoload dependencies** — `bridge validate-script` now detects when a script references autoload singletons and adds warnings, since autoloads aren't loaded in headless validation mode.

**P1 Fixes:**
- **init help text corrected** — Docstring no longer claims `--project` is on init (it's a top-level CLI option).
- **CharacterBody2D template is game-type neutral** — Default template now generates basic movement with `move_and_slide()` without assuming platformer gravity/jump. Use `--template platformer-player` for platformer-specific code.
- **node set/find supports node paths** — `find_node()` and commands using it now accept path format like `HUD/HealthLabel` for sub-node access.
- **scene tree shows instance sources** — Instance nodes now display `(instance=res://enemy.tscn)` instead of empty `()`.
- **script attach warns on missing file** — Warns when the script file doesn't exist on disk (JSON output includes `"warning"` key).
- **signal connect warns about instance targets** — Connecting to an instanced node now warns that the method must exist in the instanced scene's script.
- **analyze recognizes autoload scripts** — Scripts registered as autoloads now show `(autoload: GameManager)` instead of `(unused)`.

**P2 Fixes:**
- **scene create outputs root node name** — `scene create light_orb.tscn` now shows `Created scene: light_orb.tscn (root: LightOrb [Area2D])`. JSON output includes `root_name`.

### v0.5.1 — 2026-03-16

Bug fixes based on 迷宫饭 MVP real-world development feedback. All 4 P0 blockers resolved.

**P0 Fixes:**
- **build scripts.body now writes to file** — Build JSON `scripts` section now accepts both `"body"` and `"content"` keys for inline script content. Previously only `"content"` worked, causing `"body"` content to be silently dropped.
- **bridge.gd Godot 4.6.1 compatibility** — Rewrote bridge GDScript to use explicit type annotations and avoid variable names that shadow built-in classes (`json` → `json_parser`, `err` → `parse_err`, etc.). All bridge commands now work on Godot 4.3+.
- **config set auto-quotes string values** — `playgen config set application/config/name "My Game"` now correctly writes `"My Game"` (with quotes) to project.godot. Numbers, booleans, constructors, and already-quoted values are left as-is. Same fix applied to build command's `config` section.
- **build properties accept non-string JSON values** — Node `properties` in build JSON now accept native JSON types: `"wait_time": 3.0`, `"autostart": true`, `"speed": 300`. Previously these caused `TypeError`.

**P1 Fixes:**
- **run error reporting shows full details** — `playgen run` now always displays Godot stderr output (up to 20 lines) when errors occur, instead of hiding it. Error messages include file path and line number.
- **analyze excludes .playgen directory** — Snapshot files and bridge scripts in `.playgen/` no longer pollute `playgen analyze` output.
- **build output shows full file paths** — Build success message now lists all created files with their full filesystem paths, not just filenames.

### v0.5.0 — 2026-03-16

From "CLI tool" to "Agent execution layer" — PlayGenCLI gains the three capabilities most needed for Agent-driven prototype closure: asset pipeline, engine-native bridge, and runtime observation. Plus snapshot/rollback for multi-step safety.

**New subsystems:**

- **Asset pipeline** (`playgen asset import/attach/list`) — Agents can now import images, audio, and fonts into a project and wire them to scene nodes with auto ext_resource creation. Supports: png, jpg, svg, webp, wav, ogg, mp3, ttf, otf. Solves: "Agent can only make grey-box prototypes."

- **Engine-native bridge** (`playgen bridge`) — Runs GDScript inside Godot headless mode for operations text parsing can't reliably do. Commands: `validate-scene` (does Godot accept this scene?), `read-tree` (what does Godot see after instancing?), `validate-script` (GDScript parse check), `validate-resources` (can Godot load these?), `class-props` (ClassDB introspection), `list-types` (available node types), `project-info`. Solves: "Text-layer edits sometimes produce invalid scenes that only fail at runtime."

- **Runtime observation** (`playgen run --observe`) — Injects a telemetry autoload that captures structured runtime data: node positions (sampled every 30 frames), physics collisions, scene tree changes, and custom events via `PlayGenObserver.log_custom()`. Returns JSON telemetry after execution. Solves: "After `run`, Agent is blind to what happened."

- **Snapshot/rollback** (`playgen snapshot save/restore/diff/list/delete`) — File-copy based project state snapshots. Enables safe multi-step operations: save before risky build, restore on failure. Solves: "Multi-step Agent operations leave project in dirty state on failure."

**Enhanced commands:**

- `build` — New `--snapshot NAME` flag auto-saves project state before building (safety net). New `--validate` flag runs engine-native validation after build. Node definitions now support `audio` and `font` shorthands (alongside existing `texture` and `shape`).
- `run` — New `--observe` flag for runtime telemetry injection/collection.

**Architecture change:**

PlayGenCLI now operates as a hybrid execution layer: text-based operations (fast, no Godot dependency) + engine-native bridge (authoritative, needs Godot). The bridge script lives in `.playgen/bridge.gd` with `.gdignore` to prevent Godot from importing it as game content.

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
