"""
Tests for schema-generator
===========================

Covers DataAnalyzer (type/pattern/enum inference over raw JSON graph
data), SchemaGenerator (turning that analysis into a GraphSchema), and
SchemaFormatter (rendering a GraphSchema to Python/TypeScript/JSON/ISON).
"""

import pytest

from schema_generator.analyzer import DataAnalyzer
from schema_generator.generator import SchemaGenerator, GraphSchema, generate_schema
from schema_generator.formatter import SchemaFormatter


@pytest.fixture
def sample_data():
    """A small JSON graph mixing required/optional fields, numbers,
    booleans, and a low-cardinality field that should read as an enum.

    is_enum requires count > 3 and unique_values < min(10, count * 0.5),
    so this needs 5 people to trigger it with 2 distinct tiers.
    """
    return {
        "nodes": [
            {"type": "person", "id": "1", "name": "Alice", "age": 30,
             "active": True, "tier": "gold", "email": "alice@example.com"},
            {"type": "person", "id": "2", "name": "Bob", "age": 25,
             "active": True, "tier": "silver", "email": "bob@example.com"},
            {"type": "person", "id": "3", "name": "Carol", "age": 35,
             "active": False, "tier": "gold", "email": None},
            {"type": "person", "id": "4", "name": "Dave", "age": 28,
             "active": True, "tier": "silver", "email": "dave@example.com"},
            {"type": "person", "id": "5", "name": "Eve", "age": 32,
             "active": False, "tier": "gold", "email": "eve@example.com"},
        ],
        "edges": [
            {"rel_type": "KNOWS",
             "source": {"type": "person", "id": "1"},
             "target": {"type": "person", "id": "2"},
             "properties": {"since": 2020}},
            {"rel_type": "KNOWS",
             "source": {"type": "person", "id": "2"},
             "target": {"type": "person", "id": "3"},
             "properties": {"since": 2021}},
        ],
    }


@pytest.fixture
def empty_data():
    return {"nodes": [], "edges": []}


# =============================================================================
# DataAnalyzer Tests
# =============================================================================

class TestDataAnalyzer:
    def test_analyze_counts_node_and_edge_types(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        summary = analyzer.summary()
        assert summary["node_types"] == 1
        assert summary["edge_types"] == 1
        assert summary["total_nodes"] == 5
        assert summary["total_edges"] == 2
        assert summary["node_type_names"] == ["person"]
        assert summary["edge_type_names"] == ["KNOWS"]

    def test_field_type_inference(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        fields = analyzer.get_node_stats()["person"].fields
        assert fields["name"].primary_type == "string"
        assert fields["age"].primary_type == "int"
        assert fields["active"].primary_type == "bool"

    def test_required_vs_optional_field(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        fields = analyzer.get_node_stats()["person"].fields
        assert fields["name"].required is True
        assert fields["email"].required is False
        assert fields["email"].null_count == 1

    def test_enum_detection(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        tier = analyzer.get_node_stats()["person"].fields["tier"]
        assert tier.is_enum is True
        assert tier.unique_values == {"gold", "silver"}

    def test_min_max_tracking(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        age = analyzer.get_node_stats()["person"].fields["age"]
        assert age.min_value == 25
        assert age.max_value == 35

    def test_edge_source_target_types(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        knows = analyzer.get_edge_stats()["KNOWS"]
        assert knows.source_types == {"person"}
        assert knows.target_types == {"person"}
        assert knows.count == 2

    def test_edge_property_fields_are_analyzed(self, sample_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(sample_data)

        since = analyzer.get_edge_stats()["KNOWS"].fields["since"]
        assert since.primary_type == "int"
        assert since.min_value == 2020
        assert since.max_value == 2021

    @pytest.mark.parametrize("value,pattern", [
        ("alice@example.com", "email"),
        ("https://example.com", "url"),
        ("2024-01-15", "date"),
        ("2024-01-15T10:30:00", "datetime"),
        ("550e8400-e29b-41d4-a716-446655440000", "uuid"),
    ])
    def test_pattern_detection(self, value, pattern):
        analyzer = DataAnalyzer()
        analyzer.analyze({"nodes": [{"type": "t", "id": "1", "field": value}], "edges": []})

        stats = analyzer.get_node_stats()["t"].fields["field"]
        assert pattern in stats.patterns

    def test_empty_data(self, empty_data):
        analyzer = DataAnalyzer()
        analyzer.analyze(empty_data)

        summary = analyzer.summary()
        assert summary["node_types"] == 0
        assert summary["edge_types"] == 0

    def test_edge_rel_type_falls_back_to_type_key(self):
        analyzer = DataAnalyzer()
        analyzer.analyze({"nodes": [], "edges": [
            {"type": "LEGACY_REL", "source": {"type": "a", "id": "1"}, "target": {"type": "b", "id": "2"}}
        ]})

        assert "LEGACY_REL" in analyzer.get_edge_stats()

    def test_missing_type_defaults_to_entity(self):
        analyzer = DataAnalyzer()
        analyzer.analyze({"nodes": [{"id": "1", "name": "x"}], "edges": []})

        assert "entity" in analyzer.get_node_stats()


# =============================================================================
# SchemaGenerator Tests
# =============================================================================

class TestSchemaGenerator:
    def test_generate_returns_graph_schema(self, sample_data):
        generator = SchemaGenerator()
        schema = generator.generate(sample_data, name="my_schema")

        assert isinstance(schema, GraphSchema)
        assert schema.name == "my_schema"
        assert [nt.name for nt in schema.node_types] == ["person"]
        assert [et.name for et in schema.edge_types] == ["KNOWS"]

    def test_field_constraints_are_populated(self, sample_data):
        generator = SchemaGenerator()
        schema = generator.generate(sample_data)

        person = schema.node_types[0]
        age_field = next(f for f in person.fields if f.name == "age")
        assert age_field.type == "int"
        assert age_field.min_value == 25
        assert age_field.max_value == 35

    def test_no_self_loop_inferred_for_single_type_edge(self, sample_data):
        generator = SchemaGenerator()
        schema = generator.generate(sample_data)

        knows = schema.edge_types[0]
        assert knows.no_self_loop is True

    def test_strict_mode_forces_all_fields_required(self, sample_data):
        generator = SchemaGenerator(strict_mode=True)
        schema = generator.generate(sample_data)

        person = schema.node_types[0]
        email_field = next(f for f in person.fields if f.name == "email")
        assert email_field.required is True

    def test_disable_constraint_inference(self, sample_data):
        generator = SchemaGenerator(infer_constraints=False)
        schema = generator.generate(sample_data)

        age_field = next(f for f in schema.node_types[0].fields if f.name == "age")
        assert age_field.min_value is None
        assert age_field.max_value is None

    def test_disable_enum_inference(self, sample_data):
        generator = SchemaGenerator(infer_enums=False)
        schema = generator.generate(sample_data)

        tier_field = next(f for f in schema.node_types[0].fields if f.name == "tier")
        assert tier_field.enum is None

    def test_to_python_contains_field_declarations(self, sample_data):
        generator = SchemaGenerator()
        schema = generator.generate(sample_data, name="my_schema")
        code = generator.to_python(schema)

        assert "NodeType(\"person\")" in code
        assert "EdgeType(\"KNOWS\")" in code
        assert "GraphSchema(\"my_schema\")" in code

    def test_to_dict_round_trips_structure(self, sample_data):
        generator = SchemaGenerator()
        schema = generator.generate(sample_data, name="my_schema")
        d = generator.to_dict(schema)

        assert d["name"] == "my_schema"
        assert d["node_types"][0]["name"] == "person"
        assert d["edge_types"][0]["name"] == "KNOWS"
        assert d["edge_types"][0]["source_types"] == ["person"]

    def test_empty_data_produces_empty_schema(self, empty_data):
        generator = SchemaGenerator()
        schema = generator.generate(empty_data)

        assert schema.node_types == []
        assert schema.edge_types == []


# =============================================================================
# Canonical (Order-Independent) Generation Tests
#
# ison-graph guarantees to_ison()/to_isonl() output is canonical: the same
# logical graph always serializes to the same bytes regardless of
# construction order (sorted, ordinal string comparison). Schema generation
# should make the same guarantee - the same logical data should always
# generate the same schema code, regardless of what order nodes/edges/
# fields happened to appear in the source JSON, and regardless of Python's
# per-process hash randomization (node/edge type names and field names
# come from dict keys; enum values and pattern names come from sets).
# =============================================================================

class TestCanonicalGeneration:
    def _reordered_data(self):
        """Two JSON payloads describing the same logical graph, with
        node records, node fields, and edges all in different order."""
        data_a = {
            "nodes": [
                {"type": "zebra", "id": "1", "z_field": 1, "a_field": 2},
                {"type": "apple", "id": "1", "a_field": 1},
            ],
            "edges": [
                {"rel_type": "ZZZ", "source": {"type": "zebra", "id": "1"},
                 "target": {"type": "apple", "id": "1"}},
                {"rel_type": "AAA", "source": {"type": "apple", "id": "1"},
                 "target": {"type": "zebra", "id": "1"}},
            ],
        }
        data_b = {
            "nodes": [
                {"type": "apple", "id": "1", "a_field": 1},
                {"type": "zebra", "id": "1", "a_field": 2, "z_field": 1},
            ],
            "edges": [
                {"rel_type": "AAA", "source": {"type": "apple", "id": "1"},
                 "target": {"type": "zebra", "id": "1"}},
                {"rel_type": "ZZZ", "source": {"type": "zebra", "id": "1"},
                 "target": {"type": "apple", "id": "1"}},
            ],
        }
        return data_a, data_b

    def test_node_and_edge_type_order_is_sorted(self):
        data_a, data_b = self._reordered_data()
        generator = SchemaGenerator()

        schema_a = generator.generate(data_a, name="x")
        schema_b = generator.generate(data_b, name="x")

        assert [nt.name for nt in schema_a.node_types] == ["apple", "zebra"]
        assert [nt.name for nt in schema_b.node_types] == ["apple", "zebra"]
        assert [et.name for et in schema_a.edge_types] == ["AAA", "ZZZ"]
        assert [et.name for et in schema_b.edge_types] == ["AAA", "ZZZ"]

    def test_field_order_is_sorted(self):
        data_a, data_b = self._reordered_data()
        generator = SchemaGenerator()

        schema_a = generator.generate(data_a, name="x")
        zebra = next(nt for nt in schema_a.node_types if nt.name == "zebra")
        assert [f.name for f in zebra.fields] == ["a_field", "id", "z_field"]

    @pytest.mark.parametrize("fmt", ["to_python", "to_dict"])
    def test_generator_output_identical_regardless_of_input_order(self, fmt):
        data_a, data_b = self._reordered_data()
        generator = SchemaGenerator()

        schema_a = generator.generate(data_a, name="x")
        schema_b = generator.generate(data_b, name="x")

        result_a = getattr(generator, fmt)(schema_a)
        result_b = getattr(generator, fmt)(schema_b)
        assert result_a == result_b

    @pytest.mark.parametrize("fmt", [
        SchemaFormatter.to_python,
        SchemaFormatter.to_typescript,
        SchemaFormatter.to_json,
        SchemaFormatter.to_ison_schema,
    ])
    def test_formatter_output_identical_regardless_of_input_order(self, fmt):
        data_a, data_b = self._reordered_data()
        generator = SchemaGenerator()

        schema_a = generator.generate(data_a, name="x")
        schema_b = generator.generate(data_b, name="x")

        assert fmt(schema_a) == fmt(schema_b)

    def test_enum_values_are_sorted(self):
        data = {"nodes": [
            {"type": "t", "id": str(i), "tier": ["gold", "silver", "bronze"][i % 3]}
            for i in range(10)
        ], "edges": []}

        schema = SchemaGenerator().generate(data, name="x")
        tier_field = next(f for f in schema.node_types[0].fields if f.name == "tier")

        assert tier_field.enum == sorted(tier_field.enum)

    def test_source_target_types_are_sorted(self):
        data = {"nodes": [], "edges": [
            {"rel_type": "REL", "source": {"type": "zebra", "id": "1"},
             "target": {"type": "apple", "id": "1"}},
            {"rel_type": "REL", "source": {"type": "apple", "id": "1"},
             "target": {"type": "banana", "id": "1"}},
        ]}

        schema = SchemaGenerator().generate(data, name="x")
        rel = schema.edge_types[0]

        assert rel.source_types == sorted(rel.source_types)
        assert rel.target_types == sorted(rel.target_types)


class TestGenerateSchemaConvenienceFunction:
    def test_python_output(self, sample_data):
        result = generate_schema(sample_data, name="x", output_format="python")
        assert "NodeType(\"person\")" in result

    def test_dict_output_is_valid_json(self, sample_data):
        import json
        result = generate_schema(sample_data, name="x", output_format="dict")
        parsed = json.loads(result)
        assert parsed["name"] == "x"

    def test_unknown_format_raises(self, sample_data):
        with pytest.raises(ValueError):
            generate_schema(sample_data, name="x", output_format="bogus")


# =============================================================================
# SchemaFormatter Tests
# =============================================================================

class TestSchemaFormatter:
    @pytest.fixture
    def schema(self, sample_data):
        return SchemaGenerator().generate(sample_data, name="my_schema")

    def test_to_python(self, schema):
        code = SchemaFormatter.to_python(schema)

        assert "person_type = NodeType(\"person\")" in code
        assert "knows_type = EdgeType(\"KNOWS\")" in code
        assert "def validate(graph):" in code

    def test_to_typescript(self, schema):
        code = SchemaFormatter.to_typescript(schema)

        assert "new NodeType(\"person\")" in code
        assert "new EdgeType(\"KNOWS\")" in code
        assert "export const schema" in code

    def test_to_json(self, schema):
        import json
        result = json.loads(SchemaFormatter.to_json(schema))

        assert result["name"] == "my_schema"
        assert "person" in result["nodeTypes"]
        assert "KNOWS" in result["edgeTypes"]
        assert result["edgeTypes"]["KNOWS"]["sourceTypes"] == ["person"]

    def test_to_ison_schema(self, schema):
        result = SchemaFormatter.to_ison_schema(schema)

        assert "schema.graph my_schema" in result
        assert "schema.node person" in result
        assert "schema.edge KNOWS" in result

    def test_field_with_enum_renders_in_python(self, schema):
        code = SchemaFormatter.to_python(schema)
        assert ".enum(" in code

    def test_empty_schema(self, empty_data):
        schema = SchemaGenerator().generate(empty_data, name="empty")

        py = SchemaFormatter.to_python(schema)
        assert 'schema = GraphSchema("empty")' in py
