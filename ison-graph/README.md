<p align="center">
  <img src="https://raw.githubusercontent.com/isongraph/isongraph/main/assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ison-graph

[![PyPI](https://img.shields.io/pypi/v/ison-graph.svg)](https://pypi.org/project/ison-graph/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/isongraph/isongraph)

**ISONGraph** - A token-efficient, in-memory property graph store built on ISON format.

No external database required. Designed for LLM context windows and agentic AI workflows.

## Why ISONGraph?

| Challenge | ISONGraph Solution |
|-----------|-------------------|
| Graph databases are heavy | Pure Python, zero dependencies beyond ison-py |
| JSON graphs waste tokens | 70% smaller than JSON-LD |
| Need multi-hop traversal | Built-in N-hop queries |
| Path finding | BFS shortest path, DFS all paths |
| LLM context limits | Token-optimized serialization |

## Installation

```bash
pip install ison-graph
```

## Quick Start

```python
from ison_graph import ISONGraph, Direction

# Create a graph
graph = ISONGraph(name="social")

# Add nodes with properties
graph.add_node('person', 1, name='Alice', age=30)
graph.add_node('person', 2, name='Bob', age=25)
graph.add_node('person', 3, name='Charlie', age=35)
graph.add_node('company', 100, name='Acme', industry='tech')

# Add edges (relationships)
graph.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)
graph.add_edge('KNOWS', ('person', 2), ('person', 3), since=2021)
graph.add_edge('WORKS_AT', ('person', 1), ('company', 100), role='Engineer')

# Traverse: direct neighbors
friends = graph.neighbors(('person', 1), 'KNOWS')
# [('person', 2)]

# Multi-hop: friends of friends (2 hops)
fof = graph.multi_hop(('person', 1), 'KNOWS', hops=2)
# [('person', 3)]

# Path finding
path = graph.shortest_path(('person', 1), ('person', 3))
print(path)  # Path(:person:1 -> :person:2 -> :person:3)

# Save to file
graph.save('social.isong')
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              ISONGraph                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Data Model (Property Graph)                                            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │      Node        │    │      Edge        │    │      Path        │   │
│  │  - type: str     │    │  - rel_type: str │    │  - nodes: []     │   │
│  │  - id: int|str   │    │  - source: ref   │    │  - edges: []     │   │
│  │  - properties:{} │    │  - target: ref   │    │  - length        │   │
│  │  - ref: (t, id)  │    │  - properties:{} │    │  - start, end    │   │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘   │
│                                                                         │
│  In-Memory Storage (O(1) Lookup)                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ _nodes:     Dict[type, Dict[id, Node]]     Node lookup          │    │
│  │ _edges:     Dict[rel_type, List[Edge]]     Edges by type        │    │
│  │ _out_edges: Dict[NodeRef, List[Edge]]      Outgoing index       │    │
│  │ _in_edges:  Dict[NodeRef, List[Edge]]      Incoming index       │    │
│  │ _edge_set:  Set[EdgeKey]                   Uniqueness check     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Operations                                                             │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────────────────┐   │
│  │ CRUD           │ │ Traversal      │ │ Path Finding               │   │
│  │ - add_node     │ │ - neighbors    │ │ - shortest_path (BFS)      │   │
│  │ - get_node     │ │ - multi_hop    │ │ - all_paths (DFS)          │   │
│  │ - add_edge     │ │ - multi_hop_rng│ │ - path_exists              │   │
│  │ - remove_*     │ │ - traverse     │ │                            │   │
│  └────────────────┘ └────────────────┘ └────────────────────────────┘   │
│                                                                         │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────────────────┐   │
│  │ Analysis       │ │ Query APIs     │ │ Persistence                │   │
│  │ - is_connected │ │ - query()      │ │ - to_ison() / from_ison()  │   │
│  │ - has_cycle    │ │ - start().hop()│ │ - to_isonl() / from_isonl()│   │
│  │ - components   │ │   .filter()    │ │ - save() / load()          │   │
│  │ - degree       │ │   .collect()   │ │                            │   │
│  └────────────────┘ └────────────────┘ └────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## ISON Graph Format

ISONGraph serializes to a compact, human-readable format:

```
nodes.person
id name age
1 Alice 30
2 Bob 25
3 Charlie 35

nodes.company
id name industry
100 Acme tech

edges.KNOWS
source target since
:person:1 :person:2 2020
:person:2 :person:3 2021

edges.WORKS_AT
source target role
:person:1 :company:100 Engineer
```

**Key syntax:**
- `nodes.{type}` - Node block header
- `edges.{REL_TYPE}` - Edge block header
- `:type:id` - Node reference (used in edges)
- Whitespace-separated values

## Core Concepts

### Node References

Nodes are uniquely identified by a `(type, id)` tuple:

```python
NodeRef = Tuple[str, Union[int, str]]

# Examples
('person', 1)       # Person with ID 1
('company', 100)    # Company with ID 100
('article', 'abc')  # Article with string ID
```

### Direction

Edges can be traversed in three directions:

```python
from ison_graph import Direction

Direction.OUT   # Follow edge from source to target (default)
Direction.IN    # Follow edge from target to source
Direction.BOTH  # Follow both directions
```

## Node Operations

```python
# Create node with properties
node = graph.add_node('person', 1,
    name='Alice',
    age=30,
    email='alice@example.com'
)

# Get node
node = graph.get_node('person', 1)
print(node.type)        # 'person'
print(node.id)          # 1
print(node.properties)  # {'name': 'Alice', 'age': 30, ...}
print(node.ref)         # ('person', 1)

# Update properties (merges with existing)
graph.update_node('person', 1, age=31, title='Senior Engineer')

# Check existence
if graph.has_node('person', 1):
    ...

# Remove node (also removes all connected edges)
graph.remove_node('person', 1)

# Iterate all nodes
for node in graph.nodes():
    print(node)

# Iterate nodes of specific type
for node in graph.nodes('person'):
    print(f"{node.properties['name']}: {node.properties.get('age')}")

# Count nodes
total = graph.node_count()           # All nodes
people = graph.node_count('person')  # Just people

# Get all node types
types = graph.node_types()  # ['person', 'company', ...]
```

## Edge Operations

```python
# Create edge with properties
edge = graph.add_edge('KNOWS',
    ('person', 1),      # source
    ('person', 2),      # target
    since=2020,
    strength=0.9
)

# Get edge
edge = graph.get_edge('KNOWS', ('person', 1), ('person', 2))
print(edge.rel_type)    # 'KNOWS'
print(edge.source)      # ('person', 1)
print(edge.target)      # ('person', 2)
print(edge.properties)  # {'since': 2020, 'strength': 0.9}

# Check existence
if graph.has_edge('KNOWS', ('person', 1), ('person', 2)):
    ...

# Remove edge
graph.remove_edge('KNOWS', ('person', 1), ('person', 2))

# Iterate edges
for edge in graph.edges():           # All edges
    print(edge)

for edge in graph.edges('KNOWS'):    # By relationship type
    print(f"{edge.source} knows {edge.target}")

for edge in graph.edges(source=('person', 1)):  # By source
    print(f"From person 1: {edge}")

# Count edges
total = graph.edge_count()
knows_count = graph.edge_count('KNOWS')

# Get all relationship types
rel_types = graph.edge_types()  # ['KNOWS', 'WORKS_AT', ...]
```

ISONGraph is a **simple graph**: `add_edge` raises `DuplicateEdgeError` on a
repeated `(rel_type, source, target)` triple - parallel edges aren't
representable, by design (it's what keeps canonical serialization
tie-break-free). Converting from a multigraph source? Dedupe/merge in the
converter before calling `add_edge`.

## Traversal Operations

### Neighbors (1-hop)

```python
# Outgoing neighbors (default)
friends = graph.neighbors(('person', 1), 'KNOWS')
# [('person', 2)]

# Incoming neighbors
followers = graph.neighbors(('person', 1), 'KNOWS', Direction.IN)

# Both directions
connections = graph.neighbors(('person', 1), 'KNOWS', Direction.BOTH)

# Any relationship type
all_neighbors = graph.neighbors(('person', 1))
```

### Multi-Hop Traversal

```python
# Exactly N hops away
two_hops = graph.multi_hop(('person', 1), 'KNOWS', hops=2)
three_hops = graph.multi_hop(('person', 1), 'KNOWS', hops=3)

# Range of hops (1 to 3 inclusive)
reachable = graph.multi_hop_range(('person', 1), 'KNOWS',
    min_hops=1,
    max_hops=3
)

# Any relationship type
all_reachable = graph.multi_hop(('person', 1), hops=2)

# Traverse incoming edges
predecessors = graph.multi_hop(('person', 5), 'KNOWS', hops=2,
    direction=Direction.IN
)
```

### Pattern Traversal

Follow a sequence of relationship types:

```python
# "Find companies where Alice's friends work"
# Pattern: person:1 -[:KNOWS]-> person -[:WORKS_AT]-> company
companies = graph.traverse(
    ('person', 1),
    [('KNOWS', Direction.OUT), ('WORKS_AT', Direction.OUT)]
)

# With filter function
# "Find friends over 25 who work at tech companies"
tech_companies = graph.traverse(
    ('person', 1),
    [('KNOWS', Direction.OUT), ('WORKS_AT', Direction.OUT)],
    filter_fn=lambda node: node.properties.get('industry') == 'tech'
)
```

## Path Finding

### Shortest Path (BFS)

```python
path = graph.shortest_path(('person', 1), ('person', 5))

if path:
    print(f"Length: {path.length}")      # Number of hops
    print(f"Start: {path.start}")        # First node
    print(f"End: {path.end}")            # Last node
    print(f"Nodes: {path.nodes}")        # All nodes in path
    print(f"Edges: {path.edges}")        # All edges in path
    print(path)  # Path(:person:1 -> :person:2 -> ... -> :person:5)

# With constraints
path = graph.shortest_path(
    ('person', 1),
    ('person', 5),
    rel_type='KNOWS',     # Only follow KNOWS edges
    max_hops=10,          # Maximum path length
    direction=Direction.OUT
)
```

### All Paths (DFS)

```python
# Find all possible paths
paths = graph.all_paths(('person', 1), ('person', 5))

for path in paths:
    print(f"Path of length {path.length}: {path}")

# With constraints
paths = graph.all_paths(
    ('person', 1),
    ('person', 5),
    rel_type='KNOWS',
    max_hops=5
)
```

### Path Existence

```python
if graph.path_exists(('person', 1), ('person', 5)):
    print("Path exists!")
```

## Fluent API

Chain traversal operations for readable queries:

```python
# Find friends of friends who are over 30
result = graph.start(('person', 1)) \
    .hop('KNOWS') \
    .hop('KNOWS') \
    .filter(lambda n: n.properties.get('age', 0) > 30) \
    .collect()

# Multiple hops at once
distant = graph.start(('person', 1)) \
    .hops(3, 'KNOWS') \
    .collect()

# Get Node objects instead of references
nodes = graph.start(('person', 1)) \
    .hop('KNOWS') \
    .collect_nodes()

for node in nodes:
    print(node.properties['name'])

# Count results
count = graph.start(('person', 1)) \
    .hop('KNOWS') \
    .count()

# Get first result
first = graph.start(('person', 1)) \
    .hop('KNOWS') \
    .first()

# Chain with direction control
result = graph.start(('person', 5)) \
    .hop('KNOWS', direction=Direction.IN) \
    .hop('WORKS_AT') \
    .collect()
```

## Query Pattern Syntax

Execute queries using a pattern string:

```python
# Direct neighbors
graph.query(":person:1 -[:KNOWS]-> *")
# Returns: [('person', 2), ('person', 3)]

# Exactly 2 hops
graph.query(":person:1 -[:KNOWS*2]-> *")
# Returns: nodes exactly 2 hops away

# Range: 1 to 3 hops
graph.query(":person:1 -[:KNOWS*1..3]-> *")
# Returns: all nodes within 1-3 hops
```

**Pattern syntax:**
- `:type:id` - Starting node reference
- `-[:REL]->` - Relationship type
- `-[:REL*N]->` - Exactly N hops
- `-[:REL*M..N]->` - M to N hops (range)
- `*` - Match any node

## Graph Analysis

### Connectivity

```python
# Check if all nodes are reachable from any node
if graph.is_connected():
    print("Graph is connected!")

# Get connected components
components = graph.connected_components()
print(f"Found {len(components)} components")

for i, component in enumerate(components):
    print(f"Component {i}: {len(component)} nodes")
```

### Cycle Detection

```python
# Check for any cycles
if graph.has_cycle():
    print("Graph contains cycles (not a DAG)")

# Check for cycles via specific relationship
if graph.has_cycle('REPORTS_TO'):
    print("Org chart has cycles! (invalid)")
```

### Node Degree

```python
# Incoming edges
in_deg = graph.in_degree(('person', 1))

# Outgoing edges
out_deg = graph.out_degree(('person', 1))

# Total degree
total_deg = graph.degree(('person', 1))
```

## Persistence

### Save and Load

```python
# Save to ISON format (default)
graph.save('graph.isong')

# Load from file
graph = ISONGraph.load('graph.isong')

# Save to ISONL streaming format
graph.save('graph.isonl')
graph = ISONGraph.load('graph.isonl')

# Auto-detect format from extension
graph.save('data.isong')   # Uses ISON
graph.save('data.isonl')   # Uses ISONL
```

### Manual Serialization

```python
# To string
ison_str = graph.to_ison()
isonl_str = graph.to_isonl()

# From string
graph = ISONGraph.from_ison(ison_str)
graph = ISONGraph.from_isonl(isonl_str)
graph = ISONGraph.parse(ison_str)  # Alias for from_ison
```

## Directed vs Undirected Graphs

```python
# Directed graph (default)
directed = ISONGraph(name="social", directed=True)

# Undirected graph - edges work both ways
undirected = ISONGraph(name="network", directed=False)

# In undirected graphs, adding A->B also adds B->A
undirected.add_edge('CONNECTED', ('node', 1), ('node', 2))
# Now both directions exist
```

## Error Handling

```python
from ison_graph import (
    GraphError,
    NodeNotFoundError,
    EdgeNotFoundError,
    DuplicateNodeError,
    DuplicateEdgeError
)

# Handle node not found
try:
    node = graph.get_node('person', 999)
except NodeNotFoundError as e:
    print(f"Node not found: {e.node_ref}")

# Handle duplicate node
try:
    graph.add_node('person', 1, name='Alice')
    graph.add_node('person', 1, name='Duplicate')  # Raises
except DuplicateNodeError as e:
    print(f"Node already exists: {e.node_ref}")

# Handle edge errors
try:
    graph.add_edge('KNOWS', ('person', 1), ('person', 999))  # Target missing
except NodeNotFoundError:
    print("Cannot create edge: target node missing")
```

## Complete API Reference

### ISONGraph Class

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | "graph" | Graph name (used in serialization) |
| `directed` | bool | True | Whether edges are directed |

#### Node Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add_node(type, id, **props)` | Node | Add node with properties |
| `get_node(type, id)` | Node | Get node (raises if not found) |
| `get_node_by_ref(ref)` | Node | Get node by (type, id) tuple |
| `has_node(type, id)` | bool | Check if node exists |
| `remove_node(type, id)` | None | Remove node and its edges |
| `update_node(type, id, **props)` | Node | Update node properties |
| `nodes(type=None)` | Iterator | Iterate nodes |
| `node_count(type=None)` | int | Count nodes |
| `node_types()` | List[str] | Get all node types |

#### Edge Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add_edge(rel, src, tgt, **props)` | Edge | Add edge with properties |
| `get_edge(rel, src, tgt)` | Edge | Get edge (raises if not found) |
| `has_edge(rel, src, tgt)` | bool | Check if edge exists |
| `remove_edge(rel, src, tgt)` | None | Remove edge |
| `edges(rel=None, src=None, tgt=None)` | Iterator | Iterate edges |
| `edge_count(rel=None)` | int | Count edges |
| `edge_types()` | List[str] | Get all relationship types |

#### Traversal Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `neighbors(ref, rel, dir)` | List[NodeRef] | Get 1-hop neighbors |
| `multi_hop(ref, rel, hops, dir)` | List[NodeRef] | Get N-hop neighbors |
| `multi_hop_range(ref, rel, min, max, dir)` | List[NodeRef] | Get range of hops |
| `traverse(ref, pattern, filter)` | List[NodeRef] | Follow pattern |

#### Path Finding Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `shortest_path(start, end, rel, max, dir)` | Path | BFS shortest path |
| `all_paths(start, end, rel, max, dir)` | List[Path] | DFS all paths |
| `path_exists(start, end, rel, max)` | bool | Check if path exists |

#### Analysis Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `in_degree(ref)` | int | Count incoming edges |
| `out_degree(ref)` | int | Count outgoing edges |
| `degree(ref)` | int | Total edge count |
| `is_connected()` | bool | Check if graph is connected |
| `has_cycle(rel=None)` | bool | Check for cycles |
| `connected_components()` | List[Set] | Get connected components |

#### Persistence Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `save(path, format='auto')` | None | Save to file |
| `load(path, format='auto')` | ISONGraph | Load from file (classmethod) |
| `to_ison()` | str | Serialize to ISON |
| `to_isonl()` | str | Serialize to ISONL |
| `from_ison(text, name)` | ISONGraph | Parse ISON (classmethod) |
| `from_isonl(text, name)` | ISONGraph | Parse ISONL (classmethod) |
| `parse(text, name)` | ISONGraph | Alias for from_ison |

`to_ison()`/`to_isonl()` are canonical: node type blocks, node rows, edge
type blocks, and edge rows are all sorted (ordinal string comparison), so
the same logical graph always serializes to the same bytes regardless of
insertion order - safe for content-addressing or prompt caching. Sort order
is ordinal, not numeric (`"1" < "10" < "2"`), and matches every other
ISONGraph language port byte-for-byte.

#### Query Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `start(ref)` | GraphTraversal | Start fluent traversal |
| `query(pattern)` | List[NodeRef] | Execute pattern query |

### GraphTraversal Class

| Method | Returns | Description |
|--------|---------|-------------|
| `hop(rel, dir, where)` | self | Traverse one hop |
| `hops(n, rel, dir)` | self | Traverse N hops |
| `filter(fn)` | self | Filter current nodes |
| `collect()` | List[NodeRef] | Get current node refs |
| `collect_nodes()` | List[Node] | Get current Node objects |
| `count()` | int | Count current nodes |
| `first()` | NodeRef | Get first node or None |

### Data Classes

#### Node

| Property | Type | Description |
|----------|------|-------------|
| `type` | str | Node type |
| `id` | int\|str | Node ID |
| `properties` | Dict | Node properties |
| `ref` | NodeRef | (type, id) tuple |

#### Edge

| Property | Type | Description |
|----------|------|-------------|
| `rel_type` | str | Relationship type |
| `source` | NodeRef | Source node |
| `target` | NodeRef | Target node |
| `properties` | Dict | Edge properties |
| `key` | EdgeKey | (rel_type, source, target) |

#### Path

| Property | Type | Description |
|----------|------|-------------|
| `nodes` | List[NodeRef] | Nodes in path |
| `edges` | List[Edge] | Edges in path |
| `length` | int | Number of hops |
| `start` | NodeRef | First node |
| `end` | NodeRef | Last node |

## Performance Characteristics

| Operation | Time Complexity | Notes |
|-----------|-----------------|-------|
| `add_node` | O(1) | Hash table insert |
| `get_node` | O(1) | Hash table lookup |
| `add_edge` | O(1) | With index update |
| `has_edge` | O(1) | Set lookup |
| `neighbors` | O(degree) | Iterate edge list |
| `multi_hop(N)` | O(V + E) per hop | BFS traversal |
| `shortest_path` | O(V + E) | BFS |
| `all_paths` | O(V!) worst | DFS with backtracking |
| `is_connected` | O(V + E) | BFS from any node |
| `has_cycle` | O(V + E) | DFS with recursion stack |

## Token Efficiency

### Benchmark Results (50 Graph Questions)

| Format | Tokens | Accuracy | Acc/1K Tokens |
|--------|--------|----------|---------------|
| **ISONGraph** | 639 | 92.0% | **143.97** |
| ISON | 685 | 88.0% | 128.47 |
| TOON | 856 | 80.0% | 93.46 |
| JSON Compact | 1,072 | 82.0% | 76.49 |
| JSON | 2,039 | 84.0% | 41.20 |

**ISONGraph provides 3.5x more value per token than JSON.**

### Format Comparison

```
ISONGraph (34 tokens)              JSON-LD (120+ tokens)
─────────────────────              ─────────────────────
nodes.person                       {"@context": {...},
id name age                         "nodes": [
1 Alice 30                            {"@type": "Person",
2 Bob 25                               "@id": "person/1",
                                       "name": "Alice",
edges.KNOWS                            "age": 30}, ...
source target                       ],
:person:1 :person:2                 "edges": [...]}
```

## ISONQL Query Language

ISONGraph includes ISONQL, a query language for property graphs:

```python
from ison_graph import ISONGraph
from ison_graph.query import QueryEngine, QueryBuilder

graph = ISONGraph("social")
# ... add nodes and edges ...

engine = QueryEngine(graph)

# Query nodes with conditions
results = engine.execute("NODES person WHERE age > 25")
results = engine.execute("NODES person WHERE name = 'Alice'")
results = engine.execute("NODES company WHERE name STARTS_WITH 'Acme'")

# Query edges
results = engine.execute("EDGES KNOWS WHERE since > 2020")

# Traverse relationships
results = engine.execute("TRAVERSE person:1 -> KNOWS -> person")

# Multi-hop traversal (up to 2 hops)
results = engine.execute("TRAVERSE person:1 -> KNOWS -> person MAX 2")

# Deeper traversal (up to 3 hops)
results = engine.execute("TRAVERSE person:1 -> KNOWS -> person MAX 3")

# Find paths
results = engine.execute("PATH person:1 TO person:5 VIA KNOWS MAX 5")

# Aggregations
results = engine.execute("COUNT person WHERE age > 25")
results = engine.execute("AVG person.age")
results = engine.execute("SUM person.age WHERE city = 'NYC'")
results = engine.execute("MIN person.age")
results = engine.execute("MAX person.age")
```

### Fluent Query Builder

```python
# Node queries: start from engine.match()
result = (engine.match("person")
    .where("age", ">", 25)
    .where("city", "=", "NYC")
    .order_by("name", "DESC")
    .limit(10)
    .return_fields("name", "email")
    .execute())

# Edge queries: start from engine.match_edges()
result = (engine.match_edges("KNOWS")
    .where("since", ">=", 2020)
    .execute())

# Traversals and paths use the string query form
result = engine.execute("TRAVERSE person:1 -> KNOWS -> person MAX 2")
```

### ISONQL Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Equals | `WHERE name = 'Alice'` |
| `!=` | Not equals | `WHERE status != 'inactive'` |
| `>` | Greater than | `WHERE age > 25` |
| `>=` | Greater or equal | `WHERE age >= 18` |
| `<` | Less than | `WHERE price < 100` |
| `<=` | Less or equal | `WHERE count <= 10` |
| `IN` | In list | `WHERE city IN ('NYC', 'LA')` |
| `NOT IN` | Not in list | `WHERE city NOT IN ('NYC')` |
| `CONTAINS` | List contains | `WHERE tags CONTAINS 'tech'` |
| `STARTS_WITH` | Prefix match | `WHERE name STARTS_WITH 'A'` |
| `ENDS_WITH` | Suffix match | `WHERE email ENDS_WITH '.com'` |
| `MATCHES` | Regex match | `WHERE email MATCHES '^[a-z]+'` |
| `EXISTS` | Field present | `WHERE email EXISTS` |

## Schema Validation

Define and validate graph schemas:

```python
from ison_graph.schema import (
    GraphSchema, NodeType, EdgeType,
    String, Int, Float, Bool, Ref,
    Cardinality
)

# Define node types
Person = NodeType("person") \
    .id(Int()) \
    .field("name", String().required().max(100)) \
    .field("age", Int().min(0).max(150)) \
    .field("email", String().email())

Company = NodeType("company") \
    .id(Int()) \
    .field("name", String().required()) \
    .field("founded", Int().min(1800))

# Define edge types
Knows = EdgeType("KNOWS") \
    .from_node(Person) \
    .to_node(Person) \
    .field("since", Int()) \
    .no_self_loop() \
    .unique()

WorksAt = EdgeType("WORKS_AT") \
    .from_node(Person) \
    .to_node(Company) \
    .field("role", String()) \
    .cardinality(Cardinality.MANY_TO_ONE)

# Create schema
schema = GraphSchema("social") \
    .node_types(Person, Company) \
    .edge_types(Knows, WorksAt) \
    .no_orphans()

# Validate graph
result = schema.validate(graph)

if not result.valid:
    for error in result.errors:
        print(f"[{error.location}] {error.code}: {error.message}")
```

### Field Validators

```python
# String fields
String().required()              # Required field
String().min(5).max(100)         # Length constraints
String().pattern(r"^[A-Z]")      # Regex pattern
String().email()                 # Email validation
String().enum("active", "inactive")  # Enum values

# Numeric fields
Int().required().min(0).max(150)
Float().range(0.0, 100.0)

# Boolean fields
Bool().required()

# Reference fields
Ref("person")                    # Reference to person node
```

### Cardinality Constraints

```python
from ison_graph.schema import Cardinality

# One person can work at one company (many employees per company)
EdgeType("WORKS_AT").cardinality(Cardinality.MANY_TO_ONE)

# One company has one CEO
EdgeType("CEO_OF").cardinality(Cardinality.ONE_TO_ONE)

# One manager can manage many employees
EdgeType("MANAGES").cardinality(Cardinality.ONE_TO_MANY)

# Many people can know many people
EdgeType("KNOWS").cardinality(Cardinality.MANY_TO_MANY)
```

### Graph-Level Constraints

```python
schema = GraphSchema("social") \
    .node_types(Person, Company) \
    .edge_types(Knows, WorksAt) \
    .connected()      # Require graph to be connected
    .no_orphans()     # All nodes must have at least one edge
```

## Extensions (experimental, 1.3.0)

Two opt-in modules that lift constraints of the core graph. Importing them
changes nothing about `ISONGraph` itself — existing code is unaffected.

> **Experimental.** Both are Python-only until the JS, TS, Rust, C++ and C#
> ports implement the same on-disk format. Pin your version if you depend on
> the serialized output.

### MultiGraph — parallel edges

`ISONGraph` is a simple graph: at most one edge per
`(rel_type, source, target)`. `MultiGraph` widens that to
`(rel_type, source, target, key)`, so the same relationship can be recorded
more than once between the same pair — different time ranges, different
provenance — without inventing synthetic relation types.

```python
from ison_graph.multigraph import MultiGraph

mg = MultiGraph()
mg.add_node('person', 1, name='Alice')
mg.add_node('person', 2, name='Bob')

mg.add_edge('KNOWS', ('person', 1), ('person', 2), since=2015)   # key=0
mg.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)   # key=1

mg.neighbors(('person', 1), 'KNOWS')                  # queried by real rel_type
mg.edges_between(('person', 1), ('person', 2))        # [(0, edge), (1, edge)]
mg.get_edge('KNOWS', ('person', 1), ('person', 2), key=1)
mg.remove_edge('KNOWS', ('person', 1), ('person', 2), key=0)
```

- `key` defaults to `0`, so a single edge looks exactly like the simple-graph
  case. Omit it and keys are handed out in order.
- Relation types are stored verbatim — no `r_<encoded>_0` rewriting. "Verbatim"
  means within the identifier rules below; it is not a promise that any string
  is accepted.
- `edges()` and `edges_between()` iterate in **insertion order**; serialized
  output is canonically sorted.
- Keys are monotonic. Removing one edge does not free its key; removing every
  edge on a triple resets the counter to 0.

Serialized output carries a `meta.graph` marker. `ISONGraph` refuses to load
it rather than silently discarding the parallel edges:

```python
ISONGraph.from_ison(mg.to_ison())
# ValueError: This is a ison-graph-multigraph-v1 document ...
#             load it with ison_graph.multigraph.MultiGraph instead.
```

Emission is delegated to ison-py's canonical writer (ISONCS), so MultiGraph
decides *ordering* and the ISON layer decides *bytes*. Column order is
alphabetical and blocks are name-sorted — that is the canonical layout, not a
MultiGraph choice.

### ProtectedGraph — structural fields cannot be shadowed

A node's identity is `(type, id)`; an edge's is
`(rel_type, source, target[, key])`. In a plain `ISONGraph` a property of the
same name rides along and wins on reload:

```python
g = ISONGraph()
g.add_node('person', 1, type='villain')
ISONGraph.from_dict(g.to_dict()).node_types()   # ['villain'] — identity lost
```

`ProtectedGraph` rejects those properties at every boundary and hands out
read-only property views, so the only route to a change is a validating
update method:

```python
from ison_graph.structural import ProtectedGraph

g = ProtectedGraph()
g.add_node('person', 1, name='Alice')

g.add_node('person', 2, type='villain')     # ReservedFieldError
g.get_node('person', 1).properties['name'] = 'Mallory'   # TypeError

g.update_node_properties(('person', 1), name='Alice Q')  # OK
g.update_edge_properties('KNOWS', ('person', 1), ('person', 2), since=2016)
```

Reserved names are `type`/`id` on nodes and
`rel_type`/`source`/`target`/`key` on edges.

### Combining both

```python
from ison_graph.multigraph import MultiGraph
from ison_graph.structural import ProtectedGraph

class SafeMultiGraph(ProtectedGraph, MultiGraph):
    """Parallel edges plus a round-trip-safe identity."""

g = SafeMultiGraph()
```

Overhead versus core `ISONGraph` on 2,000 nodes / 10,000 edges: build ~1.5×
(MultiGraph), ~1.6× (ProtectedGraph), ~2× combined. `to_ison()` is ~3.5× on
MultiGraph, the cost of routing emission through the canonical writer.
Traversal is unaffected.

### Identifier constraints

Node types, node ids and relation types may not contain `:` or `|`:

```python
graph.add_node('person', 'user:1')          # InvalidIdentifierError
graph.add_edge('knows:strong', src, dst)    # InvalidIdentifierError
```

Both characters are structurally significant to the wire format — `:` delimits
`:type:id` references and `|` delimits ISONL columns — so this is deliberate
format policy shared by every ISONGraph port, not a Python-side check. It
applies to `MultiGraph` and `ProtectedGraph` equally.

If your source data uses such values, project them at your boundary rather than
expecting the graph to accept them: keep the original values as your source of
truth, map them to graph-safe references for execution, and translate back on
the way out. Keep the mapping reversible and keep the raw `ISONGraph` object
private — direct queries against it are only meaningful for graph-safe values.

Escaping these characters in the format itself would be a coordinated change
across all six ports, so it is not something a single consumer should work
around locally.

## Visualization

`ison_graph.viz` turns a graph into a picture in three stages — data, layout,
rendering — with zero extra dependencies:

```python
from ison_graph import ISONGraph
from ison_graph.viz import compute_layout, render_svg, render_html

graph = ISONGraph.load("social.ison")

# Stage 2: deterministic seeded force-directed layout -> {(type, id): (x, y)}
layout = compute_layout(graph, width=900, height=600, seed=42)

# Stage 3: render the same coordinates to SVG or interactive HTML
svg = render_svg(graph, layout, title="My graph")          # standalone image
html = render_html(graph, layout)                          # tooltips, pan/zoom, dark mode
```

The same seed always produces the same coordinates, so a server-rendered SVG
and a client-rendered page stay pixel-identical. Nodes are colored by type
(colorblind-safe palette, max 8 types before folding to a neutral), sized by
degree, and labeled from the `name` property (or `label_property=` of your
choice).

Pass ``radii={ref: radius}`` (and optionally ``spacing=2.6``) to enforce
minimum center distance ``(r_a + r_b) * spacing`` between every pair - useful
when node size encodes data and large bubbles must not overlap. Without
``radii`` the output is byte-identical to earlier releases.

The same API ships in the npm packages (`import { viz } from 'ison-graph-ts'`
or `'ison-graph-js'`) with bit-identical layout geometry, verified by
cross-language parity tests.

Command line:

```bash
python -m ison_graph.viz social.ison -o graph.svg
python -m ison_graph.viz social.ison -o graph.html --edge-labels --title "Social"
```

## Integration with ISON Ecosystem

```
┌────────────────────────────────────────────────────────────────────┐
│                        ISON Ecosystem                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ison-py          →  Core parser (loads, dumps)                    │
│       ↓                                                            │
│  ison-graph       →  Property graph store (nodes, edges, paths)    │
│       ↓                                                            │
│  isongraphantic   →  Graph schema validation (constraints)         │
│       ↓                                                            │
│  ison-graph-embeddings → Semantic search + graph traversal         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Related Packages

| Package | Purpose |
|---------|---------|
| `ison-py` | Core ISON parser |
| `isonantic` | Data validation for ISON |
| `isongraphantic` | Graph schema validation |
| `ison-graph-embeddings` | Semantic search + embeddings |

## Use Cases

### Knowledge Graphs

```python
graph = ISONGraph(name="knowledge")
graph.add_node('company', 'apple', name='Apple', industry='tech')
graph.add_node('person', 'tim', name='Tim Cook', role='CEO')
graph.add_node('product', 'iphone', name='iPhone')

graph.add_edge('WORKS_AT', ('person', 'tim'), ('company', 'apple'))
graph.add_edge('PRODUCES', ('company', 'apple'), ('product', 'iphone'))

# Query: What products does Tim Cook's company make?
products = graph.traverse(
    ('person', 'tim'),
    [('WORKS_AT', Direction.OUT), ('PRODUCES', Direction.OUT)]
)
```

### Social Networks

```python
graph = ISONGraph(name="social")
# Add users and follow relationships
# Multi-hop: friends of friends
fof = graph.multi_hop(('user', 1), 'FOLLOWS', hops=2)
```

### Org Charts

```python
graph = ISONGraph(name="org")
# REPORTS_TO edges form a DAG
if graph.has_cycle('REPORTS_TO'):
    raise ValueError("Invalid org structure!")
```

### Dependency Graphs

```python
graph = ISONGraph(name="deps")
# Package dependency resolution
path = graph.shortest_path(('pkg', 'app'), ('pkg', 'lodash'))
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=ison_graph --cov-report=term-missing
```

## License

MIT License - see [LICENSE](https://github.com/isongraph/isongraph/blob/main/LICENSE) for details.

## Author

**Mahesh Vaikri**
- Website: [graph.ison.dev](https://graph.ison.dev)
- Documentation: [graph.ison.dev/docs.html](https://graph.ison.dev/docs.html)
- GitHub: [@maheshvaikri-code](https://github.com/maheshvaikri-code)
