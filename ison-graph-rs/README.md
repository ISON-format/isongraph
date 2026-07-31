<p align="center">
  <img src="../assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ison-graph

[![Crates.io](https://img.shields.io/crates/v/ison-graph.svg)](https://crates.io/crates/ison-graph)
[![Rust](https://img.shields.io/badge/Rust-1.70+-orange.svg)](https://www.rust-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ISONGraph** - A token-efficient property graph store with ISON persistence for Rust.

## Features

- **Property Graph Model**: Nodes and edges with typed properties
- **O(1) Lookups**: Fast node access by (type, id)
- **Multi-Hop Traversal**: 1-hop, N-hop, and range queries
- **Path Finding**: BFS shortest path
- **ISONQL Query Language**: Declarative graph queries
- **Schema Validation**: Type-safe graph constraints
- **ISON Persistence**: Token-efficient serialization
- **Zero Dependencies**: Only thiserror and regex

## Installation

```toml
[dependencies]
ison-graph = "1.0.0"
```

## Quick Start

```rust
use ison_graph::{ISONGraph, NodeRef, Direction};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Create a graph
    let mut graph = ISONGraph::new("social");

    // Add nodes
    graph.add_node("person", "1", vec![("name", "Alice"), ("age", "30")])?;
    graph.add_node("person", "2", vec![("name", "Bob"), ("age", "25")])?;
    graph.add_node("company", "100", vec![("name", "TechCorp")])?;

    // Add edges
    graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), vec![("since", "2020")])?;
    graph.add_edge("WORKS_AT", ("person", "1"), ("company", "100"), vec![])?;

    // Query neighbors
    let friends = graph.neighbors(&("person", "1"), Some("KNOWS"), Direction::Out);
    println!("Friends: {:?}", friends);

    // Multi-hop traversal
    let fof = graph.multi_hop(&("person", "1"), Some("KNOWS"), 2, Direction::Out);

    // Shortest path
    if let Some(path) = graph.shortest_path(
        &("person", "1"),
        &("person", "3"),
        Some("KNOWS"),
        10,
        Direction::Out
    ) {
        println!("Path length: {}", path.length());
    }

    Ok(())
}
```

## API Reference

### ISONGraph

```rust
let mut graph = ISONGraph::new("name");
let mut graph = ISONGraph::undirected("name");
```

#### Node Operations

| Method | Description |
|--------|-------------|
| `add_node(type, id, props)` | Add a node |
| `get_node(type, id)` | Get a node |
| `has_node(type, id)` | Check if exists |
| `remove_node(type, id)` | Remove node and edges |
| `update_node(type, id, props)` | Update properties |
| `node_count()` | Count all nodes |
| `node_count_of_type(type)` | Count nodes of type |
| `node_types()` | Get all types |
| `nodes()` | Iterate over all nodes |
| `nodes_of_type(type)` | Iterate over nodes of type |

#### Edge Operations

| Method | Description |
|--------|-------------|
| `add_edge(rel, src, tgt, props)` | Add an edge |
| `has_edge(rel, src, tgt)` | Check if exists |
| `remove_edge(rel, src, tgt)` | Remove edge |
| `edge_count()` | Count all edges |
| `edge_count_of_type(type)` | Count edges of type |

ISONGraph is a **simple graph**: `add_edge` returns `Err(GraphError::DuplicateEdge)`
on a repeated `(rel_type, source, target)` triple - parallel edges aren't
representable, by design (it's what keeps canonical serialization
tie-break-free). Converting from a multigraph source? Dedupe/merge in the
converter before calling `add_edge`.
| `edge_types()` | Get all types |
| `edges_of_type(type)` | Iterate over edges of type |

#### Traversal

| Method | Description |
|--------|-------------|
| `neighbors(ref, rel?, dir)` | Get neighbors |
| `multi_hop(start, rel?, hops, dir)` | N-hop traverse |
| `multi_hop_range(start, rel?, min, max, dir)` | Range traverse |

#### Path Finding

| Method | Description |
|--------|-------------|
| `shortest_path(start, end, rel?, max, dir)` | BFS shortest |
| `path_exists(start, end, rel?, max, dir)` | Check reachability |

#### Graph Analysis

| Method | Description |
|--------|-------------|
| `in_degree(ref)` | Count incoming edges |
| `out_degree(ref)` | Count outgoing edges |
| `degree(ref)` | Total degree |
| `is_connected()` | Check connectivity |
| `has_cycle(rel?)` | Detect cycles |

#### Serialization

| Method | Description |
|--------|-------------|
| `to_ison()` | Serialize to ISON |
| `to_isonl()` | Serialize to ISONL |

Output is canonical: node/edge type blocks and rows are sorted (ordinal),
so the same logical graph always serializes to the same bytes regardless
of insertion order - byte-identical with every other ISONGraph language
port.

## Types

```rust
/// Node reference: (type, id)
pub type NodeRef<'a> = (&'a str, &'a str);

/// Owned node reference
pub struct NodeId {
    pub node_type: String,
    pub id: String,
}

/// Traversal direction
pub enum Direction {
    Out,
    In,
    Both,
}
```

## Error Handling

```rust
use ison_graph::GraphError;

match graph.add_node("person", "1", vec![]) {
    Ok(node) => println!("Added: {:?}", node),
    Err(GraphError::DuplicateNode(t, id)) => println!("Already exists: {}:{}", t, id),
    Err(GraphError::NodeNotFound(t, id)) => println!("Not found: {}:{}", t, id),
    Err(e) => println!("Error: {}", e),
}
```

---

## ISONQL Query Language

ISONQL is a declarative query language for ISONGraph, providing a pure property graph query interface without external database dependencies.

### Basic Usage

```rust
use ison_graph::{ISONGraph, query::{QueryEngine, QueryResult, QueryData}};

// Create and populate graph
let mut graph = ISONGraph::new("social");
graph.add_node("person", "alice", vec![("name", "Alice"), ("age", "30"), ("city", "NYC")])?;
graph.add_node("person", "bob", vec![("name", "Bob"), ("age", "25"), ("city", "LA")])?;
graph.add_node("person", "charlie", vec![("name", "Charlie"), ("age", "35"), ("city", "NYC")])?;
graph.add_node("company", "techcorp", vec![("name", "TechCorp"), ("size", "500")])?;
graph.add_edge("KNOWS", ("person", "alice"), ("person", "bob"), vec![("since", "2020")])?;
graph.add_edge("KNOWS", ("person", "bob"), ("person", "charlie"), vec![("since", "2021")])?;
graph.add_edge("WORKS_AT", ("person", "alice"), ("company", "techcorp"), vec![("role", "Engineer")])?;

// Create query engine
let engine = QueryEngine::new(&graph);

// Execute queries
let result = engine.execute("NODES person WHERE age > 25")?;
println!("Found {} people", result.count);
```

### Supported Query Types

#### NODES - Query Nodes

```rust
// All nodes of a type
engine.execute("NODES person")?;

// With WHERE clause
engine.execute("NODES person WHERE age > 25")?;

// Multiple conditions
engine.execute("NODES person WHERE age > 25 AND city = NYC")?;

// OR conditions (AND binds tighter than OR)
engine.execute("NODES person WHERE city = NYC AND age > 30 OR city = LA")?;

// With sorting
engine.execute("NODES person WHERE age > 20 ORDER BY age DESC")?;

// With pagination
engine.execute("NODES person ORDER BY name ASC LIMIT 10 OFFSET 5")?;

// Return specific fields
engine.execute("NODES person WHERE city = NYC RETURN name, age")?;

// Shorthand syntax
engine.execute("NODES person(city=NYC)")?;
```

#### EDGES - Query Edges

```rust
// All edges of a type
engine.execute("EDGES KNOWS")?;

// With WHERE clause on edge properties
engine.execute("EDGES KNOWS WHERE since > 2020")?;

// With limit
engine.execute("EDGES WORKS_AT LIMIT 10")?;
```

#### TRAVERSE - Graph Traversal

```rust
// Single hop outgoing
engine.execute("TRAVERSE person:alice -> KNOWS -> person")?;

// Single hop incoming
engine.execute("TRAVERSE person:bob <- KNOWS <- person")?;

// Multi-hop with max depth
engine.execute("TRAVERSE person:alice -> KNOWS -> person MAX 3")?;

// Undirected traversal
engine.execute("TRAVERSE person:alice -- KNOWS -- person")?;

// Any node type
engine.execute("TRAVERSE person:alice -> WORKS_AT -> *")?;
```

#### PATH - Find Shortest Path

```rust
// Find shortest path between nodes
engine.execute("PATH person:alice TO person:charlie")?;

// Via specific relationship
engine.execute("PATH person:alice TO person:charlie VIA KNOWS")?;

// With max hops
engine.execute("PATH person:alice TO person:charlie VIA KNOWS MAX 5")?;
```

#### COUNT - Count Nodes

```rust
// Count all nodes of a type
engine.execute("COUNT person")?;

// Count with filter
engine.execute("COUNT person WHERE city = NYC")?;
```

#### Aggregations - SUM, AVG, MIN, MAX

```rust
// Sum a property
engine.execute("SUM person.age")?;

// Average with filter
engine.execute("AVG person.age WHERE city = NYC")?;

// Min value
engine.execute("MIN person.age")?;

// Max value
engine.execute("MAX company.size")?;
```

### Query Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `=`, `==` | Equal | `name = Alice` |
| `!=`, `<>` | Not equal | `city != LA` |
| `>` | Greater than | `age > 25` |
| `>=` | Greater or equal | `age >= 25` |
| `<` | Less than | `age < 30` |
| `<=` | Less or equal | `age <= 30` |
| `IN` | In list | `city IN (NYC, LA, SF)` |
| `CONTAINS` | Contains substring | `name CONTAINS ali` |
| `STARTS_WITH` | Starts with | `name STARTS_WITH A` |
| `ENDS_WITH` | Ends with | `name ENDS_WITH e` |
| `MATCHES` | Regex match | `email MATCHES ^[a-z]+@` |
| `EXISTS` | Field exists | `EXISTS email` |
| `NOT EXISTS` | Field missing | `NOT EXISTS phone` |

### Working with Results

```rust
let result = engine.execute("NODES person WHERE age > 25")?;

// Access result metadata
println!("Count: {}", result.count);
println!("Total: {}", result.total_count);
println!("Time: {}ms", result.execution_time_ms);

// Iterate over results
for data in result.iter() {
    match data {
        QueryData::Node { node_type, id, properties } => {
            println!("Node: {}:{}", node_type, id);
            if let Some(name) = properties.get("name") {
                println!("  Name: {}", name);
            }
        }
        QueryData::Edge { rel_type, source, target, properties } => {
            println!("Edge: {} -> {}", source.to_key(), target.to_key());
        }
        QueryData::NodeRef(node_id) => {
            println!("Ref: {}:{}", node_id.node_type, node_id.id);
        }
        QueryData::Path { nodes, edges, length } => {
            println!("Path of {} hops", length);
            for node in nodes {
                println!("  -> {}:{}", node.node_type, node.id);
            }
        }
        QueryData::Count(n) => {
            println!("Count: {}", n);
        }
        QueryData::Aggregate(value) => {
            if let Some(v) = value {
                println!("Value: {}", v);
            }
        }
        QueryData::Fields(props) => {
            for (k, v) in props {
                println!("  {}: {}", k, v);
            }
        }
    }
}
```

### Fluent Query Builder

For programmatic query construction, use the fluent builder API:

```rust
use ison_graph::query::QueryEngine;

let engine = QueryEngine::new(&graph);

// Build and execute query fluently
let result = engine.match_nodes("person")
    .where_num("age", ">", 25)
    .where_cond("city", "=", "NYC")
    .order_by("age", "DESC")
    .limit(10)
    .execute()?;

// Count query
let count = engine.match_nodes("person")
    .where_cond("city", "=", "NYC")
    .count()?;

println!("Found {} people in NYC", count);

// With field selection
let result = engine.match_nodes("person")
    .where_num("age", ">=", 21)
    .return_fields(vec!["name", "age"])
    .offset(5)
    .limit(10)
    .execute()?;
```

---

## Schema Validation

The schema module provides type-safe graph validation with property constraints, relationship rules, and graph-level constraints.

### Basic Usage

```rust
use ison_graph::ISONGraph;
use ison_graph::schema::{
    GraphSchema, NodeType, EdgeType,
    StringField, IntField, FloatField, BoolField,
    Cardinality, ValidationResult,
};

// Define node types
let person = NodeType::new("person")
    .id(IntField::new())
    .field("name", StringField::new().required().max(100))
    .field("age", IntField::new().min(0).max(150))
    .field("email", StringField::new().email());

let company = NodeType::new("company")
    .id(IntField::new())
    .field("name", StringField::new().required());

// Define edge types
let knows = EdgeType::new("KNOWS")
    .from_node("person")
    .to_node("person")
    .no_self_loop()
    .unique();

let works_at = EdgeType::new("WORKS_AT")
    .from_node("person")
    .to_node("company")
    .cardinality(Cardinality::ManyToOne);

// Build schema
let schema = GraphSchema::new("social")
    .node_type(person)
    .node_type(company)
    .edge_type(knows)
    .edge_type(works_at)
    .no_orphans();

// Validate graph
let mut graph = ISONGraph::new("test");
graph.add_node("person", "1", vec![("name", "Alice"), ("age", "30")]).unwrap();
graph.add_node("person", "2", vec![("name", "Bob"), ("age", "25")]).unwrap();
graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), vec![]).unwrap();

let result = schema.validate(&graph);
if result.is_valid() {
    println!("Graph is valid!");
} else {
    for error in result.errors() {
        println!("Error: {}", error);
    }
}
```

### Field Types

#### StringField

```rust
use ison_graph::schema::StringField;

// Basic string field
let field = StringField::new();

// Required field
let field = StringField::new().required();

// Length constraints
let field = StringField::new()
    .min(3)      // Minimum 3 characters
    .max(100);   // Maximum 100 characters

// Pattern matching (regex)
let field = StringField::new()
    .pattern(r"^[A-Z][a-z]+$");  // Must start with capital

// Email validation
let field = StringField::new().email();

// Allowed values (enum)
let field = StringField::new()
    .allowed(vec!["active", "inactive", "pending"]);
```

#### IntField

```rust
use ison_graph::schema::IntField;

// Basic integer field
let field = IntField::new();

// Required
let field = IntField::new().required();

// Range constraints
let field = IntField::new()
    .min(0)
    .max(150);

// Or use range()
let field = IntField::new().range(0, 150);
```

#### FloatField

```rust
use ison_graph::schema::FloatField;

// Basic float field
let field = FloatField::new();

// With constraints
let field = FloatField::new()
    .required()
    .min(0.0)
    .max(100.0);

// Using range
let field = FloatField::new().range(-180.0, 180.0);  // e.g., longitude
```

#### BoolField

```rust
use ison_graph::schema::BoolField;

// Basic boolean field
let field = BoolField::new();

// Required boolean
let field = BoolField::new().required();
```

### Node Type Schema

```rust
use ison_graph::schema::{NodeType, StringField, IntField};

let person = NodeType::new("person")
    // Validate the ID field
    .id(IntField::new())

    // Define property fields
    .field("name", StringField::new().required().max(100))
    .field("age", IntField::new().min(0).max(150))
    .field("email", StringField::new().email())
    .field("status", StringField::new().allowed(vec!["active", "inactive"]));
```

### Edge Type Schema

```rust
use ison_graph::schema::{EdgeType, StringField, IntField, Cardinality};

// Basic edge type
let knows = EdgeType::new("KNOWS")
    .from_node("person")
    .to_node("person");

// With constraints
let works_at = EdgeType::new("WORKS_AT")
    .from_node("person")
    .to_node("company")
    .no_self_loop()      // Cannot connect node to itself
    .unique()            // No duplicate edges
    .cardinality(Cardinality::ManyToOne);  // Many persons, one company per person

// With edge properties
let reports_to = EdgeType::new("REPORTS_TO")
    .from_node("person")
    .to_node("person")
    .no_self_loop()
    .acyclic()           // Must be DAG (no cycles)
    .field("since", IntField::new().required())
    .field("department", StringField::new());

// Bidirectional edges
let friends_with = EdgeType::new("FRIENDS_WITH")
    .from_node("person")
    .to_node("person")
    .no_self_loop()
    .bidirectional();    // If A->B exists, B->A must also exist
```

### Edge Constraints

| Constraint | Method | Description |
|------------|--------|-------------|
| No Self Loop | `.no_self_loop()` | Edge cannot connect node to itself |
| Unique | `.unique()` | No duplicate edges between same pair |
| Acyclic | `.acyclic()` | Must form DAG (no cycles) |
| Bidirectional | `.bidirectional()` | Reverse edge must exist |
| Cardinality | `.cardinality(card)` | Relationship cardinality |

### Cardinality Constraints

```rust
use ison_graph::schema::Cardinality;

// One-to-One: Each source has exactly one target, each target has one source
// Example: person HAS_PASSPORT passport
EdgeType::new("HAS_PASSPORT")
    .cardinality(Cardinality::OneToOne);

// One-to-Many: One source to many targets, each target has one source
// Example: company HAS_DEPARTMENT department
EdgeType::new("HAS_DEPARTMENT")
    .cardinality(Cardinality::OneToMany);

// Many-to-One: Many sources to one target
// Example: person WORKS_AT company (many employees, one company per person)
EdgeType::new("WORKS_AT")
    .cardinality(Cardinality::ManyToOne);

// Many-to-Many: No restrictions (default)
// Example: person KNOWS person
EdgeType::new("KNOWS")
    .cardinality(Cardinality::ManyToMany);
```

### Graph-Level Constraints

```rust
use ison_graph::schema::GraphSchema;

let schema = GraphSchema::new("social")
    .node_type(person)
    .edge_type(knows)

    // Graph must be connected (all nodes reachable)
    .connected()

    // No orphan nodes (all nodes must have at least one edge)
    .no_orphans()

    // Maximum depth constraint
    .max_depth(10);
```

### Validation Results

```rust
let result = schema.validate(&graph);

// Check validity
if result.is_valid() {
    println!("Graph is valid");
}

// Access errors
for error in result.errors() {
    println!("[{}] {}: {}", error.location, error.code, error.message);
}

// Access warnings
for warning in result.warnings() {
    println!("Warning: {}", warning.message);
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `REQUIRED_FIELD` | Required field is missing |
| `INVALID_TYPE` | Value type doesn't match schema |
| `MIN_VALUE` | Value below minimum |
| `MAX_VALUE` | Value above maximum |
| `MIN_LENGTH` | String too short |
| `MAX_LENGTH` | String too long |
| `PATTERN_MISMATCH` | Doesn't match regex pattern |
| `INVALID_EMAIL` | Not a valid email format |
| `INVALID_ENUM` | Value not in allowed list |
| `REF_NOT_FOUND` | Referenced node doesn't exist |
| `REF_WRONG_TYPE` | Referenced node is wrong type |
| `SELF_LOOP` | Self-loop not allowed |
| `DUPLICATE_EDGE` | Duplicate edge (when unique) |
| `CARDINALITY_VIOLATION` | Cardinality constraint violated |
| `INVALID_SOURCE_TYPE` | Edge source is wrong node type |
| `INVALID_TARGET_TYPE` | Edge target is wrong node type |
| `CYCLE_DETECTED` | Cycle found (when acyclic required) |
| `NOT_CONNECTED` | Graph is not connected |
| `ORPHAN_NODE` | Node has no edges |
| `MAX_DEPTH_EXCEEDED` | Graph depth exceeds limit |

### Complete Example

```rust
use ison_graph::ISONGraph;
use ison_graph::schema::{
    GraphSchema, NodeType, EdgeType,
    StringField, IntField, FloatField,
    Cardinality,
};

// Define node types
let user = NodeType::new("user")
    .id(IntField::new())
    .field("username", StringField::new()
        .required()
        .min(3)
        .max(50)
        .pattern(r"^[a-zA-Z0-9_]+$"))
    .field("email", StringField::new().required().email())
    .field("age", IntField::new().min(13).max(150));

let post = NodeType::new("post")
    .id(IntField::new())
    .field("title", StringField::new().required().max(200))
    .field("content", StringField::new().required())
    .field("status", StringField::new()
        .allowed(vec!["draft", "published", "archived"]));

let comment = NodeType::new("comment")
    .id(IntField::new())
    .field("text", StringField::new().required().max(1000));

// Define edge types
let follows = EdgeType::new("FOLLOWS")
    .from_node("user")
    .to_node("user")
    .no_self_loop();

let authored = EdgeType::new("AUTHORED")
    .from_node("user")
    .to_node("post")
    .cardinality(Cardinality::OneToMany);

let commented_on = EdgeType::new("COMMENTED_ON")
    .from_node("comment")
    .to_node("post")
    .cardinality(Cardinality::ManyToOne);

let wrote_comment = EdgeType::new("WROTE_COMMENT")
    .from_node("user")
    .to_node("comment")
    .cardinality(Cardinality::OneToMany);

// Build schema
let schema = GraphSchema::new("blog")
    .node_type(user)
    .node_type(post)
    .node_type(comment)
    .edge_type(follows)
    .edge_type(authored)
    .edge_type(commented_on)
    .edge_type(wrote_comment);

// Create and populate graph
let mut graph = ISONGraph::new("blog");

graph.add_node("user", "1", vec![
    ("username", "alice_dev"),
    ("email", "alice@example.com"),
    ("age", "28"),
]).unwrap();

graph.add_node("user", "2", vec![
    ("username", "bob_coder"),
    ("email", "bob@example.com"),
    ("age", "32"),
]).unwrap();

graph.add_node("post", "101", vec![
    ("title", "Introduction to Rust"),
    ("content", "Rust is a systems programming language..."),
    ("status", "published"),
]).unwrap();

graph.add_edge("AUTHORED", ("user", "1"), ("post", "101"), vec![]).unwrap();
graph.add_edge("FOLLOWS", ("user", "2"), ("user", "1"), vec![]).unwrap();

// Validate
let result = schema.validate(&graph);
if result.is_valid() {
    println!("Blog graph is valid!");
} else {
    for error in result.errors() {
        println!("Validation error: {}", error);
    }
}
```

---

## ISON Format

ISONGraph uses a token-efficient serialization format:

```
nodes.person
id name age
1 Alice 30
2 Bob 25

edges.KNOWS
source target since
:person:1 :person:2 2020
```

### ISONL (Line-Oriented Format)

For streaming/appending:

```
nodes.person|id name|1 Alice
nodes.person|id name age|2 Bob 25
edges.KNOWS|source target since|:person:1 :person:2 2020
```

---

## License

MIT License - see [LICENSE](../LICENSE) for details.
