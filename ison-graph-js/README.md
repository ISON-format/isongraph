<p align="center">
  <img src="../assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ison-graph-js

[![npm](https://img.shields.io/npm/v/ison-graph-js.svg)](https://www.npmjs.com/package/ison-graph-js)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ISONGraph** - A token-efficient property graph store with ISON persistence for JavaScript.

## Features

- **Property Graph Model**: Nodes and edges with typed properties
- **O(1) Lookups**: Fast node access by (type, id) tuples
- **Multi-Hop Traversal**: 1-hop, N-hop, and range queries
- **Path Finding**: BFS shortest path and all paths
- **ISONQL Query Language**: Declarative graph queries
- **Schema Validation**: Type-safe graph constraints
- **ISON Persistence**: Token-efficient serialization
- **ES6 Modules**: Modern JavaScript with full ESM support

## Installation

```bash
npm install ison-graph-js
```

## Quick Start

```javascript
import { ISONGraph, Direction } from 'ison-graph-js';

// Create a graph
const graph = new ISONGraph('social');

// Add nodes
graph.addNode('person', 1, { name: 'Alice', age: 30 });
graph.addNode('person', 2, { name: 'Bob', age: 25 });
graph.addNode('company', 100, { name: 'TechCorp' });

// Add edges
graph.addEdge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
graph.addEdge('WORKS_AT', ['person', 1], ['company', 100], {});

// Query neighbors
const friends = graph.neighbors(['person', 1], 'KNOWS');
console.log('Friends:', friends);

// Multi-hop traversal
const fof = graph.multiHop(['person', 1], 'KNOWS', 2);

// Shortest path
const path = graph.shortestPath(
  ['person', 1],
  ['person', 3],
  'KNOWS',
  10
);
if (path) {
  console.log('Path length:', path.length);
}
```

## API Reference

### ISONGraph

```javascript
// Create directed graph (default)
const graph = new ISONGraph('name');

// Create undirected graph
const graph = new ISONGraph('name', false);
```

#### Node Operations

| Method | Description |
|--------|-------------|
| `addNode(type, id, props)` | Add a node |
| `getNode(type, id)` | Get a node |
| `getNodeByRef([type, id])` | Get a node by reference tuple |
| `hasNode(type, id)` | Check if exists |
| `removeNode(type, id)` | Remove node and edges |
| `updateNode(type, id, props)` | Update properties |
| `nodes(type?)` | Generator for all nodes (optional type filter) |
| `nodeCount(type?)` | Count all nodes (optional type filter) |
| `nodeTypes()` | Get all node types |

#### Edge Operations

| Method | Description |
|--------|-------------|
| `addEdge(rel, src, tgt, props)` | Add an edge |
| `getEdge(rel, src, tgt)` | Get an edge |
| `hasEdge(rel, src, tgt)` | Check if exists |
| `removeEdge(rel, src, tgt)` | Remove edge |
| `edges(rel?, src?, tgt?)` | Generator for edges with filters |
| `edgeCount(rel?)` | Count edges (optional type filter) |
| `edgeTypes()` | Get all edge types |

ISONGraph is a **simple graph**: `addEdge` throws `DuplicateEdgeError` on a
repeated `(relType, source, target)` triple - parallel edges aren't
representable, by design (it's what keeps canonical serialization
tie-break-free). Converting from a multigraph source? Dedupe/merge in the
converter before calling `addEdge`.

#### Traversal

| Method | Description |
|--------|-------------|
| `neighbors(ref, rel?, dir)` | Get neighbor node refs |
| `multiHop(start, rel?, hops, dir)` | N-hop traversal |
| `multiHopRange(start, rel?, min, max, dir)` | Range traversal |
| `traverse(start, pattern, filter?)` | Pattern-based traversal |

#### Path Finding

| Method | Description |
|--------|-------------|
| `shortestPath(start, end, rel?, max, dir)` | BFS shortest path |
| `allPaths(start, end, rel?, max, dir)` | DFS all paths |
| `pathExists(start, end, rel?, max)` | Check reachability |

#### Graph Analysis

| Method | Description |
|--------|-------------|
| `inDegree(ref)` | Count incoming edges |
| `outDegree(ref)` | Count outgoing edges |
| `degree(ref)` | Total degree |
| `isConnected()` | Check connectivity |
| `hasCycle(rel?)` | Detect cycles |
| `connectedComponents()` | Get connected components |

#### Serialization

| Method | Description |
|--------|-------------|
| `toIson()` | Serialize to ISON |
| `toIsonl()` | Serialize to ISONL |
| `ISONGraph.fromIson(text)` | Parse from ISON |
| `ISONGraph.fromIsonl(text)` | Parse from ISONL |

`toIson()`/`toIsonl()` are canonical: node/edge type blocks and rows are
sorted (ordinal), so the same logical graph always serializes to the same
bytes regardless of insertion order - safe for content-addressing or prompt
caching, and byte-identical with every other ISONGraph language port.

## Types

```javascript
// Traversal direction
import { Direction } from 'ison-graph-js';

Direction.OUT   // Outgoing edges
Direction.IN    // Incoming edges
Direction.BOTH  // Both directions

// Node reference: [type, id] tuple
const nodeRef = ['person', 1];

// Data classes
import { Node, Edge, Path } from 'ison-graph-js';
```

## Error Handling

```javascript
import {
  GraphError,
  NodeNotFoundError,
  DuplicateNodeError,
  EdgeNotFoundError,
  DuplicateEdgeError
} from 'ison-graph-js';

try {
  graph.addNode('person', 1, {});
  graph.addNode('person', 1, {}); // Throws DuplicateNodeError
} catch (e) {
  if (e instanceof DuplicateNodeError) {
    console.log('Node already exists:', e.nodeRef);
  }
}
```

## Fluent Traversal API

```javascript
// Start fluent traversal
const results = graph.start(['person', 1])
  .hop('KNOWS')                    // Single hop
  .hops(2, 'KNOWS')                // Multiple hops
  .filter(node => node.properties.age > 25)
  .collect();                       // Get node refs

// Get full nodes
const nodes = graph.start(['person', 1])
  .hop('KNOWS', Direction.OUT)
  .collectNodes();

// Count results
const count = graph.start(['person', 1])
  .hop('KNOWS')
  .count();

// Get first result
const first = graph.start(['person', 1])
  .hop('KNOWS')
  .first();
```

---

## ISONQL Query Language

ISONQL is a declarative query language for ISONGraph, providing a pure property graph query interface without external database dependencies.

### Basic Usage

```javascript
import { ISONGraph, QueryEngine } from 'ison-graph-js';

// Create and populate graph
const graph = new ISONGraph('social');
graph.addNode('person', 'alice', { name: 'Alice', age: 30, city: 'NYC' });
graph.addNode('person', 'bob', { name: 'Bob', age: 25, city: 'LA' });
graph.addNode('person', 'charlie', { name: 'Charlie', age: 35, city: 'NYC' });
graph.addNode('company', 'techcorp', { name: 'TechCorp', size: 500 });
graph.addEdge('KNOWS', ['person', 'alice'], ['person', 'bob'], { since: 2020 });
graph.addEdge('KNOWS', ['person', 'bob'], ['person', 'charlie'], { since: 2021 });
graph.addEdge('WORKS_AT', ['person', 'alice'], ['company', 'techcorp'], { role: 'Engineer' });

// Create query engine
const engine = new QueryEngine(graph);

// Execute queries
const result = engine.execute("NODES person WHERE age > 25");
console.log(`Found ${result.count} people`);
```

### Supported Query Types

#### NODES - Query Nodes

```javascript
// All nodes of a type
engine.execute("NODES person");

// With WHERE clause
engine.execute("NODES person WHERE age > 25");

// Multiple conditions
engine.execute("NODES person WHERE age > 25 AND city = NYC");

// With sorting
engine.execute("NODES person WHERE age > 20 ORDER BY age DESC");

// With pagination
engine.execute("NODES person ORDER BY name ASC LIMIT 10 OFFSET 5");

// Return specific fields
engine.execute("NODES person WHERE city = NYC RETURN name, age");

// Shorthand syntax
engine.execute("NODES person(city=NYC)");
```

#### EDGES - Query Edges

```javascript
// All edges of a type
engine.execute("EDGES KNOWS");

// With WHERE clause on edge properties
engine.execute("EDGES KNOWS WHERE since > 2020");

// With limit
engine.execute("EDGES WORKS_AT LIMIT 10");
```

#### TRAVERSE - Graph Traversal

```javascript
// Single hop outgoing
engine.execute("TRAVERSE person:alice -> KNOWS -> person");

// Single hop incoming
engine.execute("TRAVERSE person:bob <- KNOWS <- person");

// Multi-hop with max depth
engine.execute("TRAVERSE person:alice -> KNOWS -> person MAX 3");

// Undirected traversal
engine.execute("TRAVERSE person:alice -- KNOWS -- person");

// Any node type
engine.execute("TRAVERSE person:alice -> WORKS_AT -> *");
```

#### PATH - Find Shortest Path

```javascript
// Find shortest path between nodes
engine.execute("PATH person:alice TO person:charlie");

// Via specific relationship
engine.execute("PATH person:alice TO person:charlie VIA KNOWS");

// With max hops
engine.execute("PATH person:alice TO person:charlie VIA KNOWS MAX 5");
```

#### COUNT - Count Nodes

```javascript
// Count all nodes of a type
engine.execute("COUNT person");

// Count with filter
engine.execute("COUNT person WHERE city = NYC");
```

#### Aggregations - SUM, AVG, MIN, MAX

```javascript
// Sum a property
engine.execute("SUM person.age");

// Average with filter
engine.execute("AVG person.age WHERE city = NYC");

// Min/max values
engine.execute("MIN person.age");
engine.execute("MAX company.size");
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

```javascript
const result = engine.execute("NODES person WHERE age > 25");

// Access metadata
console.log('Count:', result.count);
console.log('Total:', result.totalCount);
console.log('Time:', result.executionTimeMs, 'ms');

// Iterate over results
for (const data of result) {
  console.log('Node:', data.type, data.id);
  console.log('Properties:', data.properties);
}

// Get as array
const nodes = result.toList();

// Get first result
const first = result.first();
```

### Fluent Query Builder

For programmatic query construction, use the fluent builder API:

```javascript
const engine = new QueryEngine(graph);

// Build and execute query fluently
const result = engine.match('person')
  .where('age', '>', 25)
  .where('city', '=', 'NYC')
  .orderBy('age', 'DESC')
  .limit(10)
  .execute();

// Count query
const count = engine.match('person')
  .where('city', '=', 'NYC')
  .count();

console.log(`Found ${count} people in NYC`);

// With field projection
const result = engine.match('person')
  .where('age', '>=', 21)
  .returnFields('name', 'age')
  .offset(5)
  .limit(10)
  .execute();

// Edge queries
const edges = engine.matchEdges('KNOWS')
  .where('since', '>', 2020)
  .limit(10)
  .execute();
```

---

## Schema Validation

The schema module provides type-safe graph validation with property constraints, relationship rules, and graph-level constraints.

### Basic Usage

```javascript
import { ISONGraph } from 'ison-graph-js';
import {
  GraphSchema,
  NodeType,
  EdgeType,
  StringField,
  IntField,
  FloatField,
  BoolField,
  RefField,
  Cardinality,
  ErrorCode
} from 'ison-graph-js';

// Define node types
const Person = new NodeType('person')
  .id(new IntField())
  .field('name', new StringField().required().max(100))
  .field('age', new IntField().min(0).max(150))
  .field('email', new StringField().email());

const Company = new NodeType('company')
  .id(new IntField())
  .field('name', new StringField().required());

// Define edge types
const Knows = new EdgeType('KNOWS')
  .fromNode(Person)
  .toNode(Person)
  .noSelfLoop()
  .unique();

const WorksAt = new EdgeType('WORKS_AT')
  .fromNode(Person)
  .toNode(Company)
  .cardinality(Cardinality.MANY_TO_ONE);

// Build schema
const schema = new GraphSchema('social')
  .nodeTypes(Person, Company)
  .edgeTypes(Knows, WorksAt)
  .noOrphans();

// Validate graph
const graph = new ISONGraph('test');
graph.addNode('person', 1, { name: 'Alice', age: 30 });
graph.addNode('person', 2, { name: 'Bob', age: 25 });
graph.addEdge('KNOWS', ['person', 1], ['person', 2], {});

const result = schema.validate(graph);
if (result.valid) {
  console.log('Graph is valid!');
} else {
  for (const error of result.errors) {
    console.log('Error:', error.toString());
  }
}
```

### Field Types

#### StringField

```javascript
import { StringField } from 'ison-graph-js';

// Basic string field
const field = new StringField();

// Required field
const field = new StringField().required();

// Length constraints
const field = new StringField()
  .min(3)       // Minimum 3 characters
  .max(100);    // Maximum 100 characters

// Pattern matching (regex)
const field = new StringField()
  .pattern(/^[A-Z][a-z]+$/);  // Must start with capital

// Email validation
const field = new StringField().email();

// Allowed values (enum)
const field = new StringField()
  .enum('active', 'inactive', 'pending');

// Default value
const field = new StringField().default('pending');
```

#### IntField

```javascript
import { IntField } from 'ison-graph-js';

// Basic integer field
const field = new IntField();

// Required
const field = new IntField().required();

// Range constraints
const field = new IntField()
  .min(0)
  .max(150);

// Or use range()
const field = new IntField().range(0, 150);

// Default value
const field = new IntField().default(0);
```

#### FloatField

```javascript
import { FloatField } from 'ison-graph-js';

// Basic float field
const field = new FloatField();

// With constraints
const field = new FloatField()
  .required()
  .min(0.0)
  .max(100.0);

// Using range
const field = new FloatField().range(-180.0, 180.0);  // e.g., longitude
```

#### BoolField

```javascript
import { BoolField } from 'ison-graph-js';

// Basic boolean field
const field = new BoolField();

// Required boolean
const field = new BoolField().required();

// Default value
const field = new BoolField().default(false);
```

#### RefField

```javascript
import { RefField } from 'ison-graph-js';

// Reference to any node
const field = new RefField();

// Reference to specific node type
const field = new RefField().to('person');

// Required reference
const field = new RefField('company').required();
```

### Node Type Schema

```javascript
import { NodeType, StringField, IntField } from 'ison-graph-js';

const Person = new NodeType('person')
  // Validate the ID field
  .id(new IntField())

  // Define property fields
  .field('name', new StringField().required().max(100))
  .field('age', new IntField().min(0).max(150))
  .field('email', new StringField().email())
  .field('status', new StringField().enum('active', 'inactive'))

  // Custom constraint function
  .constraint(node => {
    if (node.properties.age < 18 && node.properties.status === 'active') {
      return new ValidationError(
        ErrorCode.INVALID_TYPE,
        'Minors cannot have active status'
      );
    }
    return null;
  });
```

### Edge Type Schema

```javascript
import { EdgeType, StringField, IntField, Cardinality } from 'ison-graph-js';

// Basic edge type
const Knows = new EdgeType('KNOWS')
  .fromNode(Person)
  .toNode(Person);

// With constraints
const WorksAt = new EdgeType('WORKS_AT')
  .fromNode(Person)
  .toNode(Company)
  .noSelfLoop()      // Cannot connect node to itself
  .unique()          // No duplicate edges
  .cardinality(Cardinality.MANY_TO_ONE);

// With edge properties
const ReportsTo = new EdgeType('REPORTS_TO')
  .fromNode(Person)
  .toNode(Person)
  .noSelfLoop()
  .acyclic()         // Must be DAG (no cycles)
  .field('since', new IntField().required())
  .field('department', new StringField());

// Bidirectional edges
const FriendsWith = new EdgeType('FRIENDS_WITH')
  .fromNode(Person)
  .toNode(Person)
  .noSelfLoop()
  .bidirectional();  // If A->B exists, B->A must also exist
```

### Edge Constraints

| Constraint | Method | Description |
|------------|--------|-------------|
| No Self Loop | `.noSelfLoop()` | Edge cannot connect node to itself |
| Unique | `.unique()` | No duplicate edges between same pair |
| Acyclic | `.acyclic()` | Must form DAG (no cycles) |
| Bidirectional | `.bidirectional()` | Reverse edge must exist |
| Cardinality | `.cardinality(card)` | Relationship cardinality |

### Cardinality Constraints

```javascript
import { Cardinality } from 'ison-graph-js';

// One-to-One: Each source has exactly one target, each target has one source
// Example: person HAS_PASSPORT passport
new EdgeType('HAS_PASSPORT')
  .cardinality(Cardinality.ONE_TO_ONE);

// One-to-Many: One source to many targets, each target has one source
// Example: company HAS_DEPARTMENT department
new EdgeType('HAS_DEPARTMENT')
  .cardinality(Cardinality.ONE_TO_MANY);

// Many-to-One: Many sources to one target
// Example: person WORKS_AT company (many employees, one company per person)
new EdgeType('WORKS_AT')
  .cardinality(Cardinality.MANY_TO_ONE);

// Many-to-Many: No restrictions (default)
// Example: person KNOWS person
new EdgeType('KNOWS')
  .cardinality(Cardinality.MANY_TO_MANY);
```

### Graph-Level Constraints

```javascript
import { GraphSchema } from 'ison-graph-js';

const schema = new GraphSchema('social')
  .nodeTypes(Person, Company)
  .edgeTypes(Knows, WorksAt)

  // Graph must be connected (all nodes reachable)
  .connected()

  // No orphan nodes (all nodes must have at least one edge)
  .noOrphans()

  // Maximum depth constraint
  .maxDepth(10)

  // Custom graph constraint
  .constraint(graph => {
    if (graph.nodeCount('person') > 1000) {
      return [new ValidationError(
        ErrorCode.MAX_DEPTH_EXCEEDED,
        'Too many person nodes',
        'graph'
      )];
    }
    return [];
  });
```

### Validation Results

```javascript
const result = schema.validate(graph);

// Check validity
if (result.valid) {
  console.log('Graph is valid');
} else {
  // Access errors
  for (const error of result.errors) {
    console.log(`[${error.location}] ${error.code}: ${error.message}`);
  }

  // Access warnings
  for (const warning of result.warnings) {
    console.log('Warning:', warning.message);
  }
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

```javascript
import { ISONGraph } from 'ison-graph-js';
import {
  GraphSchema,
  NodeType,
  EdgeType,
  StringField,
  IntField,
  Cardinality
} from 'ison-graph-js';

// Define node types
const User = new NodeType('user')
  .id(new IntField())
  .field('username', new StringField()
    .required()
    .min(3)
    .max(50)
    .pattern(/^[a-zA-Z0-9_]+$/))
  .field('email', new StringField().required().email())
  .field('age', new IntField().min(13).max(150));

const Post = new NodeType('post')
  .id(new IntField())
  .field('title', new StringField().required().max(200))
  .field('content', new StringField().required())
  .field('status', new StringField().enum('draft', 'published', 'archived'));

const Comment = new NodeType('comment')
  .id(new IntField())
  .field('text', new StringField().required().max(1000));

// Define edge types
const Follows = new EdgeType('FOLLOWS')
  .fromNode(User)
  .toNode(User)
  .noSelfLoop();

const Authored = new EdgeType('AUTHORED')
  .fromNode(User)
  .toNode(Post)
  .cardinality(Cardinality.ONE_TO_MANY);

const CommentedOn = new EdgeType('COMMENTED_ON')
  .fromNode(Comment)
  .toNode(Post)
  .cardinality(Cardinality.MANY_TO_ONE);

const WroteComment = new EdgeType('WROTE_COMMENT')
  .fromNode(User)
  .toNode(Comment)
  .cardinality(Cardinality.ONE_TO_MANY);

// Build schema
const schema = new GraphSchema('blog')
  .nodeTypes(User, Post, Comment)
  .edgeTypes(Follows, Authored, CommentedOn, WroteComment);

// Create and populate graph
const graph = new ISONGraph('blog');

graph.addNode('user', 1, {
  username: 'alice_dev',
  email: 'alice@example.com',
  age: 28
});

graph.addNode('user', 2, {
  username: 'bob_coder',
  email: 'bob@example.com',
  age: 32
});

graph.addNode('post', 101, {
  title: 'Introduction to JavaScript',
  content: 'JavaScript is a dynamic programming language...',
  status: 'published'
});

graph.addEdge('AUTHORED', ['user', 1], ['post', 101], {});
graph.addEdge('FOLLOWS', ['user', 2], ['user', 1], {});

// Validate
const result = schema.validate(graph);
if (result.valid) {
  console.log('Blog graph is valid!');
} else {
  for (const error of result.errors) {
    console.log('Validation error:', error.toString());
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

## Visualization (new in 1.1.0)

Deterministic layout and dependency-free rendering, mirroring the Python
`ison_graph.viz` module - the same graph and seed produce bit-identical
coordinates in both languages (covered by a parity test).

```javascript
import { ISONGraph } from 'ison-graph-js';
import { computeLayout, renderSvg, renderHtml } from 'ison-graph-js/viz';
// (also available as a namespace: import { viz } from 'ison-graph-js')

const graph = new ISONGraph('social');
// ... add nodes and edges ...

// Stage 2: seeded force-directed layout -> Map<"type id", [x, y]>
const layout = computeLayout(graph, { width: 900, height: 600, seed: 42 });

// Stage 3: render the same coordinates
const svg = renderSvg(graph, { layout, title: 'My graph' });  // standalone image
const html = renderHtml(graph, { layout });                    // tooltips, pan/zoom, dark mode
```

Pass `radii` (keyed by `layoutKey(ref)`, i.e. `"type id"`) plus an optional
`spacing` factor to enforce minimum center distance `(rA + rB) * spacing`
between every pair - useful when node size encodes data and large bubbles
must not overlap. Without `radii` the output is byte-identical.

Nodes are colored by type (colorblind-safe palette, 8 slots assigned in
sorted order), sized by degree, and labeled from the `name` property (or
`labelProperty` of your choice).

## License

MIT License - see [LICENSE](../LICENSE) for details.
