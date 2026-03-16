"""Tests for config auto-quoting and config command.

Covers the _auto_quote_config_value function that prevents
Godot parse errors from unquoted string values (P0 #3).
"""

import pytest
from playgen.commands.config_cmd import _auto_quote_config_value


class TestAutoQuoteConfigValue:

    # Should NOT be quoted
    @pytest.mark.parametrize("value", [
        "42", "-7", "3.14", "-0.5", "0",
        "0xFF", "0x0A",
        "true", "false", "null",
    ])
    def test_no_quote_numbers_and_keywords(self, value):
        assert _auto_quote_config_value(value) == value

    @pytest.mark.parametrize("value", [
        'Vector2(100, 200)',
        'Vector3(1, 2, 3)',
        'Color(1, 0, 0, 1)',
        'Rect2(0, 0, 100, 200)',
        'Transform2D(1, 0, 0, 1, 0, 0)',
    ])
    def test_no_quote_constructors(self, value):
        assert _auto_quote_config_value(value) == value

    @pytest.mark.parametrize("value", [
        'PackedStringArray("4.3", "GL Compatibility")',
        'PackedVector2Array()',
        'PackedFloat32Array(1.0, 2.0)',
    ])
    def test_no_quote_packed_arrays(self, value):
        assert _auto_quote_config_value(value) == value

    def test_no_quote_already_quoted(self):
        assert _auto_quote_config_value('"My Game"') == '"My Game"'

    def test_no_quote_arrays(self):
        assert _auto_quote_config_value('[1, 2, 3]') == '[1, 2, 3]'

    def test_no_quote_dicts(self):
        assert _auto_quote_config_value('{"key": "val"}') == '{"key": "val"}'

    def test_no_quote_stringname(self):
        assert _auto_quote_config_value('&"my_signal"') == '&"my_signal"'

    def test_no_quote_nodepath(self):
        assert _auto_quote_config_value('^"Player"') == '^"Player"'

    def test_no_quote_subresource(self):
        assert _auto_quote_config_value('SubResource("1")') == 'SubResource("1")'

    def test_no_quote_extresource(self):
        assert _auto_quote_config_value('ExtResource("1_abc")') == 'ExtResource("1_abc")'

    # SHOULD be quoted
    @pytest.mark.parametrize("value,expected", [
        ("My Game", '"My Game"'),
        ("DungeonFood MVP", '"DungeonFood MVP"'),
        ("gl_compatibility", '"gl_compatibility"'),
        ("canvas_items", '"canvas_items"'),
        ("res://main.tscn", '"res://main.tscn"'),
        ("forward_plus", '"forward_plus"'),
        ("mobile", '"mobile"'),
    ])
    def test_quote_plain_strings(self, value, expected):
        assert _auto_quote_config_value(value) == expected

    def test_does_not_double_quote(self):
        result = _auto_quote_config_value('"already quoted"')
        assert result == '"already quoted"'
        assert result.count('"') == 2

    def test_real_world_config_name(self):
        """The exact case that caused P0 #3."""
        result = _auto_quote_config_value("DungeonFood MVP")
        assert result == '"DungeonFood MVP"'

    def test_real_world_renderer(self):
        result = _auto_quote_config_value("gl_compatibility")
        assert result == '"gl_compatibility"'

    def test_real_world_stretch_mode(self):
        result = _auto_quote_config_value("canvas_items")
        assert result == '"canvas_items"'
