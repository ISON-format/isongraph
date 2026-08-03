"""
Tests for ison_graph.structural
===============================

ProtectedGraph stops user properties from shadowing structural fields -
a node's (type, id), an edge's (rel_type, source, target, key) - and hands
properties out as read-only views so the only route to changing them is the
validating update_*_properties() methods.

Also covers composition with MultiGraph, which is the configuration
ISON-Cache needs: parallel edges plus a round-trip-safe identity.
"""

import json

import pytest

from ison_graph import ISONGraph
from ison_graph.multigraph import MultiGraph
from ison_graph.structural import (
    EDGE_RESERVED,
    NODE_RESERVED,
    ProtectedGraph,
    ReservedFieldError,
)


class SafeMultiGraph(ProtectedGraph, MultiGraph):
    """Both guarantees at once - the ISON-Cache configuration."""


@pytest.fixture
def g():
    graph = ProtectedGraph()
    graph.add_node("person", 1, name="Alice")
    graph.add_node("person", 2, name="Bob")
    graph.add_edge("KNOWS", ("person", 1), ("person", 2), since=2015)
    return graph


@pytest.fixture
def smg():
    graph = SafeMultiGraph()
    graph.add_node("person", 1, name="Alice")
    graph.add_node("person", 2, name="Bob")
    graph.add_edge("KNOWS", ("person", 1), ("person", 2), since=2015)
    graph.add_edge("KNOWS", ("person", 1), ("person", 2), since=2020)
    return graph


# =============================================================================
# Creation-boundary validation
# =============================================================================

class TestNodeCreation:
    @pytest.mark.parametrize("reserved", sorted(NODE_RESERVED))
    def test_reserved_node_property_is_rejected(self, g, reserved):
        with pytest.raises(ReservedFieldError):
            g.add_node("person", 3, **{reserved: "spoofed"})

    def test_error_names_the_offending_field(self, g):
        with pytest.raises(ReservedFieldError, match="type"):
            g.add_node("person", 3, type="villain")

    def test_error_reports_every_offender(self, g):
        with pytest.raises(ReservedFieldError) as exc:
            g.add_node("person", 3, type="villain", id="spoof")
        assert exc.value.offending == ["id", "type"]

    def test_ordinary_properties_are_accepted(self, g):
        node = g.add_node("person", 3, name="Carol", age=30)
        assert dict(node.properties) == {"name": "Carol", "age": 30}

    def test_rejected_node_is_not_created(self, g):
        with pytest.raises(ReservedFieldError):
            g.add_node("person", 3, type="villain")
        assert g.has_node("person", 3) is False


class TestEdgeCreation:
    @pytest.mark.parametrize("reserved", ["rel_type", "source", "target"])
    def test_reserved_edge_property_cannot_reach_add_edge(self, g, reserved):
        """These three are positional parameters, so Python refuses the call
        before validation ever runs - the property can never land."""
        with pytest.raises(TypeError):
            g.add_edge("LIKES", ("person", 1), ("person", 2), **{reserved: "spoof"})

    def test_ordinary_edge_properties_are_accepted(self, g):
        edge = g.add_edge("LIKES", ("person", 1), ("person", 2), weight=0.5)
        assert dict(edge.properties) == {"weight": 0.5}

    def test_key_is_forwarded_as_structural_on_a_multigraph(self, smg):
        """'key' is reserved as a property but is a real argument on a
        MultiGraph - it must reach add_edge rather than trip validation."""
        assert smg.add_edge("KNOWS", ("person", 1), ("person", 2), key=9).key == 9

    def test_key_on_a_simple_graph_is_rejected(self, g):
        """Nothing would consume it, so it would silently become a property."""
        with pytest.raises(ReservedFieldError):
            g.add_edge("LIKES", ("person", 1), ("person", 2), key=1)


# =============================================================================
# Read-only property views
# =============================================================================

class TestStructuralFieldsAreSealed:
    """A read-only property view is not enough - the structural attributes
    themselves must be final, or an object can report an identity the
    graph's indexes never used."""

    @pytest.mark.parametrize("field,value", [("type", "villain"), ("id", 99)])
    def test_node_identity_cannot_be_reassigned(self, g, field, value):
        node = g.get_node("person", 1)
        with pytest.raises(ReservedFieldError):
            setattr(node, field, value)

    @pytest.mark.parametrize("field", ["rel_type", "source", "target"])
    def test_edge_identity_cannot_be_reassigned(self, g, field):
        edge = g.get_edge("KNOWS", ("person", 1), ("person", 2))
        with pytest.raises(ReservedFieldError):
            setattr(edge, field, "spoofed")

    def test_multigraph_edge_key_cannot_be_reassigned(self, smg):
        edge = smg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        with pytest.raises(ReservedFieldError):
            edge.key = 5

    def test_sealed_objects_still_work_normally(self, g):
        node = g.get_node("person", 1)
        assert (node.type, node.id) == ("person", 1)
        assert node.ref == ("person", 1)
        assert dict(node.properties) == {"name": "Alice"}

    def test_graph_lookup_stays_consistent_after_a_blocked_mutation(self, g):
        node = g.get_node("person", 1)
        with pytest.raises(ReservedFieldError):
            node.type = "villain"

        assert g.node_types() == ["person"]
        assert g.has_node("person", 1) is True
        assert g.get_node("person", 1).ref == ("person", 1)


class TestInheritedUpdateNode:
    """The inherited mutator writes straight to .properties, so it has to
    be redirected rather than left to fail on a mappingproxy."""

    def test_update_node_works(self, g):
        g.update_node("person", 1, name="Alice Q", age=31)
        assert dict(g.get_node("person", 1).properties) == {"name": "Alice Q", "age": 31}

    def test_update_node_validates_reserved_fields(self, g):
        with pytest.raises(ReservedFieldError):
            g.update_node("person", 1, type="villain")

    def test_update_node_works_on_a_multigraph(self, smg):
        smg.update_node("person", 1, name="Alice Q")
        assert smg.get_node("person", 1).properties["name"] == "Alice Q"


class TestReadOnlyProperties:
    def test_node_properties_cannot_be_assigned(self, g):
        with pytest.raises(TypeError):
            g.get_node("person", 1).properties["name"] = "Mallory"

    def test_node_properties_cannot_be_deleted(self, g):
        with pytest.raises(TypeError):
            del g.get_node("person", 1).properties["name"]

    def test_edge_properties_cannot_be_assigned(self, g):
        with pytest.raises(TypeError):
            g.get_edge("KNOWS", ("person", 1), ("person", 2)).properties["since"] = 1999

    def test_the_view_is_shallow_by_contract(self, g):
        """Documented limit: names are protected, nested values are not.
        Pinned so a future change to the contract is a deliberate one."""
        g.add_node("person", 3, meta={"active": True})
        g.get_node("person", 3).properties["meta"]["active"] = False
        assert g.get_node("person", 3).properties["meta"] == {"active": False}

    def test_properties_still_read_normally(self, g):
        node = g.get_node("person", 1)
        assert node.properties["name"] == "Alice"
        assert dict(node.properties) == {"name": "Alice"}
        assert "name" in node.properties


# =============================================================================
# Updates
# =============================================================================

class TestUpdates:
    def test_update_node_properties_merges(self, g):
        g.update_node_properties(("person", 1), name="Alice Q", age=31)
        assert dict(g.get_node("person", 1).properties) == {"name": "Alice Q", "age": 31}

    def test_update_is_visible_through_the_read_only_view(self, g):
        view = g.get_node("person", 1).properties
        g.update_node_properties(("person", 1), age=31)
        assert view["age"] == 31

    @pytest.mark.parametrize("reserved", sorted(NODE_RESERVED))
    def test_update_node_rejects_reserved_fields(self, g, reserved):
        with pytest.raises(ReservedFieldError):
            g.update_node_properties(("person", 1), **{reserved: "spoofed"})

    def test_update_edge_properties_merges(self, g):
        g.update_edge_properties("KNOWS", ("person", 1), ("person", 2), since=2016)
        assert g.get_edge("KNOWS", ("person", 1), ("person", 2)).properties["since"] == 2016

    @pytest.mark.parametrize("reserved", ["rel_type", "source", "target"])
    def test_update_edge_reserved_fields_cannot_reach_properties(self, g, reserved):
        with pytest.raises(TypeError):
            g.update_edge_properties(
                "KNOWS", ("person", 1), ("person", 2), **{reserved: "spoofed"}
            )

    def test_update_edge_targets_one_parallel_edge(self, smg):
        smg.update_edge_properties("KNOWS", ("person", 1), ("person", 2), key=1, since=2021)
        assert [
            e.properties["since"]
            for _, e in smg.edges_between(("person", 1), ("person", 2))
        ] == [2015, 2021]

    def test_structural_fields_survive_a_rejected_update(self, g):
        with pytest.raises(ReservedFieldError):
            g.update_node_properties(("person", 1), type="villain")
        node = g.get_node("person", 1)
        assert (node.type, node.id) == ("person", 1)


# =============================================================================
# Round-trip contract - identity must survive serialization
# =============================================================================

class TestRoundTrip:
    def test_to_dict_is_json_serializable(self, g):
        assert json.loads(json.dumps(g.to_dict()))["nodes"][0]["type"] == "person"

    def test_ison_roundtrip_preserves_identity(self, g):
        restored = ProtectedGraph.from_ison(g.to_ison())
        assert restored.get_node("person", 1).type == "person"
        assert restored.to_ison() == g.to_ison()

    def test_roundtrip_properties_stay_read_only(self, g):
        restored = ProtectedGraph.from_ison(g.to_ison())
        with pytest.raises(TypeError):
            restored.get_node("person", 1).properties["name"] = "Mallory"

    def test_dict_roundtrip_preserves_identity(self, g):
        restored = ProtectedGraph.from_dict(g.to_dict())
        assert restored.node_count() == 2
        assert restored.get_node("person", 2).properties["name"] == "Bob"

    @pytest.mark.parametrize("reserved", sorted(EDGE_RESERVED))
    def test_from_dict_rejects_reserved_edge_properties(self, reserved):
        """The path that matters: reserved names arrive in a payload's
        property dict, where the add_edge signature cannot screen them."""
        payload = {
            "nodes": [{"type": "person", "id": 1}, {"type": "person", "id": 2}],
            "edges": [{
                "rel_type": "KNOWS",
                "source": {"type": "person", "id": 1},
                "target": {"type": "person", "id": 2},
                "properties": {reserved: "spoofed"},
            }],
        }
        with pytest.raises(ReservedFieldError, match=reserved):
            ProtectedGraph.from_dict(payload)

    def test_from_dict_accepts_ordinary_edge_properties(self):
        payload = {
            "nodes": [{"type": "person", "id": 1}, {"type": "person", "id": 2}],
            "edges": [{
                "rel_type": "KNOWS",
                "source": {"type": "person", "id": 1},
                "target": {"type": "person", "id": 2},
                "properties": {"since": 2015},
            }],
        }
        graph = ProtectedGraph.from_dict(payload)
        assert graph.get_edge("KNOWS", ("person", 1), ("person", 2)).properties["since"] == 2015

    def test_type_property_cannot_hijack_a_node_on_reload(self):
        """The hole ProtectedGraph closes: on a plain ISONGraph a 'type'
        property round-trips into the node's real type."""
        plain = ISONGraph()
        plain.add_node("person", 1, type="villain")
        assert ISONGraph.from_dict(plain.to_dict()).node_types() == ["villain"]

        with pytest.raises(ReservedFieldError):
            ProtectedGraph().add_node("person", 1, type="villain")


# =============================================================================
# Composition with MultiGraph
# =============================================================================

class TestSafeMultiGraph:
    def test_parallel_edges_are_allowed(self, smg):
        assert smg.edge_count() == 2

    def test_field_protection_still_applies(self, smg):
        with pytest.raises(ReservedFieldError):
            smg.add_node("person", 3, type="villain")

    def test_carries_the_multigraph_format_marker(self, smg):
        assert smg.to_dict()["format"] == "ison-graph-multigraph-v1"

    def test_to_dict_is_json_serializable(self, smg):
        assert len(json.loads(json.dumps(smg.to_dict()))["edges"]) == 2

    def test_roundtrip_preserves_keys_and_protection(self, smg):
        restored = SafeMultiGraph.from_ison(smg.to_ison())
        assert [k for k, _ in restored.edges_between(("person", 1), ("person", 2))] == [0, 1]
        with pytest.raises(TypeError):
            restored.get_node("person", 1).properties["name"] = "Mallory"

    def test_serialization_is_canonical(self):
        a = SafeMultiGraph()
        a.add_node("z", 1)
        a.add_node("a", 1)
        a.add_edge("K", ("z", 1), ("a", 1), key=1)
        a.add_edge("K", ("z", 1), ("a", 1), key=0)

        b = SafeMultiGraph()
        b.add_node("a", 1)
        b.add_node("z", 1)
        b.add_edge("K", ("z", 1), ("a", 1), key=0)
        b.add_edge("K", ("z", 1), ("a", 1), key=1)

        assert a.to_ison() == b.to_ison()


class TestSimpleGraphUnaffected:
    def test_isongraph_still_accepts_type_as_a_property(self):
        """ProtectedGraph is opt-in - core behavior is unchanged."""
        g = ISONGraph()
        node = g.add_node("person", 1, type="villain")
        assert node.properties["type"] == "villain"
        assert node.type == "person"

    def test_isongraph_properties_stay_mutable(self):
        g = ISONGraph()
        g.add_node("person", 1, name="Alice")
        g.get_node("person", 1).properties["name"] = "Mallory"
        assert g.get_node("person", 1).properties["name"] == "Mallory"
