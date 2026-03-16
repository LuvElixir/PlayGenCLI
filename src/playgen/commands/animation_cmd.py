"""playgen animation - Create animations in scenes."""

from __future__ import annotations

import json
import random
import string
from pathlib import Path

import click

from playgen.godot.tscn import parse_tscn, write_tscn, SubResource, _gen_id


# ---------------------------------------------------------------------------
# Animation presets: common game animations
# ---------------------------------------------------------------------------

def _anim_id() -> str:
    return f"Animation_{''.join(random.choices(string.ascii_lowercase + string.digits, k=5))}"


def _lib_id() -> str:
    return f"AnimationLibrary_{''.join(random.choices(string.ascii_lowercase + string.digits, k=5))}"


ANIMATION_PRESETS: dict[str, dict] = {
    "fade_in": {
        "length": 0.5,
        "tracks": [{
            "path": "{target}:modulate",
            "values": ["Color(1, 1, 1, 0)", "Color(1, 1, 1, 1)"],
        }],
    },
    "fade_out": {
        "length": 0.5,
        "tracks": [{
            "path": "{target}:modulate",
            "values": ["Color(1, 1, 1, 1)", "Color(1, 1, 1, 0)"],
        }],
    },
    "bounce": {
        "length": 0.4,
        "tracks": [{
            "path": "{target}:scale",
            "times": [0, 0.15, 0.3, 0.4],
            "values": ["Vector2(1, 1)", "Vector2(1.2, 0.8)", "Vector2(0.9, 1.1)", "Vector2(1, 1)"],
        }],
    },
    "pulse": {
        "length": 0.6,
        "tracks": [{
            "path": "{target}:modulate",
            "times": [0, 0.3, 0.6],
            "values": ["Color(1, 1, 1, 1)", "Color(1.5, 1.5, 1.5, 1)", "Color(1, 1, 1, 1)"],
        }],
    },
    "shake": {
        "length": 0.3,
        "tracks": [{
            "path": "{target}:position",
            "times": [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
            "values": [
                "Vector2(0, 0)", "Vector2(-5, 3)", "Vector2(4, -2)",
                "Vector2(-3, 4)", "Vector2(5, -1)", "Vector2(-2, 2)", "Vector2(0, 0)",
            ],
        }],
    },
    "slide_in_left": {
        "length": 0.4,
        "tracks": [{
            "path": "{target}:position:x",
            "type": "value",
            "values": ["-200.0", "0.0"],
        }],
    },
    "slide_in_right": {
        "length": 0.4,
        "tracks": [{
            "path": "{target}:position:x",
            "type": "value",
            "values": ["200.0", "0.0"],
        }],
    },
    "spin": {
        "length": 1.0,
        "tracks": [{
            "path": "{target}:rotation",
            "times": [0, 1.0],
            "values": ["0.0", "6.28318"],
        }],
    },
}


def _build_animation_props(
    name: str,
    length: float,
    tracks: list[dict],
    loop: bool = False,
) -> dict[str, str]:
    """Build sub-resource properties for an Animation."""
    props: dict[str, str] = {
        "resource_name": f'"{name}"',
        "length": str(length),
    }
    if loop:
        props["loop_mode"] = "1"

    for i, track in enumerate(tracks):
        prefix = f"tracks/{i}"
        props[f"{prefix}/type"] = '"value"'
        props[f"{prefix}/imported"] = "false"
        props[f"{prefix}/enabled"] = "true"
        props[f"{prefix}/path"] = f'NodePath("{track["path"]}")'
        props[f"{prefix}/interp"] = str(track.get("interp", 1))
        props[f"{prefix}/loop_wrap"] = "true"

        times = track.get("times")
        values = track["values"]
        if times is None:
            # Auto-generate evenly spaced times
            if len(values) == 1:
                times = [0]
            else:
                times = [round(i * length / (len(values) - 1), 4) for i in range(len(values))]

        times_str = ", ".join(str(t) for t in times)
        transitions_str = ", ".join("1" for _ in times)
        values_str = ", ".join(str(v) for v in values)

        props[f"{prefix}/keys"] = (
            f'{{\n"times": PackedFloat32Array({times_str}),\n'
            f'"transitions": PackedFloat32Array({transitions_str}),\n'
            f'"update": 0,\n'
            f'"values": [{values_str}]\n}}'
        )

    return props


@click.group("animation")
def animation_cmd() -> None:
    """Animation operations: add AnimationPlayer and animations to scenes.

    \b
    Presets: fade_in, fade_out, bounce, pulse, shake,
             slide_in_left, slide_in_right, spin
    """
    pass


@animation_cmd.command("add")
@click.argument("scene")
@click.option("--player", "-p", default="AnimationPlayer",
              help="AnimationPlayer node name (default: AnimationPlayer)")
@click.option("--parent", default=".", help="Parent node for the AnimationPlayer")
@click.option("--name", "-n", "anim_name", required=True, help="Animation name")
@click.option("--preset", default=None,
              help="Use a preset animation (fade_in, bounce, pulse, shake, etc.)")
@click.option("--target", "-t", default="..",
              help="Target node path for preset (relative to AnimationPlayer, default: '..')")
@click.option("--length", "-l", default=1.0, help="Animation length in seconds")
@click.option("--loop", is_flag=True, help="Loop the animation")
@click.option("--track", "tracks_raw", multiple=True,
              help="Track as 'node:property=from,to' (e.g., '..:modulate=Color(1,1,1,0),Color(1,1,1,1)')")
@click.option("--list-presets", is_flag=True, help="List available animation presets")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def animation_add(
    ctx: click.Context, scene: str, player: str, parent: str,
    anim_name: str, preset: str | None, target: str,
    length: float, loop: bool, tracks_raw: tuple[str, ...],
    list_presets: bool, as_json: bool,
) -> None:
    """Add an animation to a scene.

    SCENE is the scene filename (e.g., 'main.tscn').

    \b
    Examples:
      playgen animation add main -n fade_in --preset fade_in --target Player
      playgen animation add main -n bounce --preset bounce -t Sprite
      playgen animation add main -n custom -l 0.5 --track "..:scale=Vector2(1,1),Vector2(2,2)"
      playgen animation add main -n idle --preset pulse -t Player --loop
    """
    if list_presets:
        if as_json:
            click.echo(json.dumps(list(ANIMATION_PRESETS.keys())))
        else:
            click.echo("Available presets:")
            for name, data in ANIMATION_PRESETS.items():
                click.echo(f"  {name:20s} (length: {data['length']}s)")
        return

    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"
    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))

    # Build tracks
    tracks: list[dict] = []
    if preset and preset in ANIMATION_PRESETS:
        preset_data = ANIMATION_PRESETS[preset]
        length = preset_data["length"]
        for t in preset_data["tracks"]:
            track = dict(t)
            track["path"] = track["path"].replace("{target}", target)
            tracks.append(track)
    elif tracks_raw:
        for tr in tracks_raw:
            # Parse: "node:prop=val1,val2,val3"
            if "=" not in tr:
                click.echo(f"Error: track format must be 'path=val1,val2,...'", err=True)
                ctx.exit(1)
                return
            path_part, values_part = tr.split("=", 1)
            # Split values carefully (respecting parentheses)
            values = _split_values(values_part)
            tracks.append({"path": path_part, "values": values})
    else:
        click.echo("Error: provide --preset or --track", err=True)
        ctx.exit(1)
        return

    # Create animation sub-resource
    anim_props = _build_animation_props(anim_name, length, tracks, loop)
    anim_sub = scene_obj.add_sub_resource("Animation", anim_props)

    # Create or find AnimationLibrary
    lib_sub = None
    for sr in scene_obj.sub_resources:
        if sr.type == "AnimationLibrary":
            # Append to existing library
            existing = sr.properties.get("_data", "{}")
            # Insert before closing brace
            new_entry = f'&"{anim_name}": SubResource("{anim_sub.id}")'
            if existing.strip() == "{}":
                sr.properties["_data"] = f'{{\n{new_entry}\n}}'
            else:
                sr.properties["_data"] = existing.rstrip("}").rstrip() + f',\n{new_entry}\n}}'
            lib_sub = sr
            break

    if lib_sub is None:
        lib_sub = scene_obj.add_sub_resource("AnimationLibrary", {
            "_data": f'{{\n&"{anim_name}": SubResource("{anim_sub.id}")\n}}',
        })

    # Create or find AnimationPlayer node
    player_node = scene_obj.find_node(player)
    if player_node is None:
        scene_obj.add_node(player, "AnimationPlayer", parent=parent, properties={
            "libraries": f'{{\n&"": SubResource("{lib_sub.id}")\n}}',
        })

    scene_path.write_text(write_tscn(scene_obj), encoding="utf-8")

    if as_json:
        click.echo(json.dumps({
            "animation": anim_name, "player": player, "scene": scene,
            "length": length, "tracks": len(tracks),
        }))
    else:
        click.echo(f"Animation added: {anim_name} (length: {length}s, tracks: {len(tracks)}) -> {player}")


@animation_cmd.command("list")
@click.argument("scene")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def animation_list(ctx: click.Context, scene: str, as_json: bool) -> None:
    """List all animations in a scene."""
    project_path: Path = ctx.obj["project_path"]
    if not scene.endswith(".tscn"):
        scene += ".tscn"
    scene_path = project_path / scene
    if not scene_path.exists():
        msg = f"{scene} not found"
        if as_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        ctx.exit(1)
        return

    scene_obj = parse_tscn(scene_path.read_text(encoding="utf-8"))
    anims: list[dict[str, str]] = []
    for sr in scene_obj.sub_resources:
        if sr.type == "Animation":
            name = sr.properties.get("resource_name", "").strip('"')
            length = sr.properties.get("length", "0")
            # Count tracks
            track_count = 0
            for k in sr.properties:
                if k.endswith("/type"):
                    track_count += 1
            anims.append({"name": name, "length": length, "tracks": str(track_count)})

    if as_json:
        click.echo(json.dumps(anims, indent=2))
    else:
        if not anims:
            click.echo("No animations found.")
            return
        for a in anims:
            click.echo(f"  {a['name']:25s} length={a['length']}s  tracks={a['tracks']}")


def _split_values(s: str) -> list[str]:
    """Split comma-separated values, respecting parentheses."""
    values: list[str] = []
    depth = 0
    current = ""
    for ch in s:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            if current.strip():
                values.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        values.append(current.strip())
    return values
