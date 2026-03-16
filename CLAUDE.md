# PlayGen CLI (v0.5.2)

Agent execution layer for Godot 4.x. Lets AI Agents go from idea to playable prototype by providing a complete, closable, observable, and recoverable control plane over Godot projects.

## Architecture
PlayGenCLI is NOT a product surface — it is an **Agent's Godot execution backend**.
- Human → Agent → PlayGenCLI → Godot
- Two execution layers: **text-based** (fast, reliable for scene/script/config) + **engine-native bridge** (authoritative for validation, runtime, complex structures)
- All commands support `--json-output` for structured Agent consumption

## Tech stack
- Python 3.10+ with Click for CLI
- Godot 4.x as game engine (text-based file formats: .tscn, .tres, .gd, project.godot)
- Engine-native bridge: GDScript running in Godot headless mode for authoritative operations
- Agent-agnostic: any AI agent can use this via `--help` and `--json-output` flags

## Project structure
- `src/playgen/` - main package
  - `cli.py` - Click CLI entry point, registers all commands
  - `commands/` - CLI command implementations
    - Scene commands: build, scene, node, script, signal_cmd, analyze
    - Project commands: autoload_cmd, config_cmd, input_cmd, resource_cmd, animation_cmd
    - Asset pipeline: asset_cmd (import, attach, list)
    - Engine bridge: bridge_cmd (validate-scene, read-tree, validate-script, class-props)
    - Safety: snapshot_cmd (save, restore, diff, list, delete)
    - System commands: init_cmd, run_cmd (with --observe), doctor
  - `godot/tscn.py` - .tscn parser/writer (most critical file — handle with care, test round-trips)
  - `godot/project_file.py` - project.godot parser/writer (supports multi-line values)
  - `godot/runner.py` - Godot executable finder and project runner
  - `godot/bridge.py` - Engine-native bridge (GDScript + headless Godot)
  - `godot/observe.py` - Runtime telemetry observer (autoload injection)
  - `templates/` - project/scene/script templates, EXTENDS_DEFAULTS for smart type-specific scripts

## Commands
```
# Scene operations
playgen init        # Initialize Godot project (with templates)
playgen build       # Build complete scene from JSON (highest-leverage command)
playgen analyze     # Show project state (scenes, scripts, resources, signals)
playgen scene       # Scene operations (create, tree, list)
playgen node        # Node operations (add, remove, set, copy, list)
playgen script      # Script operations (create, attach, list)
playgen signal      # Signal operations (connect, list, remove)

# Asset pipeline
playgen asset import   # Copy assets into project
playgen asset attach   # Wire asset to scene node (auto ext_resource)
playgen asset list     # List all project assets by type

# Engine bridge (requires Godot)
playgen bridge validate-scene   # Validate scene via Godot engine
playgen bridge read-tree        # Read instantiated scene tree
playgen bridge validate-script  # Validate GDScript syntax
playgen bridge validate-resources  # Check resource loadability
playgen bridge class-props      # Inspect node type properties
playgen bridge list-types       # List available node types
playgen bridge project-info     # Read project info from engine

# Project management
playgen autoload    # Autoload/singleton management (add, remove, list)
playgen config      # Project settings (set, get, list)
playgen input       # Input mapping (add, remove, list)
playgen resource    # .tres resource files (create, list) — themes, shapes, materials
playgen animation   # Animation operations (add, list) — presets + custom

# Safety & recovery
playgen snapshot save      # Save project state before risky operations
playgen snapshot restore   # Rollback to saved state
playgen snapshot diff      # Compare current state to snapshot
playgen snapshot list      # List available snapshots
playgen snapshot delete    # Remove a snapshot

# System
playgen run             # Run project via Godot CLI, capture output
playgen run --observe   # Run with runtime telemetry (positions, collisions, events)
playgen doctor          # Diagnose and fix common issues
```

## Build command enhancements (v0.5.0)
- `--snapshot NAME` auto-saves project state before build (safety net)
- `--validate` runs engine-native validation after build
- Node definitions support `audio` shorthand (like `texture`)
- Node definitions support `font` shorthand for Label/Button nodes

## Critical implementation details
- **Body types** (Area2D, CharacterBody2D, StaticBody2D, RigidBody2D, + 3D variants): don't have a `shape` property — must create CollisionShape2D/3D child. See `BODY_TYPES` in tscn.py.
- **auto_quote_value()**: Plain strings need quotes in .tscn, but numbers/bools/constructors (Vector2, Color) must NOT be quoted. Used in node add, node set, build.
- **_NODE_RE regex**: Uses greedy `(.*)` not lazy `(.*?)` because `[node ... groups=["a","b"]]` contains `]` inside the header.
- **Round-trip safety**: Any change to tscn.py MUST be tested with parse→modify→write→parse to ensure nothing is lost.
- **Multi-line values in project.godot**: Input maps use multi-line `{...}` values. The parser counts braces to handle these correctly.
- **Bridge script**: Lives in `.playgen/bridge.gd` with `.gdignore` so Godot doesn't import it as game content.
- **Observer autoload**: Injected temporarily during `run --observe`, removed after execution.

## Text layer vs Engine bridge division
- **Text layer** (fast, no Godot needed): scene creation/editing, script generation, project.godot config, signal connections, resource .tres files
- **Engine bridge** (authoritative, needs Godot): scene validation, scene tree reading, script validation, resource loadability checks, class introspection, runtime observation

## Conventions
- All commands support `--json-output` flag for machine-readable output
- Godot project path defaults to current directory, override with `--project`
- Use `GODOT_PATH` env var to specify Godot executable location
- File paths in output use `res://` notation consistent with Godot
- Every code update must include a changelog entry in README.md with version number and date
