"""
ProtectedGraph - structural fields cannot be shadowed by user properties.

A node's identity is ``(type, id)``; an edge's is
``(rel_type, source, target[, key])``. In a plain ``ISONGraph`` nothing
stops a property of the same name from riding along - ``add_node('person',
1, type='villain')`` is accepted, and after a ``to_dict()`` round trip the
property overwrites the real type. ``ProtectedGraph`` closes that hole:

    from ison_graph.structural import ProtectedGraph

    g = ProtectedGraph()
    g.add_node('person', 1, name='Alice')

    g.add_node('person', 2, type='villain')   # ReservedFieldError
    g.update_node_properties(('person', 1), name='Alice Q')   # fine

Properties are handed out as read-only mappings, so the only way to change
them is ``update_node_properties()`` / ``update_edge_properties()``, both
of which validate.

Compose with MultiGraph for both guarantees:

    from ison_graph.multigraph import MultiGraph

    class SafeMultiGraph(ProtectedGraph, MultiGraph):
        pass

Experimental in 1.3.0.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional, cast

from . import Edge, GraphError, ISONGraph, Node, NodeRef

#: Property names a node may not carry - they would shadow its identity.
NODE_RESERVED = frozenset({"type", "id"})

#: Property names an edge may not carry.
EDGE_RESERVED = frozenset({"rel_type", "source", "target", "key"})

_MISSING = object()


class ReservedFieldError(GraphError):
    """A property collided with a structural field."""

    def __init__(self, context: str, offending: Iterable[str], reserved: Iterable[str]):
        self.offending = sorted(offending)
        self.reserved = sorted(reserved)
        super().__init__(
            f"{context}: {self.offending} cannot be used as propert"
            f"{'y' if len(self.offending) == 1 else 'ies'} - reserved for "
            f"structural fields {self.reserved}."
        )


def _reject_reserved(properties: Mapping[str, Any], reserved: frozenset, context: str) -> None:
    clash = reserved & set(properties)
    if clash:
        raise ReservedFieldError(context, clash, reserved)


_SEALED_TYPES: Dict[type, type] = {}


def _sealed_type(cls: type, reserved: frozenset) -> type:
    """Build (once per class) a subtype whose structural fields are final.

    Sealing has to happen on the instance's type rather than the graph,
    because ``node.type = 'other'`` bypasses the graph entirely and would
    leave the object reporting an identity the indexes do not use.
    """
    if cls not in _SEALED_TYPES:
        def __setattr__(self: Any, name: str, value: Any) -> None:
            if name in reserved and getattr(self, "_sealed", False):
                raise ReservedFieldError(
                    f"{cls.__name__}.{name} is structural and final", [name], reserved
                )
            object.__setattr__(self, name, value)

        _SEALED_TYPES[cls] = type(f"Sealed{cls.__name__}", (cls,), {
            "__setattr__": __setattr__,
            "__doc__": f"{cls.__name__} with structural fields sealed after creation.",
        })
    return _SEALED_TYPES[cls]


def _seal(obj: Any, properties: Dict[str, Any], reserved: frozenset) -> None:
    """Freeze an object's structural fields and hand out a read-only
    view of its properties.

    The property view is *shallow*: it blocks rebinding and deletion of
    top-level keys, but a mutable value stored under one (a dict, a list)
    can still be changed in place. Protecting names, not deep values, is
    the contract - copy defensively if you need more.
    """
    obj.__class__ = _sealed_type(type(obj), reserved)
    obj._props = properties
    obj.properties = MappingProxyType(properties)
    obj._sealed = True


class ProtectedGraph(ISONGraph):
    """Graph that refuses properties shadowing structural fields.

    Written as a mixin over ``ISONGraph`` so it composes left-of any other
    graph class in the same hierarchy - ``class SafeMultiGraph(ProtectedGraph,
    MultiGraph)`` validates, then defers to MultiGraph for storage.
    """

    def add_node(self, node_type: str, node_id: Any, **properties: Any) -> Node:
        _reject_reserved(properties, NODE_RESERVED, "add_node")
        node = super().add_node(node_type, node_id, **properties)
        _seal(node, dict(properties), NODE_RESERVED)
        return node

    def update_node(self, node_type: str, node_id: Any, **properties: Any) -> Node:
        """Merge properties into a node.

        Overridden because the inherited version writes straight to
        ``node.properties``, which is a read-only view here - calling it
        would fail with an AttributeError about mappingproxy rather than
        doing the job or naming the problem.
        """
        return self.update_node_properties((node_type, node_id), **properties)

    def add_edge(self, rel_type: str, source: NodeRef, target: NodeRef, **properties: Any) -> Edge:
        # 'key' is structural on a MultiGraph, so it is forwarded there
        # rather than validated as a property. On a simple graph nothing
        # would consume it and it would silently become a property, so it
        # is rejected like any other reserved name.
        key = properties.pop("key", _MISSING)
        _reject_reserved(properties, EDGE_RESERVED, "add_edge")

        if key is _MISSING:
            edge = super().add_edge(rel_type, source, target, **properties)
        elif getattr(self, "_supports_edge_keys", False):
            edge = super().add_edge(rel_type, source, target, key=key, **properties)
        else:
            raise ReservedFieldError("add_edge", ["key"], EDGE_RESERVED)

        _seal(edge, dict(properties), EDGE_RESERVED)
        return edge

    @classmethod
    def from_dict(cls, data: Dict[str, Any], name: Optional[str] = None) -> "ProtectedGraph":
        """Parse a graph, refusing payloads whose edge properties collide
        with structural fields.

        Validated up front because ``rel_type``/``source``/``target`` are
        positional parameters of ``add_edge`` - reaching it with those in a
        property dict raises an opaque TypeError instead of naming the
        problem.
        """
        for edge_data in data.get("edges", []):
            _reject_reserved(
                edge_data.get("properties", {}), EDGE_RESERVED, "from_dict edge properties"
            )
        return cast("ProtectedGraph", super().from_dict(data, name))

    def update_node_properties(self, node_ref: NodeRef, **updates: Any) -> Node:
        """Merge properties into a node.

        The only supported way to change them - ``node.properties`` is a
        read-only view.
        """
        _reject_reserved(updates, NODE_RESERVED, "update_node_properties")
        node = self.get_node(node_ref[0], node_ref[1])
        # _props is attached by _seal(); .properties is a read-only view of it.
        cast(Any, node)._props.update(updates)
        return node

    def update_edge_properties(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        key: Optional[int] = None,
        **updates: Any,
    ) -> Edge:
        """Merge properties into an edge.

        ``key`` selects one parallel edge on a MultiGraph; leave it off on
        a simple graph.
        """
        _reject_reserved(updates, EDGE_RESERVED, "update_edge_properties")
        if key is None:
            edge = self.get_edge(rel_type, source, target)
        else:
            # 'key' only exists on a MultiGraph base; see _supports_edge_keys.
            edge = cast(Any, self).get_edge(rel_type, source, target, key=key)
        cast(Any, edge)._props.update(updates)
        return edge

    def to_dict(self) -> Dict[str, Any]:
        """Serialize, unwrapping the read-only views into plain dicts."""
        data = super().to_dict()
        for edge in data.get("edges", []):
            if isinstance(edge.get("properties"), MappingProxyType):
                edge["properties"] = dict(edge["properties"])
        return data


__all__ = [
    "ProtectedGraph",
    "ReservedFieldError",
    "NODE_RESERVED",
    "EDGE_RESERVED",
]
