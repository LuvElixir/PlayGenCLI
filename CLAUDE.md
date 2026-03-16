# PlayGen CLI (v0.4.0)

Vibe game dev CLI for Godot 4.x. Lets non-game-developers go from idea to playable prototype through AI Agent collaboration.

## Tech stack
- Python 3.10+ with Click for CLI
- Godot 4.x as game engine (text-based file formats: .tscn, .tres, .gd, project.godot)
- Agent-agnostic: any AI agent can use this via `--help` and `--json` flags

## Project structure
- `src/playgen/` - main package
  - `cli.py` - Click CLI entry point, registers all commands
  - `commands/` - CLI command implementations
    - Scene commands: build, scene, node, script, signal_cmd, analyze
    - Project commands: autoload_cmd, config_cmd, input_cmd, resource_cmd, animation_cmd
    - System commands: init_cmd, run_cmd, doctor
  - `godot/tscn.py` - .tscn parser/writer (most critical file — handle with care, test round-trips)
  - `godot/project_file.py` - project.godot parser/writer (supports multi-line values)
  - `godot/runner.py` - Godot executable finder and project runner
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

# Project management
playgen autoload    # Autoload/singleton management (add, remove, list)
playgen config      # Project settings (set, get, list)
playgen input       # Input mapping (add, remove, list)
playgen resource    # .tres resource files (create, list) — themes, shapes, materials
playgen animation   # Animation operations (add, list) — presets + custom

# System
playgen run         # Run project via Godot CLI, capture output
playgen doctor      # Diagnose and fix common issues
```

## Critical implementation details
- **Body types** (Area2D, CharacterBody2D, StaticBody2D, RigidBody2D, + 3D variants): don't have a `shape` property — must create CollisionShape2D/3D child. See `BODY_TYPES` in tscn.py.
- **auto_quote_value()**: Plain strings need quotes in .tscn, but numbers/bools/constructors (Vector2, Color) must NOT be quoted. Used in node add, node set, build.
- **_NODE_RE regex**: Uses greedy `(.*)` not lazy `(.*?)` because `[node ... groups=["a","b"]]` contains `]` inside the header.
- **Round-trip safety**: Any change to tscn.py MUST be tested with parse→modify→write→parse to ensure nothing is lost.
- **Multi-line values in project.godot**: Input maps use multi-line `{...}` values. The parser counts braces to handle these correctly.

## Conventions
- All commands support `--json-output` flag for machine-readable output
- Godot project path defaults to current directory, override with `--project`
- Use `GODOT_PATH` env var to specify Godot executable location
- File paths in output use `res://` notation consistent with Godot
- Every code update must include a changelog entry in README.md with version number and date
