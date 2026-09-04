<p align="center">
  <img src="assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ISONGraph

**Token-Efficient Property Graph Store for the AI Era**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![Rust](https://img.shields.io/badge/Rust-2021-orange.svg)](https://www.rust-lang.org/)

ISONGraph is a **multi-language property graph library** designed specifically for LLM and AI applications. It is the most token-efficient **graph** format in our 10-format benchmark while maintaining high accuracy for graph-based reasoning tasks. (For flat, non-graph data, its sibling format ISON is smaller still: ISONGraph spends a few extra tokens on relationship primitives, which is what you want when your data has edges.)

---

## Why ISONGraph?

### The Problem

When working with LLMs, every token counts. Traditional graph formats like JSON, GraphML, or RDF are verbose and waste precious context window space:

```json
{
  "nodes": [
    {"id": 1, "type": "person", "name": "Alice", "age": 30},
    {"id": 2, "type": "person", "name": "Bob", "age": 25}
  ],
  "edges": [
    {"source": 1, "target": 2, "relation": "knows", "since": 2020}
  ]
}
```
**In the full benchmark document, JSON uses 596 tokens for this dataset — the snippet above is an abbreviated excerpt.**

### The Solution

ISONGraph uses a compact tabular format that LLMs understand naturally:

```
edges.KNOWS
since source target
2020 :person:1 :person:2

nodes.person
id age name
1 30 Alice
2 25 Bob
```
**ISONGraph represents the same full dataset in 177 tokens: 70% smaller than formatted JSON, ~41% smaller than minified JSON. Both baselines are reported in the benchmark.**

### Benchmark Results

ISONGraph has been comprehensively tested with two benchmark suites:

#### Knowledge Graph Benchmark (Format Comparison)
*100 questions, 7 datasets, 10 formats (top 8 shown)*

| Format | Tokens | Savings vs JSON (pretty) | Savings vs JSON (minified) | Accuracy | Efficiency |
|--------|--------|--------------------------|----------------------------|----------|------------|
| **ISONGraph** | **1,698** | **68.6%** | **41.3%** | **90.0%** | **53.00** |
| ISON | 1,976 | 63.4% | 31.7% | 88.0% | 44.53 |
| JSON Compact | 2,893 | 46.5% | 0.0% | 88.0% | 30.42 |
| TOON | 2,934 | 45.7% | -1.4% | 85.0% | 28.97 |
| Cypher (Neo4j) | 3,522 | 34.9% | -21.7% | 89.0% | 25.27 |
| JSON | 5,406 | 0.0% | -86.9% | 87.0% | 16.09 |
| RDF/Turtle | 4,166 | 22.9% | -44.0% | 58.0% | 13.92 |
| GraphML | 9,093 | -68.2% | -214.3% | 87.0% | 9.57 |

*Two baselines are reported deliberately: pretty-printed JSON (`indent=2`) is what most codebases emit today; minified JSON is the strongest JSON baseline. ISONGraph saves 41.3% against the strongest baseline. Note: with current `ison-py` releases, plain ISON serializes these datasets at 1,606 tokens (tighter than the 1,976 recorded here); see Limitations in the full results.*

#### Data Traversal Benchmark (Graph Operations)
*50 questions, 4 datasets, 5 formats*

| Format | Tokens | Accuracy | Efficiency (Acc/1K) |
|--------|--------|----------|---------------------|
| **ISONGraph** | **639** | **92.0%** | **143.97** |
| ISON | 685 | 88.0% | 128.47 |
| TOON | 856 | 80.0% | 93.46 |
| JSON Compact | 1,072 | 82.0% | 76.49 |
| JSON | 2,039 | 84.0% | 41.20 |

**Key Findings:**
- **Efficiency (the headline result)**: ISONGraph delivers the best accuracy-per-token of all 10 formats: 53.0 acc/1K tokens, 74% ahead of minified JSON
- **Accuracy**: ISONGraph scored highest (90%), but differences inside the top cluster (85-90%) are within sampling noise at n=100; the statistically robust accuracy result is compact formats vs the verbose tail (RDF/Turtle: 58%)
- **Data Traversal**: ISONGraph achieves 92% accuracy on graph operations
- **Multi-hop queries**: 18/21 for ISONGraph vs 10/21 for RDF/Turtle on identical data
- **Best fit**: reference graphs serialized once and read many times. If you mutate a graph inside a cached prompt prefix between turns, columnar layouts invalidate more of the cache than JSON does; see Limitations in [BENCHMARK.md](benchmark/KnowledgeGraph_Benchmark/BENCHMARK.md)

*See [benchmark/](benchmark/) for detailed results and methodology*

---

## Features

### Core Graph Operations
- **Node & Edge CRUD** - Create, read, update, delete with O(1) lookups
- **Multi-hop Traversal** - Traverse N hops in any direction
- **Path Finding** - BFS shortest path, DFS all paths
- **Graph Analysis** - Connectivity, cycle detection, components
- **Fluent Query API** - Chainable traversal interface
- **Pattern Queries** - Cypher-like query patterns
- **ISONQL** - Declarative SQL-like query language for graphs
- **Visualization** - Deterministic force layout + SVG/HTML rendering (Python, JavaScript, TypeScript, C# - bit-identical geometry across languages)

### Schema Validation (ISONGraphantic)
- **Type Validators** - String, Int, Float, Bool, Ref
- **Constraints** - Required, min/max, patterns, enums
- **Edge Constraints** - No self-loops, unique, acyclic, cardinality
- **Graph Constraints** - Connected, no orphans, max depth

### Semantic Search (Embeddings) — planned
- **Vector Embeddings** - Automatic node embedding
- **Similarity Search** - Find semantically similar nodes
- **Semantic Multi-hop** - Combine embeddings with graph traversal
- **SQLite Storage** - Persistent vector store

*Ships as the separate `ison-graph-embeddings` package, not yet released.*

### Multi-Language Support
- **Python** - Native implementation
- **TypeScript** - Full feature parity
- **Rust** - High-performance implementation
- **C++** - Header-only library
- **C#** - .NET 8 library (`IsonGraph`), zero dependencies

---

## Installation

All packages are live: [PyPI](https://pypi.org/project/ison-graph/) · [npm (ison-graph-ts)](https://www.npmjs.com/package/ison-graph-ts) · [npm (ison-graph-js)](https://www.npmjs.com/package/ison-graph-js) · [crates.io](https://crates.io/crates/ison-graph)

### Python

```bash
pip install ison-graph   # includes ISONQL and schema validation (ison_graph.schema)
```

### TypeScript / JavaScript

```bash
npm install ison-graph-ts
```

### Rust

```toml
[dependencies]
ison-graph = "1.4.0"
```

### C++

```cmake
find_package(ison_graph REQUIRED)
target_link_libraries(your_target ison::ison_graph)
```

### C# (.NET 8)

```bash
dotnet add package IsonGraph
```

---

## Quick Start

### Basic Graph Operations

```python
from ison_graph import ISONGraph, Direction

# Create a graph
graph = ISONGraph(name='social')

# Add nodes
graph.add_node('person', 1, name='Alice', age=30)
graph.add_node('person', 2, name='Bob', age=25)
graph.add_node('person', 3, name='Carol', age=28)
graph.add_node('company', 100, name='TechCorp', employees=500)

# Add edges
graph.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)
graph.add_edge('KNOWS', ('person', 2), ('person', 3), since=2021)
graph.add_edge('WORKS_AT', ('person', 1), ('company', 100), role='Engineer')

# Query neighbors
friends = graph.neighbors(('person', 1), 'KNOWS')
# [('person', 2)]

# Multi-hop traversal
friends_of_friends = graph.multi_hop(('person', 1), 'KNOWS', hops=2)
# [('person', 3)]

# Find shortest path
path = graph.shortest_path(('person', 1), ('person', 3))
# Path: person:1 -> person:2 -> person:3

# Fluent API
results = graph.start(('person', 1)) \
    .hop('KNOWS') \
    .hop('KNOWS') \
    .filter(lambda n: n.properties.get('age', 0) > 25) \
    .collect()

# Serialize to ISON format
print(graph.to_ison())
```

**Output** (node types and fields are emitted in sorted order):
```
edges.KNOWS
since source target
2020 :person:1 :person:2
2021 :person:2 :person:3

edges.WORKS_AT
role source target
Engineer :person:1 :company:100

nodes.company
id employees name
100 500 TechCorp

nodes.person
id age name
1 30 Alice
2 25 Bob
3 28 Carol
```

### Schema Validation

```python
from ison_graph.schema import (
    GraphSchema, NodeType, EdgeType,
    String, Int, Cardinality
)

# Define node types
Person = NodeType('person') \
    .id(Int()) \
    .field('name', String().required().max(100)) \
    .field('age', Int().min(0).max(150))

Company = NodeType('company') \
    .id(Int()) \
    .field('name', String().required()) \
    .field('employees', Int().min(1))

# Define edge types
Knows = EdgeType('KNOWS') \
    .from_node(Person) \
    .to_node(Person) \
    .field('since', Int()) \
    .no_self_loop() \
    .unique()

WorksAt = EdgeType('WORKS_AT') \
    .from_node(Person) \
    .to_node(Company) \
    .field('role', String()) \
    .cardinality(Cardinality.MANY_TO_ONE)

# Create schema
schema = GraphSchema('social') \
    .node_types(Person, Company) \
    .edge_types(Knows, WorksAt) \
    .no_orphans()

# Validate graph
result = schema.validate(graph)

if result.valid:
    print("Graph is valid!")
else:
    for error in result.errors:
        print(f"Error: {error.code} - {error.message}")
```

### Semantic Search (planned)

> The `ison-graph-embeddings` package shown below is on the roadmap and not yet released; the API is a preview.

```python
from ison_graph_embeddings import SemanticGraph, SentenceTransformerEncoder

# Create semantic graph with embeddings
encoder = SentenceTransformerEncoder(model_name="all-MiniLM-L6-v2")
graph = SemanticGraph(
    name='knowledge',
    embedding_db='knowledge.db',
    encoder=encoder,
    auto_embed=True
)

# Add nodes with automatic embedding
graph.add_node('article', 1,
    title='Introduction to Machine Learning',
    _embed_text='Machine learning is a subset of AI that enables systems to learn from data'
)
graph.add_node('article', 2,
    title='Deep Learning Fundamentals',
    _embed_text='Deep learning uses neural networks with multiple layers for complex pattern recognition'
)

# Find similar articles
results = graph.similarity_search(
    query="artificial intelligence and neural networks",
    top_k=5,
    threshold=0.5
)

for result in results:
    print(f"{result.node_ref}: {result.score:.3f}")

# Semantic multi-hop: find related content through graph structure
results = graph.semantic_multi_hop(
    query="machine learning techniques",
    rel_type='REFERENCES',
    max_hops=2,
    top_k_results=10
)
```

---

## Architecture

### Module Structure

```
isongraph/
├── ison-graph/              # Core Python library
│   └── src/ison_graph/
├── ison-graph-js/           # JavaScript implementation
├── ison-graph-ts/           # TypeScript implementation
├── ison-graph-rs/           # Rust implementation (crate name: ison-graph)
├── ison-graph-cpp/          # C++ implementation (header-only)
├── ison-graph-cs/           # C# implementation (.NET 8, package: IsonGraph)
├── vscode-isongraph/        # VS Code extension: graph visualizer (d3-based)
├── vscode-isongraphviz/     # VS Code extension: deterministic viz (zero-dependency)
├── benchmark/               # Performance benchmarks
└── assets/                  # Logos and images
```

Additional developer tooling (including the ISON language VS Code extension) is maintained in separate repositories under the [isongraph](https://github.com/isongraph) organization.

### Data Model

```
ISONGraph
├── _nodes: {type: {id: Node}}           # O(1) node lookup
├── _edges: {rel_type: [Edge]}           # Edges grouped by type
├── _out_edges: {NodeRef: [Edge]}        # Outgoing edges index
├── _in_edges: {NodeRef: [Edge]}         # Incoming edges index
└── _edge_set: Set[EdgeKey]              # Uniqueness check
```

### Core Types

```text
NodeRef = Tuple[str, Any]  # (type, id) e.g., ('person', 1)

Node:
    type: str
    id: Any
    properties: Dict[str, Any]

Edge:
    rel_type: str
    source: NodeRef
    target: NodeRef
    properties: Dict[str, Any]

Path:
    nodes: List[NodeRef]
    edges: List[Edge]
    length: int
    start: NodeRef
    end: NodeRef
```

---

## API Reference

### ISONGraph Core

#### Constructor

```text
ISONGraph(name: str = "graph", directed: bool = True)
```

#### Node Operations

| Method | Description |
|--------|-------------|
| `add_node(type, id, **props)` | Add a node with properties |
| `get_node(type, id)` | Get node by type and id |
| `has_node(type, id)` | Check if node exists |
| `remove_node(type, id)` | Remove a node |
| `update_node(type, id, **props)` | Update node properties |
| `nodes(type=None)` | Iterator over nodes |
| `node_count(type=None)` | Count nodes |
| `node_types()` | List all node types |

#### Edge Operations

| Method | Description |
|--------|-------------|
| `add_edge(rel_type, source, target, **props)` | Add an edge |
| `get_edge(rel_type, source, target)` | Get edge |
| `has_edge(rel_type, source, target)` | Check if edge exists |
| `remove_edge(rel_type, source, target)` | Remove an edge |
| `edges(rel_type=None)` | Iterator over edges |
| `edge_count(rel_type=None)` | Count edges |
| `edge_types()` | List all edge types |

ISONGraph is a **simple graph**: `add_edge` raises `DuplicateEdgeError` on a
repeated `(rel_type, source, target)` triple, so parallel edges between the
same pair aren't representable. This is deliberate, not a gap to work
around - the uniqueness of that triple is what lets serialization stay
canonical (edge rows sort by `(source, target)` with no tie-breaking
needed). If you're converting from a source that has genuine multigraph
edges (repeated relationships, multiple timestamps between the same pair),
resolve that in the converter before calling `add_edge` - either skip
repeats, or merge their properties into one edge (e.g. a list-valued
property, or the earliest/latest timestamp), whichever fits the source
semantics. Catching `DuplicateEdgeError` around the call is the simplest
way to do this inline.

#### Traversal

| Method | Description |
|--------|-------------|
| `neighbors(node, rel_type, direction)` | Get adjacent nodes |
| `multi_hop(start, rel_type, hops, direction)` | N-hop traversal |
| `multi_hop_range(start, rel_type, min, max)` | Range traversal |
| `traverse(start, pattern, filter_fn)` | Pattern-based traversal |

#### Path Finding

| Method | Description |
|--------|-------------|
| `shortest_path(start, end, max_hops)` | BFS shortest path |
| `all_paths(start, end, max_hops)` | DFS all paths |
| `path_exists(start, end, max_hops)` | Check path existence |

#### Graph Analysis

| Method | Description |
|--------|-------------|
| `in_degree(node)` | Count incoming edges |
| `out_degree(node)` | Count outgoing edges |
| `degree(node)` | Total degree |
| `is_connected()` | Check connectivity |
| `has_cycle(rel_type)` | Detect cycles |
| `connected_components()` | Find components |

#### Fluent API

```text
graph.start(node_ref)
    .hop(rel_type, direction, where)
    .hops(n, rel_type, direction)
    .filter(fn)
    .collect()        # List[NodeRef]
    .collect_nodes()  # List[Node]
    .count()          # int
    .first()          # Optional[NodeRef]
```

#### Pattern Queries (ISONQL)

```python
# Neighbors: traverse KNOWS edges from person:1
engine.execute("TRAVERSE person:1 -> KNOWS -> person")

# Multi-hop: traverse up to 2 hops
engine.execute("TRAVERSE person:1 -> KNOWS -> person MAX 2")

# Shortest path between two nodes via KNOWS edges
engine.execute("PATH person:1 TO person:3 VIA KNOWS")
```

### ISONQL Query Language

ISONQL provides SQL-like declarative queries for property graphs. Available in Python, TypeScript, Rust, and C++.

#### Query Types

```python
from ison_graph.query import QueryEngine

engine = QueryEngine(graph)

# NODES - Query nodes with conditions
engine.execute("NODES person WHERE age > 25")
engine.execute("NODES person WHERE age > 25 AND city = NYC")
engine.execute("NODES person ORDER BY age DESC LIMIT 10")

# EDGES - Query edges
engine.execute("EDGES KNOWS WHERE since > 2020")

# TRAVERSE - Graph traversal
engine.execute("TRAVERSE person:alice -> KNOWS -> person")
engine.execute("TRAVERSE person:alice -> KNOWS -> person MAX 3")

# PATH - Find shortest path
engine.execute("PATH person:alice TO person:charlie VIA KNOWS")

# COUNT - Count nodes
engine.execute("COUNT person WHERE city = NYC")

# Aggregations
engine.execute("AVG person.age WHERE city = NYC")
engine.execute("SUM person.salary")
engine.execute("MIN person.age")
engine.execute("MAX company.employees")
```

#### Operators

| Operator | Example |
|----------|---------|
| `=`, `!=` | `name = Alice`, `city != LA` |
| `>`, `>=`, `<`, `<=` | `age > 25` |
| `IN`, `NOT IN` | `city IN (NYC, LA, SF)` |
| `CONTAINS` | `name CONTAINS lic` (case-sensitive) |
| `STARTS_WITH`, `ENDS_WITH` | `name STARTS_WITH A` |
| `MATCHES` | `email MATCHES '^[a-z]+@'` |
| `EXISTS`, `NOT EXISTS` | `email EXISTS` or `EXISTS email` |

#### Fluent Query Builder

```python
# Build queries programmatically (engine.match for nodes, engine.match_edges for edges)
result = engine.match("person") \
    .where("age", ">", 25) \
    .where("city", "=", "NYC") \
    .order_by("age", "DESC") \
    .limit(10) \
    .execute()
```

#### Serialization

| Method | Description |
|--------|-------------|
| `to_ison()` | Serialize to ISON format |
| `to_isonl()` | Serialize to ISONL (streaming) |
| `from_ison(text)` | Parse from ISON |
| `from_isonl(text)` | Parse from ISONL |
| `save(path)` | Save to file |
| `load(path)` | Load from file |

`to_ison()`/`to_isonl()` output is canonical (sorted, insertion-order-independent) - see [Canonical Serialization](#canonical-serialization).

### ISONGraphantic

#### Field Types

```python
String().required().min(1).max(100).pattern(r'\w+').email().enum('a', 'b')
Int().required().min(0).max(100).range(0, 100)
Float().required().min(0.0).max(1.0)
Bool().required().default(True)
Ref('node_type').required()
```

#### Node Type

```text
NodeType('name')
    .id(field_type)
    .field('name', field_type)
    .constraint(fn)
```

#### Edge Type

```text
EdgeType('REL_TYPE')
    .from_node(node_type)
    .to_node(node_type)
    .field('name', field_type)
    .no_self_loop()
    .unique()
    .acyclic()
    .bidirectional()
    .cardinality(Cardinality.ONE_TO_MANY)
    .constraint(fn)
```

#### Graph Schema

```text
GraphSchema('name')
    .node_types(Type1, Type2)
    .edge_types(Edge1, Edge2)
    .connected()
    .no_orphans()
    .max_depth(n)
    .constraint(fn)
    .validate(graph) -> ValidationResult
```

### Embeddings (planned — unreleased `ison-graph-embeddings` package)

#### Encoders

```python
SentenceTransformerEncoder(model_name="all-MiniLM-L6-v2")
MockEncoder(dimension=384)  # For testing
```

#### SemanticGraph

```python
SemanticGraph(
    name="graph",
    embedding_db=":memory:",
    encoder=None,
    auto_embed=True,
    embed_fields=['name', 'description']
)

# Methods
graph.embed_node(node_ref, text)
graph.get_embedding(node_ref)
graph.similarity_search(query, top_k, threshold)
graph.semantic_multi_hop(query, rel_type, max_hops, top_k_seeds, decay)
graph.semantic_path(query, target_ref, max_hops)
```

---

## Format Specification

Two sample files ship at the repository root: `sampleX.ison` uses the core-ISON tabular format, while `social.ison` uses the ISONGraph graph format (`nodes.*` / `edges.*` blocks) described below.

### ISON Graph Format

```
nodes.<type>
<field1> <field2> <field3> ...
<value1> <value2> <value3> ...
<value1> <value2> <value3> ...

edges.<REL_TYPE>
source target <field1> <field2> ...
:<type>:<id> :<type>:<id> <value1> <value2> ...
```

### Reference Syntax

- Node references: `:<type>:<id>` (e.g., `:person:1`, `:company:100`)
- Supports any serializable ID type (int, string, UUID)

### Value Types

| Type | Example |
|------|---------|
| String | `Alice` or `"Alice Smith"` (quoted if spaces) |
| Integer | `42` |
| Float | `3.14` |
| Boolean | `true` / `false` |
| Null | `~` or `null` |

ISON scalars stop there. A value like `[1,2,3]` is legal but carries no
structure - it parses back as the string `[1,2,3]`, not as a list. Nest by
adding a block and referencing it, not by embedding a literal.

### ISONL (Streaming Format)

```
edges.KNOWS|since source target|2020 :person:1 :person:2
nodes.person|id age name|1 30 Alice
nodes.person|id age name|2 25 Bob
```

### Canonical Serialization

`to_ison()` / `to_isonl()` output is **canonical**: node type blocks, node
rows within a block, edge type blocks, and edge rows within a block are all
sorted (ordinal string comparison), independent of insertion order. The same
logical graph always serializes to the same bytes, regardless of
construction history - two graphs built from the same nodes and edges in a
different order, or rebuilt across separate runs, produce byte-identical
output. This is what makes ISON output safe to content-address or use as an
LLM prompt-cache prefix: appending or reordering how you built the graph in
memory never changes what gets written.

Sort order is ordinal, not numeric - node ids `"1"`, `"2"`, `"10"` serialize
in that order (`"1" < "10" < "2"` as strings), consistently across every
language port. All six implementations (Python, JavaScript, TypeScript,
Rust, C++, C#) are verified byte-identical against a shared golden fixture
in their test suites.

---

## Performance

### Complexity

| Operation | Time Complexity |
|-----------|-----------------|
| Node lookup | O(1) |
| Edge lookup | O(1) |
| Add node | O(1) |
| Add edge | O(1) |
| Neighbors | O(degree) |
| Multi-hop | O(V + E) per hop |
| Shortest path | O(V + E) |
| Has cycle | O(V + E) |

### Memory

- Nodes: ~100 bytes + properties
- Edges: ~80 bytes + properties
- Indexes add ~50% overhead for fast traversal

### Token Efficiency

ISONGraph consistently uses **60-70% fewer tokens** than JSON across all tested datasets, enabling:

- 3x more graph data in the same context window
- Higher accuracy on graph reasoning tasks
- Lower API costs for LLM applications

---

## Examples

### Social Network Analysis

```python
from ison_graph import ISONGraph

graph = ISONGraph()

# Build network
users = ['Alice', 'Bob', 'Carol', 'David', 'Eve']
for i, name in enumerate(users, 1):
    graph.add_node('user', i, name=name)

graph.add_edge('FOLLOWS', ('user', 1), ('user', 2))
graph.add_edge('FOLLOWS', ('user', 2), ('user', 3))
graph.add_edge('FOLLOWS', ('user', 3), ('user', 1))  # Creates cycle

# Analysis
print(f"Has cycle: {graph.has_cycle()}")  # True
print(f"Connected: {graph.is_connected()}")
print(f"Components: {len(graph.connected_components())}")

# Find influencers (highest in-degree)
for user in graph.nodes('user'):
    ref = ('user', user.id)
    print(f"{user.properties['name']}: {graph.in_degree(ref)} followers")
```

### Knowledge Graph for RAG (planned)

> Uses the unreleased `ison-graph-embeddings` package — API preview.

```python
from ison_graph_embeddings import SemanticGraph

graph = SemanticGraph(embedding_db='knowledge.db')

# Add documents with embeddings
graph.add_node('doc', 1,
    title='Python Basics',
    _embed_text='Python is a high-level programming language known for readability'
)
graph.add_node('doc', 2,
    title='Machine Learning',
    _embed_text='ML algorithms learn patterns from data to make predictions'
)
graph.add_node('concept', 'python', name='Python')
graph.add_node('concept', 'ml', name='Machine Learning')

# Link documents to concepts
graph.add_edge('COVERS', ('doc', 1), ('concept', 'python'))
graph.add_edge('COVERS', ('doc', 2), ('concept', 'ml'))
graph.add_edge('USES', ('concept', 'ml'), ('concept', 'python'))

# Semantic search + graph traversal
results = graph.semantic_multi_hop(
    query="How to use Python for AI?",
    rel_type=None,  # Follow any relationship
    max_hops=2,
    top_k_results=5
)

for r in results:
    node = graph.get_node(*r.node_ref)
    print(f"Score: {r.score:.3f} | Hops: {r.hop_count} | {node.properties}")
```

### LLM Context Optimization

```python
from ison_graph import ISONGraph, Direction

# Load your graph
graph = ISONGraph.load('large_graph.ison')

# Get subgraph relevant to query
relevant_nodes = graph.start(('topic', 'ai')) \
    .hop('RELATED_TO', direction=Direction.BOTH) \
    .hops(2, 'CONTAINS') \
    .collect()

# Create focused subgraph for LLM
subgraph = ISONGraph()
for ref in relevant_nodes:
    node = graph.get_node(*ref)
    subgraph.add_node(ref[0], ref[1], **node.properties)

# Serialize for LLM prompt
context = subgraph.to_ison()
prompt = f"""Given this knowledge graph:

{context}

Question: What are the key concepts in AI?
"""
```

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone repository
git clone https://github.com/ISON-format/isongraph.git
cd isongraph

# Python
cd ison-graph
pip install -e ".[dev]"
pytest

# TypeScript
cd ison-graph-ts
npm install
npm test

# Rust
cd ison-graph-rs
cargo test
```

---

## Roadmap

- [ ] GPU-accelerated similarity search
- [ ] Distributed graph support
- [ ] GraphQL interface
- [ ] Neo4j import/export
- [x] Visualization tools (`ison_graph.viz` + VS Code extensions in [vscode-isongraph/](vscode-isongraph/) and [vscode-isongraphviz/](vscode-isongraphviz/))
- [ ] WASM builds for browser

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Links

- **Website**: [graph.ison.dev](https://graph.ison.dev)
- **Documentation**: [graph.ison.dev/docs.html](https://graph.ison.dev/docs.html)
- **ISON Format**: [https://www.ison.dev](https://www.ison.dev)
- **GitHub**: [https://github.com/ISON-format/isongraph](https://github.com/ISON-format/isongraph)

### Benchmarks

- **Knowledge Graph Benchmark**: [benchmark/KnowledgeGraph_Benchmark/](benchmark/KnowledgeGraph_Benchmark/)
  - 100 questions, 10 formats, 7 datasets
  - Comprehensive format comparison
  - [Full Results](benchmark/KnowledgeGraph_Benchmark/BENCHMARK.md)

- **Data Traversal Benchmark**: [benchmark/DataTraversal_Benchmark/](benchmark/DataTraversal_Benchmark/)
  - 50 questions, 5 formats, 4 datasets
  - Multi-hop traversal, path finding, graph analysis
  - [Full Results](benchmark/DataTraversal_Benchmark/BENCHMARK.md)

---

## Author

**Mahesh Vaikri**

---

## Citation

```bibtex
@software{isongraph2025,
  author = {Vaikri, Mahesh},
  title = {ISONGraph: Token-Efficient Property Graph Store for AI},
  year = {2025},
  url = {https://github.com/ISON-format/isongraph}
}
```
