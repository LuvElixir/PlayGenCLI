"""Godot .tscn (Text Scene) file parser and writer.

Handles Godot 4.x format=3 scene files. These are text-based and fully
parseable, containing sections for external resources, sub-resources,
nodes, and signal connections.
"""

from __future__ import annotations

import re
import random
import string
from dataclasses import dataclass, field


def _gen_id() -> str:
    num = random.randint(1, 99)
    chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"{num}_{chars}"


def _gen_uid() -> str:
    chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=13))
    return f"uid://{chars}"


@dataclass
class ExtResource:
    type: str
    path: str
    id: str = field(default_factory=_gen_id)


@dataclass
class SubResource:
    type: str
    id: str = field(default_factory=lambda: f"SubResource_{random.randint(1, 9999)}")
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class SceneNode:
    name: str
    type: str = ""
    parent: str | None = None  # None = root, "." = direct child, "A/B" = deeper
    properties: dict[str, str] = field(default_factory=dict)
    instance_id: str | None = None
    groups: list[str] = field(default_factory=list)


@dataclass
class Connection:
    signal_name: str
    from_node: str
    to_node: str
    method: str


@dataclass
class Scene:
    uid: str = field(default_factory=_gen_uid)
    ext_resources: list[ExtResource] = field(default_factory=list)
    sub_resources: list[SubResource] = field(default_factory=list)
    nodes: list[SceneNode] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)

    def add_ext_resource(self, type: str, path: str) -> ExtResource:
        for r in self.ext_resources:
            if r.path == path:
                return r
        res = ExtResource(type=type, path=path)
        self.ext_resources.append(res)
        return res

    def add_sub_resource(self, type: str, properties: dict[str, str] | None = None) -> SubResource:
        res = SubResource(type=type, properties=properties or {})
        self.sub_resources.append(res)
        return res

    def add_node(
        self,
        name: str,
        type: str,
        parent: str | None = None,
        properties: dict[str, str] | None = None,
        groups: list[str] | None = None,
    ) -> SceneNode:
        node = SceneNode(name=name, type=type, parent=parent, properties=properties or {}, groups=groups or [])
        self.nodes.append(node)
        return node

    def get_root(self) -> SceneNode | None:
        for n in self.nodes:
            if n.parent is None:
                return n
        return None

    def find_node(self, name: str) -> SceneNode | None:
        for n in self.nodes:
            if n.name == name:
                return n
        return None

    def get_node_path(self, node: SceneNode) -> str:
        if node.parent is None:
            return node.name
        if node.parent == ".":
            return node.name
        return f"{node.parent}/{node.name}"

    def get_children(self, node_name: str) -> list[SceneNode]:
        root = self.get_root()
        if root and root.name == node_name:
            return [n for n in self.nodes if n.parent == "."]
        return [n for n in self.nodes if n.parent and n.parent.rsplit("/", 1)[-1] == node_name]

    def to_dict(self) -> dict:
        def _build_tree(node: SceneNode) -> dict:
            path = self.get_node_path(node)
            children = []
            for n in self.nodes:
                if n.parent is None:
                    continue
                if n.parent == "." and node.parent is None:
                    children.append(_build_tree(n))
                elif n.parent == path:
                    children.append(_build_tree(n))
            result: dict = {"name": node.name, "type": node.type}
            if node.groups:
                result["groups"] = node.groups
            if node.properties:
                result["properties"] = node.properties
            if children:
                result["children"] = children
            return result

        root = self.get_root()
        return _build_tree(root) if root else {}


# Types that need a CollisionShape child when --shape is used
BODY_TYPES_2D = {"Area2D", "CharacterBody2D", "StaticBody2D", "RigidBody2D", "AnimatableBody2D"}
BODY_TYPES_3D = {"Area3D", "CharacterBody3D", "StaticBody3D", "RigidBody3D", "AnimatableBody3D"}
BODY_TYPES = BODY_TYPES_2D | BODY_TYPES_3D

# Patterns that should NOT be quoted (Godot type constructors, numbers, etc.)
_NO_QUOTE_RES = [
    re.compile(r"^-?\d+(\.\d+)?$"),                     # Numbers
    re.compile(r"^0x[0-9a-fA-F]+$"),                     # Hex
    re.compile(r"^(true|false|null|inf|nan|-inf)$"),      # Keywords
    re.compile(r"^(Vector[234i]?|Color|Rect2i?|Transform[23]D|Basis|Quaternion|Plane|AABB|Projection)\("),
    re.compile(r"^Packed(String|Vector[23]|Int[36][24]|Float[36][24]|Byte|Color)Array\("),
    re.compile(r"^(ExtResource|SubResource)\("),
    re.compile(r"^(Array|Dictionary)\("),
    re.compile(r'^&"'),                                   # StringName
    re.compile(r'^\^"'),                                  # NodePath
    re.compile(r'^".*"$'),                                # Already quoted
]


def auto_quote_value(value: str) -> str:
    """Auto-quote a tscn property value if it looks like a plain string.

    Numbers, booleans, Godot constructors (Vector2, Color, etc.), and
    resource references are left as-is. Everything else gets quoted.
    """
    for pattern in _NO_QUOTE_RES:
        if pattern.match(value):
            return value
    return f'"{value}"'


_HEADER_RE = re.compile(r"\[gd_scene\s+(.*?)\]")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_EXT_RE = re.compile(r"\[ext_resource\s+(.*?)\]")
_SUB_RE = re.compile(r"\[sub_resource\s+(.*?)\]")
_NODE_RE = re.compile(r"\[node\s+(.*)\]")
_CONN_RE = re.compile(r"\[connection\s+(.*?)\]")
_INSTANCE_RE = re.compile(r'instance=ExtResource\("([^"]*)"\)')
_GROUPS_RE = re.compile(r'groups=\[([^\]]*)\]')
_KV_RE = re.compile(r"^([A-Za-z_]\w*(?:/\w+)*)\s*=\s*(.*)")


def _parse_attrs(text: str) -> dict[str, str]:
    return dict(_ATTR_RE.findall(text))


def parse_tscn(content: str) -> Scene:
    scene = Scene()
    lines = content.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith(";"):
            i += 1
            continue

        # Header
        m = _HEADER_RE.match(stripped)
        if m:
            attrs = _parse_attrs(m.group(1))
            if "uid" in attrs:
                scene.uid = attrs["uid"]
            i += 1
            continue

        # External resource
        m = _EXT_RE.match(stripped)
        if m:
            attrs = _parse_attrs(m.group(1))
            scene.ext_resources.append(
                ExtResource(
                    type=attrs.get("type", ""),
                    path=attrs.get("path", ""),
                    id=attrs.get("id", _gen_id()),
                )
            )
            i += 1
            continue

        # Sub resource
        m = _SUB_RE.match(stripped)
        if m:
            attrs = _parse_attrs(m.group(1))
            props: dict[str, str] = {}
            i += 1
            while i < n:
                pl = lines[i].strip()
                if not pl or pl.startswith("["):
                    break
                kv = _KV_RE.match(pl)
                if kv:
                    props[kv.group(1)] = kv.group(2)
                i += 1
            scene.sub_resources.append(
                SubResource(
                    type=attrs.get("type", ""),
                    id=attrs.get("id", ""),
                    properties=props,
                )
            )
            continue

        # Node
        m = _NODE_RE.match(stripped)
        if m:
            raw = m.group(1)
            attrs = _parse_attrs(raw)
            inst_m = _INSTANCE_RE.search(raw)
            groups_m = _GROUPS_RE.search(raw)
            groups = re.findall(r'"([^"]*)"', groups_m.group(1)) if groups_m else []
            props = {}
            i += 1
            while i < n:
                pl = lines[i].strip()
                if not pl or pl.startswith("["):
                    break
                kv = _KV_RE.match(pl)
                if kv:
                    props[kv.group(1)] = kv.group(2)
                i += 1
            scene.nodes.append(
                SceneNode(
                    name=attrs.get("name", "Unknown"),
                    type=attrs.get("type", ""),
                    parent=attrs.get("parent"),
                    properties=props,
                    instance_id=inst_m.group(1) if inst_m else None,
                    groups=groups,
                )
            )
            continue

        # Connection
        m = _CONN_RE.match(stripped)
        if m:
            attrs = _parse_attrs(m.group(1))
            scene.connections.append(
                Connection(
                    signal_name=attrs.get("signal", ""),
                    from_node=attrs.get("from", ""),
                    to_node=attrs.get("to", ""),
                    method=attrs.get("method", ""),
                )
            )
            i += 1
            continue

        i += 1

    return scene


def write_tscn(scene: Scene) -> str:
    lines: list[str] = []

    # Header
    total = len(scene.ext_resources) + len(scene.sub_resources)
    parts = []
    if total > 0:
        parts.append(f"load_steps={total + 1}")
    parts.append("format=3")
    parts.append(f'uid="{scene.uid}"')
    lines.append(f'[gd_scene {" ".join(parts)}]')
    lines.append("")

    # External resources
    for r in scene.ext_resources:
        lines.append(f'[ext_resource type="{r.type}" path="{r.path}" id="{r.id}"]')
    if scene.ext_resources:
        lines.append("")

    # Sub resources
    for r in scene.sub_resources:
        lines.append(f'[sub_resource type="{r.type}" id="{r.id}"]')
        for k, v in r.properties.items():
            lines.append(f"{k} = {v}")
        lines.append("")

    # Nodes
    for nd in scene.nodes:
        p = [f'name="{nd.name}"']
        if nd.type:
            p.append(f'type="{nd.type}"')
        if nd.parent is not None:
            p.append(f'parent="{nd.parent}"')
        if nd.instance_id:
            p.append(f'instance=ExtResource("{nd.instance_id}")')
        if nd.groups:
            groups_str = ", ".join(f'"{g}"' for g in nd.groups)
            p.append(f"groups=[{groups_str}]")
        lines.append(f'[node {" ".join(p)}]')
        for k, v in nd.properties.items():
            lines.append(f"{k} = {v}")
        lines.append("")

    # Connections
    for c in scene.connections:
        lines.append(
            f'[connection signal="{c.signal_name}" from="{c.from_node}" '
            f'to="{c.to_node}" method="{c.method}"]'
        )
    if scene.connections:
        lines.append("")

    return "\n".join(lines)
