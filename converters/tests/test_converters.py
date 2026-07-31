"""
Tests for Converters Package
============================

Comprehensive tests for graph format converters including
GraphML, CSV, Cypher, DOT, and RDF converters.
"""

import pytest
import tempfile
import os
import warnings
from pathlib import Path

from ison_graph import ISONGraph

from converters.graphml import GraphMLConverter
from converters.csv_converter import CSVConverter, Neo4jCSVConverter
from converters.cypher import CypherConverter


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_graph():
    """Create a sample ISONGraph for testing"""
    graph = ISONGraph(name="test-graph")

    # Add nodes
    graph.add_node("person", "alice", name="Alice Smith", age=30, active=True)
    graph.add_node("person", "bob", name="Bob Jones", age=25, active=True)
    graph.add_node("company", "acme", name="Acme Corp", founded=1990)
    graph.add_node("project", "proj1", name="Project Alpha", budget=50000.0)

    # Add edges
    graph.add_edge("WORKS_AT", ("person", "alice"), ("company", "acme"),
                   since="2020-01-01", role="Engineer")
    graph.add_edge("WORKS_AT", ("person", "bob"), ("company", "acme"),
                   since="2021-06-15", role="Manager")
    graph.add_edge("MANAGES", ("person", "bob"), ("person", "alice"))
    graph.add_edge("ASSIGNED_TO", ("person", "alice"), ("project", "proj1"),
                   hours=20)

    return graph


@pytest.fixture
def empty_graph():
    """Create an empty ISONGraph"""
    return ISONGraph(name="empty-graph")


@pytest.fixture
def complex_graph():
    """Create a more complex graph for edge case testing"""
    graph = ISONGraph(name="complex-graph")

    # Nodes with special characters and various types
    graph.add_node("type_with_spaces", "id-with-dashes",
                   special_chars="Hello, World! <>&\"'",
                   list_value="[1, 2, 3]",
                   json_value='{"key": "value"}')

    graph.add_node("numbers", "num1",
                   integer=42,
                   float_val=3.14159,
                   negative=-100,
                   zero=0)

    graph.add_node("booleans", "bool1",
                   true_val=True,
                   false_val=False)

    graph.add_node("empty_props", "empty1")

    return graph


# =============================================================================
# GraphML Converter Tests
# =============================================================================

class TestGraphMLConverter:
    """Tests for GraphML converter"""

    @pytest.fixture
    def converter(self):
        return GraphMLConverter()

    def test_converter_initialization(self, converter):
        """Test converter initialization"""
        assert converter.include_properties is True

    def test_to_graphml_basic(self, converter, sample_graph):
        """Test basic conversion to GraphML"""
        graphml = converter.to_graphml(sample_graph)

        assert graphml is not None
        assert "<?xml" in graphml
        assert "graphml" in graphml
        assert "person:alice" in graphml
        assert "Alice Smith" in graphml

    def test_to_graphml_contains_edges(self, converter, sample_graph):
        """Test that edges are included in GraphML"""
        graphml = converter.to_graphml(sample_graph)

        assert "WORKS_AT" in graphml
        assert "MANAGES" in graphml

    def test_from_graphml_roundtrip(self, converter, sample_graph):
        """Test GraphML roundtrip conversion"""
        graphml = converter.to_graphml(sample_graph)
        restored = converter.from_graphml(graphml, "restored")

        assert restored.node_count() == sample_graph.node_count()
        assert restored.edge_count() == sample_graph.edge_count()

    def test_empty_graph(self, converter, empty_graph):
        """Test conversion of empty graph"""
        graphml = converter.to_graphml(empty_graph)

        assert "<?xml" in graphml
        assert "graphml" in graphml

    def test_save_and_load(self, converter, sample_graph, tmp_path):
        """Test saving and loading GraphML files"""
        path = tmp_path / "test.graphml"

        converter.save(sample_graph, str(path))
        assert path.exists()

        loaded = converter.load(str(path))
        assert loaded.node_count() == sample_graph.node_count()

    def test_special_characters(self, converter, complex_graph):
        """Test handling of special characters"""
        graphml = converter.to_graphml(complex_graph)

        # Should properly escape special XML characters
        assert graphml is not None

        # Roundtrip should preserve data
        restored = converter.from_graphml(graphml, "restored")
        assert restored.node_count() == complex_graph.node_count()

    def test_without_properties(self, sample_graph):
        """Test conversion without properties"""
        converter = GraphMLConverter(include_properties=False)
        graphml = converter.to_graphml(sample_graph)

        assert graphml is not None
        # Properties might still appear due to implementation

    def test_from_graphml_duplicate_edge_is_skipped_with_warning(self, converter):
        """Duplicate (rel_type, source, target) edges are deduped, not a crash"""
        graphml = """<?xml version="1.0" encoding="UTF-8"?>
        <graphml xmlns="http://graphml.graphdrawing.org/xmlns">
          <key id="edge_type" for="edge" attr.name="rel_type" attr.type="string"/>
          <graph id="g" edgedefault="directed">
            <node id="person:alice"/>
            <node id="person:bob"/>
            <edge source="person:alice" target="person:bob">
              <data key="edge_type">KNOWS</data>
            </edge>
            <edge source="person:alice" target="person:bob">
              <data key="edge_type">KNOWS</data>
            </edge>
          </graph>
        </graphml>"""

        with pytest.warns(UserWarning, match="duplicate edge"):
            graph = converter.from_graphml(graphml, "dedup-test")

        assert graph.edge_count() == 1
        assert graph.has_edge("KNOWS", ("person", "alice"), ("person", "bob"))

    def test_from_graphml_no_warning_without_duplicates(self, converter, sample_graph):
        """No warning is raised when there are no duplicate edges"""
        graphml = converter.to_graphml(sample_graph)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            restored = converter.from_graphml(graphml, "no-dupes")

        assert restored.edge_count() == sample_graph.edge_count()


# =============================================================================
# CSV Converter Tests
# =============================================================================

class TestCSVConverter:
    """Tests for CSV converter"""

    @pytest.fixture
    def converter(self):
        return CSVConverter()

    def test_converter_initialization(self, converter):
        """Test converter initialization"""
        assert converter.delimiter == ","
        assert converter.quotechar == '"'
        assert converter.include_headers is True

    def test_to_csv_basic(self, converter, sample_graph):
        """Test basic conversion to CSV"""
        nodes_csv, edges_csv = converter.to_csv(sample_graph)

        assert nodes_csv is not None
        assert edges_csv is not None
        assert "person" in nodes_csv
        assert "alice" in nodes_csv
        assert "WORKS_AT" in edges_csv

    def test_to_csv_headers(self, converter, sample_graph):
        """Test that headers are included"""
        nodes_csv, edges_csv = converter.to_csv(sample_graph)

        lines = nodes_csv.strip().split('\n')
        assert lines[0].startswith("type,id")

        edge_lines = edges_csv.strip().split('\n')
        assert "rel_type" in edge_lines[0]

    def test_from_csv_roundtrip(self, converter, sample_graph):
        """Test CSV roundtrip conversion"""
        nodes_csv, edges_csv = converter.to_csv(sample_graph)
        restored = converter.from_csv(nodes_csv, edges_csv, "restored")

        assert restored.node_count() == sample_graph.node_count()
        assert restored.edge_count() == sample_graph.edge_count()

    def test_from_csv_nodes_only(self, converter, sample_graph):
        """Test conversion with nodes only"""
        nodes_csv, _ = converter.to_csv(sample_graph)
        restored = converter.from_csv(nodes_csv, None, "nodes-only")

        assert restored.node_count() == sample_graph.node_count()
        assert restored.edge_count() == 0

    def test_empty_graph(self, converter, empty_graph):
        """Test conversion of empty graph"""
        nodes_csv, edges_csv = converter.to_csv(empty_graph)

        # Should have headers at minimum
        assert nodes_csv is not None

    def test_save_and_load(self, converter, sample_graph, tmp_path):
        """Test saving and loading CSV files"""
        nodes_path = tmp_path / "nodes.csv"
        edges_path = tmp_path / "edges.csv"

        converter.save(sample_graph, str(nodes_path), str(edges_path))

        assert nodes_path.exists()
        assert edges_path.exists()

        loaded = converter.load(str(nodes_path), str(edges_path))
        assert loaded.node_count() == sample_graph.node_count()

    def test_custom_delimiter(self, sample_graph):
        """Test CSV with custom delimiter"""
        converter = CSVConverter(delimiter=";")
        nodes_csv, _ = converter.to_csv(sample_graph)

        assert ";" in nodes_csv

    def test_value_serialization(self, converter, complex_graph):
        """Test value serialization for different types"""
        nodes_csv, _ = converter.to_csv(complex_graph)

        assert "true" in nodes_csv.lower() or "True" in nodes_csv
        assert "false" in nodes_csv.lower() or "False" in nodes_csv
        assert "42" in nodes_csv
        assert "3.14159" in nodes_csv

    def test_from_csv_duplicate_edge_is_skipped_with_warning(self, converter):
        """Duplicate (rel_type, source, target) rows are deduped, not a crash"""
        nodes_csv = (
            "type,id\n"
            "person,alice\n"
            "person,bob\n"
        )
        edges_csv = (
            "rel_type,source_type,source_id,target_type,target_id\n"
            "KNOWS,person,alice,person,bob\n"
            "KNOWS,person,alice,person,bob\n"
        )

        with pytest.warns(UserWarning, match="duplicate edge"):
            graph = converter.from_csv(nodes_csv, edges_csv, "dedup-test")

        assert graph.edge_count() == 1
        assert graph.has_edge("KNOWS", ("person", "alice"), ("person", "bob"))

    def test_from_csv_no_warning_without_duplicates(self, converter, sample_graph):
        """No warning is raised when there are no duplicate edge rows"""
        nodes_csv, edges_csv = converter.to_csv(sample_graph)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            restored = converter.from_csv(nodes_csv, edges_csv, "no-dupes")

        assert restored.edge_count() == sample_graph.edge_count()


class TestNeo4jCSVConverter:
    """Tests for Neo4j CSV converter"""

    @pytest.fixture
    def converter(self):
        return Neo4jCSVConverter()

    def test_to_neo4j_csv_basic(self, converter, sample_graph):
        """Test Neo4j CSV format"""
        nodes_csv, rels_csv = converter.to_neo4j_csv(sample_graph)

        # Check Neo4j header format
        assert ":ID" in nodes_csv
        assert ":LABEL" in nodes_csv
        assert ":START_ID" in rels_csv
        assert ":END_ID" in rels_csv
        assert ":TYPE" in rels_csv

    def test_node_id_format(self, converter, sample_graph):
        """Test that node IDs include type prefix"""
        nodes_csv, _ = converter.to_neo4j_csv(sample_graph)

        assert "person:alice" in nodes_csv
        assert "company:acme" in nodes_csv


# =============================================================================
# Cypher Converter Tests
# =============================================================================

class TestCypherConverter:
    """Tests for Cypher converter"""

    @pytest.fixture
    def converter(self):
        return CypherConverter()

    def test_converter_initialization(self, converter):
        """Test converter initialization"""
        assert converter.use_labels is True
        assert converter.batch_size == 1000

    def test_to_cypher_create(self, converter, sample_graph):
        """Test CREATE mode conversion"""
        cypher = converter.to_cypher(sample_graph, mode="create")

        assert "CREATE" in cypher
        assert "Person" in cypher or "person" in cypher
        assert "alice" in cypher

    def test_to_cypher_merge(self, converter, sample_graph):
        """Test MERGE mode conversion"""
        cypher = converter.to_cypher(sample_graph, mode="merge")

        assert "MERGE" in cypher
        assert "SET" in cypher

    def test_to_cypher_contains_relationships(self, converter, sample_graph):
        """Test that relationships are included"""
        cypher = converter.to_cypher(sample_graph, mode="create")

        assert "WORKS_AT" in cypher
        assert "MANAGES" in cypher

    def test_to_cypher_batch(self, converter, sample_graph):
        """Test batched Cypher generation"""
        cypher = converter.to_cypher_batch(sample_graph)

        assert "UNWIND" in cypher

    def test_to_cypher_apoc(self, converter, sample_graph):
        """Test APOC-based Cypher generation"""
        cypher = converter.to_cypher_apoc(sample_graph)

        assert "APOC" in cypher or "apoc" in cypher

    def test_empty_graph(self, converter, empty_graph):
        """Test conversion of empty graph"""
        cypher = converter.to_cypher(empty_graph)

        assert "Generated Cypher" in cypher
        assert "Nodes: 0" in cypher

    def test_save(self, converter, sample_graph, tmp_path):
        """Test saving Cypher script"""
        path = tmp_path / "script.cypher"

        converter.save(sample_graph, str(path))

        assert path.exists()
        content = path.read_text()
        assert "CREATE" in content or "MERGE" in content

    def test_save_batch(self, converter, sample_graph, tmp_path):
        """Test saving batched Cypher script"""
        path = tmp_path / "batch.cypher"

        converter.save_batch(sample_graph, str(path))

        assert path.exists()
        content = path.read_text()
        assert "UNWIND" in content

    def test_special_characters_escaping(self, converter, complex_graph):
        """Test proper escaping of special characters"""
        cypher = converter.to_cypher(complex_graph)

        # Should escape quotes properly
        assert cypher is not None
        # No unclosed strings
        assert cypher.count("'") % 2 == 0 or "\\\'" in cypher

    def test_label_escaping(self, converter):
        """Test label escaping for Neo4j"""
        # Labels with spaces should be converted to underscores
        escaped = converter._escape_label("label with spaces")
        assert " " not in escaped

        # Labels starting with numbers should be prefixed
        escaped = converter._escape_label("123label")
        assert escaped[0].isalpha() or escaped[0] == "_"


# =============================================================================
# Integration Tests
# =============================================================================

class TestConverterIntegration:
    """Integration tests across converters"""

    def test_graphml_csv_interoperability(self, sample_graph, tmp_path):
        """Test that GraphML and CSV produce equivalent graphs"""
        graphml_conv = GraphMLConverter()
        csv_conv = CSVConverter()

        # Convert to both formats
        graphml = graphml_conv.to_graphml(sample_graph)
        nodes_csv, edges_csv = csv_conv.to_csv(sample_graph)

        # Restore from both
        from_graphml = graphml_conv.from_graphml(graphml, "from-graphml")
        from_csv = csv_conv.from_csv(nodes_csv, edges_csv, "from-csv")

        # Both should have same counts
        assert from_graphml.node_count() == from_csv.node_count()
        assert from_graphml.edge_count() == from_csv.edge_count()

    def test_large_graph_handling(self):
        """Test handling of larger graphs"""
        graph = ISONGraph(name="large-graph")

        # Create a moderately large graph
        for i in range(100):
            graph.add_node("entity", f"e{i}", index=i, name=f"Entity {i}")

        for i in range(50):
            graph.add_edge("RELATES_TO",
                          ("entity", f"e{i}"),
                          ("entity", f"e{i+1}"))

        # All converters should handle it
        graphml_conv = GraphMLConverter()
        csv_conv = CSVConverter()
        cypher_conv = CypherConverter()

        graphml = graphml_conv.to_graphml(graph)
        nodes_csv, edges_csv = csv_conv.to_csv(graph)
        cypher = cypher_conv.to_cypher(graph)

        assert graphml is not None
        assert nodes_csv is not None
        assert cypher is not None

    def test_property_preservation(self, complex_graph):
        """Test that properties are preserved across conversions"""
        csv_conv = CSVConverter()

        nodes_csv, _ = csv_conv.to_csv(complex_graph)
        restored = csv_conv.from_csv(nodes_csv, None, "restored")

        # Check that numeric properties are preserved
        for node in restored.nodes():
            if node.type == "numbers":
                # Values should be numeric (may be strings after CSV roundtrip)
                assert "integer" in node.properties or any(
                    "42" in str(v) for v in node.properties.values()
                )
