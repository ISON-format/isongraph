<p align="center">
  <img src="../assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ison-graph-cs

[![.NET](https://img.shields.io/badge/.NET-8.0-blue.svg)](https://dotnet.microsoft.com/)
[![C#](https://img.shields.io/badge/C%23-12-blue.svg)](https://learn.microsoft.com/dotnet/csharp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ISONGraph** - A token-efficient property graph store with ISON persistence for C# / .NET 8.

## Features

- **Property Graph Model**: Nodes and edges with string properties
- **O(1) Lookups**: Fast node access by (type, id)
- **Multi-Hop Traversal**: 1-hop, N-hop, and range queries
- **Path Finding**: BFS shortest path and iterative all-paths DFS
- **ISONQL Query Language**: Declarative graph queries
- **Schema Validation**: Type-safe graph constraints (Graphantic)
- **Deterministic Visualization**: Seeded force layout with bit-identical
  cross-language geometry, SVG and interactive HTML rendering
- **Fluent API**: Chainable traversal and query builders
- **ISON Persistence**: Token-efficient serialization (ISON and ISONL)
- **Zero Dependencies**: Pure .NET base class library

## Installation

```bash
dotnet add package IsonGraph
```

Or build from source:

```bash
dotnet build -c Release
dotnet test
```

## Quick Start

```csharp
using IsonGraph;

// Create a graph
var graph = new ISONGraph("social");

// Add nodes
graph.AddNode("person", "1", new() { ["name"] = "Alice", ["age"] = "30" });
graph.AddNode("person", "2", new() { ["name"] = "Bob", ["age"] = "25" });
graph.AddNode("person", "3", new() { ["name"] = "Charlie", ["age"] = "35" });
graph.AddNode("company", "100", new() { ["name"] = "TechCorp" });

// Add edges
graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"), new() { ["since"] = "2020" });
graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"), new() { ["since"] = "2021" });
graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"), new() { ["role"] = "Engineer" });

// Query neighbors
List<NodeRef> friends = graph.Neighbors(new("person", "1"), "KNOWS");

// Multi-hop traversal
List<NodeRef> fof = graph.MultiHop(new("person", "1"), "KNOWS", 2);

// Shortest path
Path? path = graph.ShortestPath(new("person", "1"), new("person", "3"), "KNOWS");
if (path is not null)
    Console.WriteLine($"Path length: {path.Length}");

// Serialize
string ison = graph.ToIson();
graph.Save("social.ison");
var loaded = ISONGraph.Load("social.ison");
```

## API Reference

### ISONGraph

```csharp
var graph = new ISONGraph("name");                  // Directed graph
var graph = new ISONGraph("name", directed: false); // Undirected graph
```

#### Node Operations

| Method | Description |
|--------|-------------|
| `AddNode(type, id, props)` | Add a node (type/id must not contain `:`) |
| `GetNode(type, id)` / `GetNode(ref)` | Get a node |
| `HasNode(type, id)` / `HasNode(ref)` | Check if exists |
| `RemoveNode(type, id)` | Remove node and its edges |
| `UpdateNode(type, id, props)` | Merge properties |
| `Nodes(type?)` | Iterate nodes (optionally by type) |
| `NodeCount(type?)` | Count nodes |
| `NodeTypes()` | Get all node types |

#### Edge Operations

| Method | Description |
|--------|-------------|
| `AddEdge(rel, src, tgt, props)` | Add an edge (undirected graphs auto-add the reverse) |
| `GetEdge(rel, src, tgt)` | Get an edge |
| `HasEdge(rel, src, tgt)` | Check if exists |
| `RemoveEdge(rel, src, tgt)` | Remove edge (both directions when undirected) |
| `Edges(rel?, source?, target?)` | Iterate edges with filters |
| `EdgeCount(rel?)` | Count edges |
| `EdgeTypes()` | Get all edge types |

ISONGraph is a **simple graph**: `AddEdge` throws `DuplicateEdgeError` on a
repeated `(relType, source, target)` triple - parallel edges aren't
representable, by design (it's what keeps canonical serialization
tie-break-free). Converting from a multigraph source? Dedupe/merge in the
converter before calling `AddEdge`.

#### Traversal

| Method | Description |
|--------|-------------|
| `Neighbors(ref, rel?, dir)` | Get neighbors |
| `MultiHop(start, rel?, hops, dir)` | N-hop traverse |
| `MultiHopRange(start, rel?, min, max, dir)` | Range traverse |
| `Traverse(start, pattern, filter?)` | Pattern traverse |
| `Start(ref)` | Begin a fluent traversal |

#### Path Finding

| Method | Description |
|--------|-------------|
| `ShortestPath(start, end, rel?, max, dir)` | BFS shortest path |
| `AllPaths(start, end, rel?, max, dir)` | All simple paths (iterative DFS) |
| `PathExists(start, end, rel?, max)` | Check reachability |

#### Graph Analysis

| Method | Description |
|--------|-------------|
| `InDegree(ref)` / `OutDegree(ref)` / `Degree(ref)` | Degree counts |
| `IsConnected()` | Check connectivity |
| `HasCycle(rel?)` | Detect cycles (parent-edge tracking for undirected) |
| `ConnectedComponents()` | All connected components |

#### Serialization

| Method | Description |
|--------|-------------|
| `ToIson()` / `ToIsonl()` | Serialize to ISON / ISONL |
| `ISONGraph.FromIson(text)` / `FromIsonl(text)` | Parse (strict; malformed input throws) |
| `Save(path)` / `ISONGraph.Load(path)` | File I/O (format by extension) |

`ToIson()`/`ToIsonl()` are canonical: node/edge type blocks and rows are
sorted (ordinal, `StringComparer.Ordinal`), so the same logical graph
always serializes to the same bytes regardless of insertion order -
byte-identical with every other ISONGraph language port.

### Types

```csharp
public readonly record struct NodeRef(string Type, string Id);

// Properties are string dictionaries
Dictionary<string, string> props;

public enum Direction { Out, In, Both }
```

### Fluent Traversal

```csharp
var companies = graph.Start(new("person", "1"))
    .Hop("KNOWS")
    .Hop("WORKS_AT")
    .Filter(n => n.Properties.GetValueOrDefault("industry") == "Tech")
    .Collect();
```

---

## ISONQL Query Language

ISONQL is a declarative query language for ISONGraph, providing SQL-like
queries for property graphs.

### Basic Usage

```csharp
using IsonGraph;

var graph = new ISONGraph("social");
graph.AddNode("person", "alice", new() { ["name"] = "Alice", ["age"] = "30", ["city"] = "NYC" });
graph.AddNode("person", "bob", new() { ["name"] = "Bob", ["age"] = "25", ["city"] = "LA" });
graph.AddEdge("KNOWS", new("person", "alice"), new("person", "bob"), new() { ["since"] = "2020" });

var engine = new QueryEngine(graph);

QueryResult result = engine.Execute("NODES person WHERE age > 25");
Console.WriteLine($"Found {result.Count} people");
```

### Supported Query Types

```sql
-- NODES: select and filter nodes
NODES person
NODES person WHERE age > 25 AND city = NYC
NODES person WHERE city = LA OR city = Chicago
NODES person ORDER BY age DESC LIMIT 10 OFFSET 5
NODES person WHERE city = NYC RETURN name, age
NODES person(city="NYC")

-- EDGES: select and filter edges
EDGES KNOWS WHERE since > 2020 LIMIT 10

-- TRAVERSE: graph traversal
TRAVERSE person:alice -> KNOWS -> person
TRAVERSE person:bob <- KNOWS <- person
TRAVERSE person:alice -> KNOWS -> person MAX 3

-- PATH: shortest path
PATH person:alice TO person:bob VIA KNOWS MAX 5

-- COUNT and aggregations
COUNT person WHERE age > 20
SUM person.salary WHERE city = NYC
AVG person.age
MIN person.age
MAX person.age
```

### Query Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `=`, `==` | Equal | `name = Alice` |
| `!=`, `<>` | Not equal | `city != LA` |
| `>` `>=` `<` `<=` | Comparisons (numeric-aware) | `age >= 25` |
| `IN` / `NOT IN` | List membership | `city IN (NYC, LA)` |
| `CONTAINS` | Contains substring | `name CONTAINS ali` |
| `STARTS_WITH` / `ENDS_WITH` | Prefix / suffix | `name STARTS_WITH A` |
| `MATCHES` | Regex match (anchored at start) | `email MATCHES ^[a-z]+@` |
| `EXISTS field` / `field EXISTS` | Field exists | `EXISTS email` |
| `NOT EXISTS field` / `field NOT EXISTS` | Field missing | `phone NOT EXISTS` |

`AND` binds tighter than `OR`: `a AND b OR c` evaluates as `(a AND b) OR c`.

### Fluent Query Builder

```csharp
var result = engine.Match("person")
    .Where("age", ">", 25)
    .Where("city", "=", "NYC")
    .OrderBy("age", "DESC")
    .Limit(10)
    .Execute();

long count = engine.Match("person").Where("city", "=", "NYC").Count();

var edges = engine.MatchEdges("KNOWS")
    .Where("since", ">", 2020)
    .Limit(10)
    .Execute();
```

Unknown operator strings in `Where()` throw `ArgumentException` instead of
silently matching everything.

---

## Schema Validation (Graphantic)

```csharp
using IsonGraph;

var person = new NodeType("person")
    .Id(new IntField())
    .Field("name", new StringField().Required().Max(100))
    .Field("age", new IntField().Min(0).Max(150))
    .Field("email", new StringField().Email())
    .Field("status", new StringField().Enum("active", "inactive").Default("active"));

var company = new NodeType("company")
    .Id(new IntField())
    .Field("name", new StringField().Required());

var knows = new EdgeType("KNOWS")
    .FromNode(person)
    .ToNode(person)
    .NoSelfLoop()
    .Unique();

var worksAt = new EdgeType("WORKS_AT")
    .FromNode(person)
    .ToNode(company)
    .Cardinality(Cardinality.ManyToOne);

var reportsTo = new EdgeType("REPORTS_TO")
    .FromNode(person)
    .ToNode(person)
    .Acyclic()                      // per-relationship-type DAG check
    .Field("since", new IntField().Required());

var schema = new GraphSchema("social")
    .NodeTypes(person, company)
    .EdgeTypes(knows, worksAt, reportsTo)
    .NoOrphans();

ValidationResult result = schema.Validate(graph);
if (!result.Valid)
{
    foreach (var error in result.Errors)
        Console.WriteLine($"[{error.Location}] {error.Code}: {error.Message}");
}
```

Field validators: `StringField` (`Required`, `Min`, `Max`, `Pattern`, `Email`,
`Enum`, `Default`), `IntField`, `FloatField`, `BoolField`, and `RefField`
(`To`). Declared defaults are written into missing properties during
validation. Edge constraints: `NoSelfLoop`, `Unique`, `Acyclic` (checked per
relationship type), `Bidirectional`, and `Cardinality` (`OneToOne`,
`OneToMany`, `ManyToOne`, `ManyToMany`). Graph constraints: `Connected`,
`NoOrphans`, `MaxDepth`, and custom `Constraint` callbacks.

---

## Visualization

Deterministic force-directed layout plus SVG and self-contained interactive
HTML rendering. The PRNG is a portable 32-bit LCG, so the same graph, size,
and seed produce bit-identical coordinates across every ISONGraph language
port.

```csharp
using IsonGraph;

var layout = Viz.ComputeLayout(graph, width: 900, height: 600, seed: 42);

string svg = Viz.RenderSvg(graph, layout, title: "My Graph");
string html = Viz.RenderHtml(graph, layout);   // hover tooltips, zoom, pan

Viz.Save(graph, "graph.svg");
Viz.Save(graph, "graph.html");

// Radius-aware collision pass: keep node centers >= (rA + rB) * spacing apart
var radii = graph.Nodes().ToDictionary(n => n.Ref, _ => 24.0);
var spaced = Viz.ComputeLayout(graph, radii: radii, spacing: 1.2);
```

---

## Exception Handling

```csharp
try
{
    graph.AddNode("person", "1");
    graph.AddNode("person", "1");  // throws DuplicateNodeError
}
catch (DuplicateNodeError e)
{
    Console.Error.WriteLine($"Duplicate node: {e.Message}");
}

try
{
    var node = graph.GetNode("person", "999");  // throws NodeNotFoundError
}
catch (NodeNotFoundError e)
{
    Console.Error.WriteLine($"Node not found: {e.Message}");
}

// AddNode("bad:type", ...) throws ArgumentException (':' is reserved)
// FromIson / FromIsonl throw GraphError on malformed input - never a silent skip
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

Values containing a space, `|`, `"`, a newline, or the empty string are
double-quoted with `\"`, `\n`, and `\\` escapes; round-trips are lossless.

---

## Requirements

- .NET 8.0 SDK or later
- No external dependencies (base class library only)

## Running Tests

```bash
dotnet test
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

**Mahesh Vaikri**
- Website: [graph.ison.dev](https://graph.ison.dev)
- Documentation: [graph.ison.dev/docs.html](https://graph.ison.dev/docs.html)
- GitHub: [@maheshvaikri-code](https://github.com/maheshvaikri-code)
