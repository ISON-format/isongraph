# ISONGraph Format Converters

Convert between ISONGraph and various popular graph formats.

## Supported Formats

| Format | Extension | Import | Export | Description |
|--------|-----------|--------|--------|-------------|
| ISON | `.ison` | ✅ | ✅ | Token-efficient format (68% smaller than JSON) |
| ISONL | `.isonl` | ✅ | ✅ | Streaming line-based format |
| JSON | `.json` | ✅ | ✅ | Standard JSON representation |
| GraphML | `.graphml` | ✅ | ✅ | XML-based graph format |
| RDF Turtle | `.ttl` | ✅ | ✅ | Semantic web format |
| N-Triples | `.nt` | ❌ | ✅ | Line-based RDF format |
| CSV | `.csv` | ✅ | ✅ | Tabular node/edge files |
| Neo4j Cypher | `.cypher` | ❌ | ✅ | Graph database import |
| DOT/Graphviz | `.dot` | ❌ | ✅ | Visualization format |

## Installation

Not on PyPI yet. Install from a checkout of the ISONGraph repo:

```bash
git clone https://github.com/ISON-format/isongraph.git
pip install ./isongraph/converters
```

## Command Line Usage

```bash
# Convert JSON to ISON
ison-convert input.json output.ison

# Convert ISON to GraphML
ison-convert graph.ison graph.graphml

# Convert to Cypher with MERGE statements
ison-convert graph.ison import.cypher --cypher-mode merge

# Convert to DOT with clustering by node type
ison-convert graph.ison graph.dot --clustered

# Convert to RDF Turtle with custom base URI
ison-convert graph.ison graph.ttl --base-uri https://myproject.org/
```

## Python API

### GraphML

```python
from converters import GraphMLConverter
from ison_graph import ISONGraph

# Export to GraphML
graph = ISONGraph("example")
graph.add_node("person", "alice", name="Alice", age=30)
graph.add_node("person", "bob", name="Bob", age=25)
graph.add_edge("KNOWS", ("person", "alice"), ("person", "bob"))

converter = GraphMLConverter()
graphml = converter.to_graphml(graph)

# Save to file
converter.save(graph, "graph.graphml")

# Import from GraphML
graph2 = converter.from_graphml(graphml)
# or from file
graph2 = converter.load("graph.graphml")
```

### RDF/Turtle

```python
from converters import RDFConverter

# Export to Turtle
converter = RDFConverter(base_uri="http://example.org/")
turtle = converter.to_turtle(graph)

# Export to N-Triples
ntriples = converter.to_ntriples(graph)

# Import from Turtle
graph2 = converter.from_turtle(turtle)
```

### CSV

```python
from converters import CSVConverter, Neo4jCSVConverter

# Export to standard CSV
converter = CSVConverter()
nodes_csv, edges_csv = converter.to_csv(graph)

# Save to files
converter.save(graph, "nodes.csv", "edges.csv")

# Import from CSV
graph2 = converter.from_csv(nodes_csv, edges_csv)
# or from files
graph2 = converter.load("nodes.csv", "edges.csv")

# Neo4j-compatible CSV format
neo4j_converter = Neo4jCSVConverter()
nodes_csv, rels_csv = neo4j_converter.to_neo4j_csv(graph)
```

### Neo4j Cypher

```python
from converters import CypherConverter

converter = CypherConverter()

# Generate CREATE statements
cypher = converter.to_cypher(graph, mode="create")

# Generate MERGE statements (idempotent)
cypher = converter.to_cypher(graph, mode="merge")

# Generate batched Cypher with UNWIND (efficient for large graphs)
cypher = converter.to_cypher_batch(graph, mode="merge")

# Generate APOC-based import (requires APOC library)
cypher = converter.to_cypher_apoc(graph, mode="merge")
```

### DOT/Graphviz

```python
from converters import DOTConverter

converter = DOTConverter(
    label_property="name",  # Property to use as node label
    show_properties=False,  # Show all properties in label
    rankdir="TB",           # Layout direction (TB, BT, LR, RL)
)

# Generate DOT format
dot = converter.to_dot(graph)

# Generate clustered DOT (groups by node type)
dot = converter.to_dot_clustered(graph)

# Save as DOT file
converter.save(graph, "graph.dot")

# Save as SVG (requires Graphviz installed)
converter.save_svg(graph, "graph.svg")

# Save as PNG (requires Graphviz installed)
converter.save_png(graph, "graph.png")
```

## Format Details

### GraphML
- XML-based standard format
- Preserves all node/edge types and properties
- Compatible with yEd, Gephi, NetworkX, and many other tools
- Good for archival and interoperability

### RDF/Turtle
- Semantic web standard
- Nodes become RDF resources with URIs
- Edges become RDF predicates
- Properties become RDF literals
- Compatible with SPARQL endpoints and triple stores

### CSV
- Simple tabular format
- Separate files for nodes and edges
- Easy to edit in spreadsheets
- Good for data import/export pipelines

### Neo4j Cypher
- Direct import into Neo4j graph database
- Supports CREATE and MERGE modes
- Batched mode for large imports
- APOC mode for best performance

### DOT/Graphviz
- Standard graph visualization format
- Automatic layout algorithms
- Supports node shapes, colors, and clustering
- Can render to SVG, PNG, PDF

## Token Efficiency Comparison

When converting to ISON format, you get significant token savings:

| Format | Tokens | Savings vs JSON |
|--------|--------|-----------------|
| JSON | 1000 | - |
| ISON | 314 | 68.6% |
| GraphML | 1500 | -50% |
| Turtle | 800 | 20% |
| CSV | 400 | 60% |

ISON format is optimized for LLM context windows, making it ideal when you need to inject graph data into prompts.

## Custom Node Styling (DOT)

```python
converter = DOTConverter(
    shapes={
        "person": "ellipse",
        "company": "box",
        "document": "note",
    },
    colors={
        "person": "#a8d5ba",
        "company": "#f4a460",
        "document": "#87ceeb",
    }
)
```

## Error Handling

All converters raise appropriate exceptions:

```python
try:
    graph = converter.load("nonexistent.graphml")
except FileNotFoundError:
    print("File not found")

try:
    graph = converter.from_graphml("invalid xml")
except ValueError as e:
    print(f"Parse error: {e}")
```
