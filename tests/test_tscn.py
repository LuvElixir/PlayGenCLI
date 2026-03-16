"""Tests for playgen.godot.tscn — .tscn parser/writer round-trip safety.

This is the most critical test file. Any regression in tscn.py means
corrupted scene files, which means Godot can't open projects.
"""

import pytest
from playgen.godot.tscn import (
    auto_quote_value,
    parse_tscn,
    write_tscn,
    Scene,
    SceneNode,
    ExtResource,
    SubResource,
    Connection,
    BODY_TYPES,
    BODY_TYPES_2D,
    BODY_TYPES_3D,
)


# ─── auto_quote_value ───────────────────────────────────────────────

class TestAutoQuoteValue:
    """auto_quote_value must quote plain strings but leave
    numbers, booleans, constructors, and references alone."""

    # Should NOT be quoted
    @pytest.mark.parametrize("value", [
        "42", "-7", "3.14", "-0.5", "0",         # Numbers
        "0xFF", "0x0A",                            # Hex
        "true", "false", "null", "inf", "nan", "-inf",  # Keywords
    ])
    def test_no_quote_numbers_and_keywords(self, value):
        assert auto_quote_value(value) == value

    @pytest.mark.parametrize("value", [
        'Vector2(100, 200)',
        'Vector3(1, 2, 3)',
        'Vector2i(10, 20)',
        'Color(1, 0, 0, 1)',
        'Rect2(0, 0, 100, 200)',
        'Rect2i(0, 0, 100, 200)',
        'Transform2D(1, 0, 0, 1, 0, 0)',
        'Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)',
        'Basis(1, 0, 0, 0, 1, 0, 0, 0, 1)',
        'Quaternion(0, 0, 0, 1)',
        'Plane(0, 1, 0, 0)',
        'AABB(0, 0, 0, 1, 1, 1)',
    ])
    def test_no_quote_constructors(self, value):
        assert auto_quote_value(value) == value

    @pytest.mark.parametrize("value", [
        'PackedStringArray("a", "b")',
        'PackedVector2Array()',
        'PackedInt32Array(1, 2, 3)',
        'PackedFloat64Array(1.0)',
        'PackedByteArray()',
        'PackedColorArray()',
    ])
    def test_no_quote_packed_arrays(self, value):
        assert auto_quote_value(value) == value

    @pytest.mark.parametrize("value", [
        'ExtResource("1_abc")',
        'SubResource("shape_1")',
    ])
    def test_no_quote_resource_refs(self, value):
        assert auto_quote_value(value) == value

    def test_no_quote_string_name(self):
        assert auto_quote_value('&"my_signal"') == '&"my_signal"'

    def test_no_quote_node_path(self):
        assert auto_quote_value('^"Player/Sprite"') == '^"Player/Sprite"'

    def test_no_quote_already_quoted(self):
        assert auto_quote_value('"hello world"') == '"hello world"'

    def test_no_quote_array_dict(self):
        assert auto_quote_value('Array(["a"])') == 'Array(["a"])'
        assert auto_quote_value('Dictionary({})') == 'Dictionary({})'

    # SHOULD be quoted
    @pytest.mark.parametrize("value,expected", [
        ("hello", '"hello"'),
        ("my string", '"my string"'),
        ("red", '"red"'),
        ("player_idle", '"player_idle"'),
        ("res://icon.png", '"res://icon.png"'),  # paths need quotes in .tscn
    ])
    def test_quote_plain_strings(self, value, expected):
        assert auto_quote_value(value) == expected

    def test_does_not_double_quote(self):
        """Already-quoted strings must not get double-quoted."""
        result = auto_quote_value('"already quoted"')
        assert result == '"already quoted"'
        assert result.count('"') == 2  # exactly the original quotes


# ─── parse_tscn ─────────────────────────────────────────────────────

MINIMAL_SCENE = """\
[gd_scene format=3 uid="uid://test123"]

[node name="Root" type="Node2D"]
"""

SCENE_WITH_EXT_RESOURCES = """\
[gd_scene load_steps=3 format=3 uid="uid://test456"]

[ext_resource type="Script" path="res://player.gd" id="1_abc"]
[ext_resource type="Texture2D" path="res://icon.png" id="2_def"]

[node name="Main" type="Node2D"]

[node name="Player" type="CharacterBody2D" parent="."]
script = ExtResource("1_abc")

[node name="Sprite" type="Sprite2D" parent="Player"]
texture = ExtResource("2_def")
"""

SCENE_WITH_SUB_RESOURCES = """\
[gd_scene load_steps=2 format=3 uid="uid://test789"]

[sub_resource type="RectangleShape2D" id="SubResource_1"]
size = Vector2(28, 44)

[node name="Main" type="Node2D"]

[node name="Player" type="CharacterBody2D" parent="."]

[node name="Collision" type="CollisionShape2D" parent="Player"]
shape = SubResource("SubResource_1")
"""

SCENE_WITH_GROUPS = """\
[gd_scene format=3 uid="uid://grp"]

[node name="Main" type="Node2D"]

[node name="Coin" type="Area2D" parent="." groups=["collectibles", "interactable"]]

[node name="Key" type="Area2D" parent="." groups=["keys"]]
"""

SCENE_WITH_CONNECTIONS = """\
[gd_scene format=3 uid="uid://conn"]

[node name="Main" type="Node2D"]

[node name="Button" type="Button" parent="."]

[connection signal="pressed" from="Button" to="." method="_on_button_pressed"]
[connection signal="mouse_entered" from="Button" to="." method="_on_mouse_enter"]
"""

SCENE_WITH_INSTANCE = """\
[gd_scene load_steps=2 format=3 uid="uid://inst"]

[ext_resource type="PackedScene" path="res://coin.tscn" id="1_coin"]

[node name="Main" type="Node2D"]

[node name="Coin1" parent="." instance=ExtResource("1_coin")]
"""


class TestParseTscn:

    def test_parse_minimal(self):
        scene = parse_tscn(MINIMAL_SCENE)
        assert scene.uid == "uid://test123"
        assert len(scene.nodes) == 1
        root = scene.get_root()
        assert root.name == "Root"
        assert root.type == "Node2D"
        assert root.parent is None

    def test_parse_ext_resources(self):
        scene = parse_tscn(SCENE_WITH_EXT_RESOURCES)
        assert len(scene.ext_resources) == 2
        assert scene.ext_resources[0].type == "Script"
        assert scene.ext_resources[0].path == "res://player.gd"
        assert scene.ext_resources[1].type == "Texture2D"

    def test_parse_node_properties(self):
        scene = parse_tscn(SCENE_WITH_EXT_RESOURCES)
        player = scene.find_node("Player")
        assert player is not None
        assert player.type == "CharacterBody2D"
        assert player.parent == "."
        assert "script" in player.properties

    def test_parse_sub_resources(self):
        scene = parse_tscn(SCENE_WITH_SUB_RESOURCES)
        assert len(scene.sub_resources) == 1
        sr = scene.sub_resources[0]
        assert sr.type == "RectangleShape2D"
        assert sr.properties["size"] == "Vector2(28, 44)"

    def test_parse_groups(self):
        scene = parse_tscn(SCENE_WITH_GROUPS)
        coin = scene.find_node("Coin")
        assert coin is not None
        assert coin.groups == ["collectibles", "interactable"]
        key = scene.find_node("Key")
        assert key.groups == ["keys"]

    def test_parse_connections(self):
        scene = parse_tscn(SCENE_WITH_CONNECTIONS)
        assert len(scene.connections) == 2
        assert scene.connections[0].signal_name == "pressed"
        assert scene.connections[0].from_node == "Button"
        assert scene.connections[0].to_node == "."
        assert scene.connections[0].method == "_on_button_pressed"

    def test_parse_instance(self):
        scene = parse_tscn(SCENE_WITH_INSTANCE)
        coin = scene.find_node("Coin1")
        assert coin is not None
        assert coin.instance_id == "1_coin"
        assert coin.type == ""  # instanced nodes don't have explicit type


# ─── write_tscn ─────────────────────────────────────────────────────

class TestWriteTscn:

    def test_write_minimal(self):
        scene = Scene(uid="uid://test")
        scene.add_node("Root", "Node2D")
        output = write_tscn(scene)
        assert "[gd_scene" in output
        assert 'name="Root"' in output
        assert 'type="Node2D"' in output

    def test_write_ext_resources(self):
        scene = Scene(uid="uid://test")
        scene.add_ext_resource("Script", "res://player.gd")
        scene.add_node("Root", "Node2D")
        output = write_tscn(scene)
        assert '[ext_resource type="Script" path="res://player.gd"' in output
        assert "load_steps=2" in output

    def test_write_sub_resources(self):
        scene = Scene(uid="uid://test")
        scene.add_sub_resource("RectangleShape2D", {"size": "Vector2(28, 44)"})
        scene.add_node("Root", "Node2D")
        output = write_tscn(scene)
        assert '[sub_resource type="RectangleShape2D"' in output
        assert "size = Vector2(28, 44)" in output

    def test_write_groups(self):
        scene = Scene(uid="uid://test")
        scene.add_node("Root", "Node2D")
        scene.add_node("Coin", "Area2D", parent=".", groups=["collectibles", "keys"])
        output = write_tscn(scene)
        assert 'groups=["collectibles", "keys"]' in output

    def test_write_connections(self):
        scene = Scene(uid="uid://test")
        scene.add_node("Root", "Node2D")
        scene.connections.append(Connection("pressed", "Button", ".", "_on_pressed"))
        output = write_tscn(scene)
        assert '[connection signal="pressed" from="Button" to="." method="_on_pressed"]' in output


# ─── Round-trip tests ────────────────────────────────────────────────

class TestRoundTrip:
    """The most critical tests: parse → write → parse must preserve all data."""

    def _roundtrip(self, content: str) -> Scene:
        """Parse, write, re-parse and verify structural equivalence."""
        original = parse_tscn(content)
        written = write_tscn(original)
        reparsed = parse_tscn(written)
        return reparsed

    def test_roundtrip_minimal(self):
        reparsed = self._roundtrip(MINIMAL_SCENE)
        assert len(reparsed.nodes) == 1
        assert reparsed.get_root().name == "Root"
        assert reparsed.get_root().type == "Node2D"

    def test_roundtrip_ext_resources(self):
        reparsed = self._roundtrip(SCENE_WITH_EXT_RESOURCES)
        assert len(reparsed.ext_resources) == 2
        assert reparsed.ext_resources[0].path == "res://player.gd"
        assert reparsed.ext_resources[1].path == "res://icon.png"

    def test_roundtrip_sub_resources(self):
        reparsed = self._roundtrip(SCENE_WITH_SUB_RESOURCES)
        assert len(reparsed.sub_resources) == 1
        assert reparsed.sub_resources[0].properties["size"] == "Vector2(28, 44)"

    def test_roundtrip_groups(self):
        """Critical: groups were previously lost due to lazy regex."""
        reparsed = self._roundtrip(SCENE_WITH_GROUPS)
        coin = reparsed.find_node("Coin")
        assert coin.groups == ["collectibles", "interactable"]
        key = reparsed.find_node("Key")
        assert key.groups == ["keys"]

    def test_roundtrip_connections(self):
        reparsed = self._roundtrip(SCENE_WITH_CONNECTIONS)
        assert len(reparsed.connections) == 2
        assert reparsed.connections[0].signal_name == "pressed"
        assert reparsed.connections[1].method == "_on_mouse_enter"

    def test_roundtrip_instance(self):
        reparsed = self._roundtrip(SCENE_WITH_INSTANCE)
        coin = reparsed.find_node("Coin1")
        assert coin.instance_id == "1_coin"

    def test_roundtrip_node_properties(self):
        reparsed = self._roundtrip(SCENE_WITH_EXT_RESOURCES)
        player = reparsed.find_node("Player")
        assert 'ExtResource("1_abc")' in player.properties["script"]

    def test_roundtrip_preserves_node_count(self):
        """Every node must survive the round-trip."""
        for content in [
            MINIMAL_SCENE,
            SCENE_WITH_EXT_RESOURCES,
            SCENE_WITH_SUB_RESOURCES,
            SCENE_WITH_GROUPS,
            SCENE_WITH_CONNECTIONS,
            SCENE_WITH_INSTANCE,
        ]:
            original = parse_tscn(content)
            reparsed = self._roundtrip(content)
            assert len(reparsed.nodes) == len(original.nodes), \
                f"Node count mismatch after roundtrip"

    def test_roundtrip_complex_scene(self):
        """A scene with every feature combined."""
        content = """\
[gd_scene load_steps=4 format=3 uid="uid://complex"]

[ext_resource type="Script" path="res://main.gd" id="1_scr"]
[ext_resource type="Texture2D" path="res://icon.png" id="2_tex"]

[sub_resource type="CircleShape2D" id="SubResource_1"]
radius = 32.0

[node name="World" type="Node2D"]
script = ExtResource("1_scr")

[node name="Player" type="CharacterBody2D" parent="." groups=["players"]]

[node name="Collision" type="CollisionShape2D" parent="Player"]
shape = SubResource("SubResource_1")

[node name="Sprite" type="Sprite2D" parent="Player"]
texture = ExtResource("2_tex")
position = Vector2(0, -16)

[node name="Enemy" type="Area2D" parent="." groups=["enemies", "damageable"]]

[connection signal="body_entered" from="Enemy" to="." method="_on_enemy_hit"]
"""
        reparsed = self._roundtrip(content)
        assert len(reparsed.nodes) == 5
        assert len(reparsed.ext_resources) == 2
        assert len(reparsed.sub_resources) == 1
        assert len(reparsed.connections) == 1
        player = reparsed.find_node("Player")
        assert player.groups == ["players"]
        enemy = reparsed.find_node("Enemy")
        assert enemy.groups == ["enemies", "damageable"]
        sprite = reparsed.find_node("Sprite")
        assert sprite.properties["position"] == "Vector2(0, -16)"


# ─── Scene helper methods ───────────────────────────────────────────

class TestSceneHelpers:

    def test_add_ext_resource_deduplicates(self):
        scene = Scene()
        r1 = scene.add_ext_resource("Script", "res://player.gd")
        r2 = scene.add_ext_resource("Script", "res://player.gd")
        assert r1.id == r2.id
        assert len(scene.ext_resources) == 1

    def test_find_node(self):
        scene = parse_tscn(SCENE_WITH_EXT_RESOURCES)
        assert scene.find_node("Player") is not None
        assert scene.find_node("Nonexistent") is None

    def test_get_root(self):
        scene = parse_tscn(SCENE_WITH_EXT_RESOURCES)
        root = scene.get_root()
        assert root.name == "Main"
        assert root.parent is None

    def test_to_dict(self):
        scene = parse_tscn(SCENE_WITH_EXT_RESOURCES)
        d = scene.to_dict()
        assert d["name"] == "Main"
        assert "children" in d

    def test_get_node_path(self):
        scene = Scene()
        root = scene.add_node("Root", "Node2D")
        child = scene.add_node("Child", "Sprite2D", parent=".")
        deep = scene.add_node("Deep", "Node", parent="Child")
        assert scene.get_node_path(root) == "Root"
        assert scene.get_node_path(child) == "Child"
        assert scene.get_node_path(deep) == "Child/Deep"


# ─── Body type constants ────────────────────────────────────────────

class TestBodyTypes:

    def test_2d_body_types(self):
        expected = {"Area2D", "CharacterBody2D", "StaticBody2D", "RigidBody2D", "AnimatableBody2D"}
        assert BODY_TYPES_2D == expected

    def test_3d_body_types(self):
        expected = {"Area3D", "CharacterBody3D", "StaticBody3D", "RigidBody3D", "AnimatableBody3D"}
        assert BODY_TYPES_3D == expected

    def test_body_types_is_union(self):
        assert BODY_TYPES == BODY_TYPES_2D | BODY_TYPES_3D
