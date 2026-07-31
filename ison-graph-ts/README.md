<p align="center">
  <img src="../assets/github_logo_stretched.png" alt="ISONGraph Logo">
</p>

# ison-graph-ts

[![npm](https://img.shields.io/npm/v/ison-graph-ts.svg)](https://www.npmjs.com/package/ison-graph-ts)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ISONGraph** - A token-efficient property graph store with ISON persistence for TypeScript/JavaScript.

## Features

- **Property Graph Model**: Nodes and edges with typed properties
- **O(1) Lookups**: Fast node access by (type, id)
- **Multi-Hop Traversal**: 1-hop, N-hop, and range queries
- **Path Finding**: BFS shortest path, DFS all paths
- **ISONQL**: Declarative query language
- **Schema Validation**: Node/edge type constraints with cardinality
- **Fluent API**: Chainable traversal queries
- **ISON Persistence**: Token-efficient serialization

## Installation

```bash
npm install ison-graph-ts
```

## Quick Start

```typescript
import { ISONGraph, Direction } from 'ison-graph-ts';

// Create a graph
const graph = new ISONGraph('social');

// Add nodes
graph.addNode('person', 1, { name: 'Alice', age: 30 });
graph.addNode('person', 2, { name: 'Bob', age: 25 });
graph.addNode('company', 100, { name: 'TechCorp' });

// Add edges
graph.addEdge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
graph.addEdge('WORKS_AT', ['person', 1], ['company', 100]);

// Query neighbors
const friends = graph.neighbors(['person', 1], 'KNOWS');
console.log(friends); // [['person', 2]]

// Multi-hop traversal
const friendsOfFriends = graph.multiHop(['person', 1], 'KNOWS', 2);

// Shortest path
const path = graph.shortestPath(['person', 1], ['person', 3]);
```

## API Reference

### ISONGraph

```typescript
const graph = new ISONGraph(name?: string, directed?: boolean);
```

#### Node Operations

| Method | Description |
|--------|-------------|
| `addNode(type, id, properties)` | Add a node |
| `getNode(type, id)` | Get a node |
| `getNodeByRef(ref)` | Get node by NodeRef tuple |
| `hasNode(type, id)` | Check if exists |
| `removeNode(type, id)` | Remove node and edges |
| `updateNode(type, id, props)` | Update properties |
| `nodes(type?)` | Iterate over nodes |
| `nodeCount(type?)` | Count nodes |
| `nodeTypes()` | Get all types |

#### Edge Operations

| Method | Description |
|--------|-------------|
| `addEdge(relType, source, target, props)` | Add an edge |
| `getEdge(relType, source, target)` | Get an edge |
| `hasEdge(relType, source, target)` | Check if exists |
| `removeEdge(relType, source, target)` | Remove edge |
| `edges(relType?, source?, target?)` | Iterate over edges |
| `edgeCount(relType?)` | Count edges |
| `edgeTypes()` | Get all types |

ISONGraph is a **simple graph**: `addEdge` throws `DuplicateEdgeError` on a
repeated `(relType, source, target)` triple - parallel edges aren't
representable, by design (it's what keeps canonical serialization
tie-break-free). Converting from a multigraph source? Dedupe/merge in the
converter before calling `addEdge`.

#### Traversal

| Method | Description |
|--------|-------------|
| `neighbors(nodeRef, relType?, direction?)` | Get neighbors |
| `multiHop(start, relType?, hops, direction?)` | N-hop traverse |
| `multiHopRange(start, relType?, min, max, dir?)` | Range traverse |
| `traverse(start, pattern, filterFn?)` | Pattern traverse |

#### Path Finding

| Method | Description |
|--------|-------------|
| `shortestPath(start, end, relType?, maxHops?, dir?)` | BFS shortest |
| `allPaths(start, end, relType?, maxHops?, dir?)` | DFS all paths |
| `pathExists(start, end, relType?, maxHops?)` | Check reachability |

#### Graph Analysis

| Method | Description |
|--------|-------------|
| `inDegree(nodeRef)` | Count incoming edges |
| `outDegree(nodeRef)` | Count outgoing edges |
| `degree(nodeRef)` | Total degree |
| `isConnected()` | Check if graph is connected |
| `hasCycle(relType?)` | Check for cycles |
| `connectedComponents()` | Get all components |

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

### Fluent API

```typescript
const companies = graph.start(['person', 1])
  .hop('KNOWS')
  .hop('WORKS_AT')
  .filter(n => n.properties.industry === 'Tech')
  .collect();

// Multiple hops
const distant = graph.start(['person', 1])
  .hops(3, 'KNOWS')
  .collectNodes();

// Count results
const count = graph.start(['person', 1])
  .hop('KNOWS', Direction.BOTH)
  .count();
```

### Simple Pattern Query

```typescript
// One hop
const friends = graph.query(':person:1 -[:KNOWS]-> *');

// N hops
const fof = graph.query(':person:1 -[:KNOWS*2]-> *');

// Range of hops
const extended = graph.query(':person:1 -[:KNOWS*1..3]-> *');
```

## ISONQL Query Language

ISONQL is a declarative query language for ISONGraph.

### Setup

```typescript
import { ISONGraph, QueryEngine } from 'ison-graph-ts';

const graph = new ISONGraph('example');
// ... add nodes and edges ...

const engine = new QueryEngine(graph);
```

### Node Queries

```typescript
// All nodes of a type
const result = engine.execute('NODES person');

// With conditions
const adults = engine.execute('NODES person WHERE age >= 18');

// Multiple conditions
const result = engine.execute('NODES person WHERE age > 25 AND city = "NYC"');

// String operations
engine.execute('NODES person WHERE name STARTS_WITH "A"');
engine.execute('NODES person WHERE email CONTAINS "@"');
engine.execute('NODES person WHERE name MATCHES "^[A-Z]"');

// IN operator
engine.execute('NODES person WHERE status IN ("active", "pending")');

// EXISTS
engine.execute('NODES person WHERE EXISTS email');
engine.execute('NODES person WHERE NOT EXISTS phone');

// Ordering and pagination
engine.execute('NODES person ORDER BY age DESC LIMIT 10 OFFSET 20');

// Field projection
engine.execute('NODES person RETURN name, age');

// Shorthand syntax
engine.execute('NODES person(name="Alice")');
```

### Edge Queries

```typescript
// All edges of a type
const result = engine.execute('EDGES KNOWS');

// With conditions
const recent = engine.execute('EDGES KNOWS WHERE since > 2020');

// With limit
const sample = engine.execute('EDGES KNOWS LIMIT 100');
```

### Traversal Queries

```typescript
// Single hop
engine.execute('TRAVERSE :person:1 -> KNOWS -> *');

// Multiple hops (pattern)
engine.execute('TRAVERSE :person:1 -> KNOWS -> person -> WORKS_AT -> company');

// With max depth
engine.execute('TRAVERSE :person:1 -> KNOWS -> * MAX 3');
```

### Path Queries

```typescript
// Find shortest path
engine.execute('PATH :person:1 TO :person:5');

// Via specific relationship
engine.execute('PATH :person:1 TO :person:5 VIA KNOWS');

// With max hops
engine.execute('PATH :person:1 TO :person:5 VIA KNOWS MAX 5');
```

### Aggregations

```typescript
// Count
engine.execute('COUNT person');
engine.execute('COUNT person WHERE age > 30');

// Numeric aggregations
engine.execute('SUM person.age');
engine.execute('AVG person.age WHERE city = "NYC"');
engine.execute('MIN person.age');
engine.execute('MAX person.salary');
```

### Fluent Query Builder

```typescript
// Build queries programmatically
const result = engine.match('person')
  .where('age', '>', 25)
  .where('city', '=', 'NYC')
  .orderBy('name', 'ASC')
  .limit(10)
  .execute();

// Count query
const count = engine.match('person')
  .where('status', '=', 'active')
  .count();

// Edge queries
const edges = engine.matchEdges('KNOWS')
  .where('since', '>=', 2020)
  .limit(50)
  .execute();
```

### Working with Results

```typescript
const result = engine.execute('NODES person WHERE age > 25');

// Access properties
console.log(result.count);          // number of results
console.log(result.totalCount);     // total before limit
console.log(result.executionTimeMs); // query time in ms
console.log(result.query);          // original query string

// Iterate over data
for (const item of result) {
  console.log(item);
}

// Get as array
const items = result.toList();

// Get first result
const first = result.first();
```

## Schema Validation

Define and validate graph schemas with type constraints.

### Defining Node Types

```typescript
import {
  GraphSchema,
  NodeType,
  EdgeType,
  StringField,
  IntField,
  FloatField,
  BoolField,
  RefField,
  Cardinality
} from 'ison-graph-ts';

// Define Person node type
const Person = new NodeType('person')
  .id(new IntField())
  .field('name', new StringField().required().max(100))
  .field('email', new StringField().email())
  .field('age', new IntField().min(0).max(150));

// Define Company node type
const Company = new NodeType('company')
  .id(new StringField())
  .field('name', new StringField().required())
  .field('employees', new IntField().min(0));
```

### Field Types

```typescript
// String field with validation
const nameField = new StringField()
  .required()
  .min(1)          // min length
  .max(100)        // max length
  .pattern(/^[A-Z]/) // regex pattern
  .email()         // email format
  .enum('active', 'inactive', 'pending'); // enum values

// Integer field
const ageField = new IntField()
  .required()
  .min(0)
  .max(150)
  .range(0, 150);  // shorthand for min/max

// Float field
const salaryField = new FloatField()
  .min(0)
  .max(1000000);

// Boolean field
const activeField = new BoolField()
  .required()
  .default(true);

// Reference field
const managerField = new RefField('person')
  .required();
```

### Defining Edge Types

```typescript
// Define KNOWS edge type
const Knows = new EdgeType('KNOWS')
  .fromNode(Person)
  .toNode(Person)
  .field('since', new IntField())
  .noSelfLoop()      // prevent A->A
  .unique();         // prevent duplicate edges

// Define WORKS_AT edge type
const WorksAt = new EdgeType('WORKS_AT')
  .fromNode(Person)
  .toNode(Company)
  .field('role', new StringField().required())
  .field('salary', new FloatField().min(0))
  .cardinality(Cardinality.MANY_TO_ONE);

// Define REPORTS_TO (hierarchy - must be acyclic)
const ReportsTo = new EdgeType('REPORTS_TO')
  .fromNode(Person)
  .toNode(Person)
  .noSelfLoop()
  .acyclic();        // prevent cycles (DAG)
```

### Cardinality Constraints

```typescript
import { Cardinality } from 'ison-graph-ts';

// Cardinality options:
// - ONE_TO_ONE: Each source has one target, each target has one source
// - ONE_TO_MANY: Each source has many targets, each target has one source
// - MANY_TO_ONE: Each source has one target, each target has many sources
// - MANY_TO_MANY: No restrictions (default)

const WorksAt = new EdgeType('WORKS_AT')
  .fromNode(Person)
  .toNode(Company)
  .cardinality(Cardinality.MANY_TO_ONE);  // many employees, one company
```

### Graph Schema

```typescript
// Define complete schema
const Schema = new GraphSchema('social')
  .nodeTypes(Person, Company)
  .edgeTypes(Knows, WorksAt, ReportsTo)
  .connected()       // require all nodes be reachable
  .noOrphans();      // require every node has at least one edge

// Validate a graph
const result = Schema.validate(graph);

if (result.valid) {
  console.log('Graph is valid!');
} else {
  for (const error of result.errors) {
    console.log(error.toString());
    // Example output:
    // [nodes.person[1].email] INVALID_EMAIL: Field 'email' is not a valid email address
    // [edges.KNOWS[person:1->person:1]] SELF_LOOP: Self-loop not allowed
  }
}
```

### Custom Constraints

```typescript
import { ValidationError, ErrorCode } from 'ison-graph-ts';

// Node constraint
const Adult = new NodeType('adult')
  .field('age', new IntField().min(18))
  .constraint((node) => {
    if (node.properties.age < 18) {
      return new ValidationError(
        ErrorCode.MIN_VALUE,
        'Adult must be at least 18 years old'
      );
    }
    return null;
  });

// Edge constraint
const Transfer = new EdgeType('TRANSFER')
  .constraint((edge) => {
    if (edge.properties.amount < 0) {
      return new ValidationError(
        ErrorCode.MIN_VALUE,
        'Transfer amount must be positive'
      );
    }
    return null;
  });

// Graph constraint
const Schema = new GraphSchema('network')
  .nodeTypes(Router)
  .edgeTypes(Connection)
  .constraint((graph) => {
    const errors: ValidationError[] = [];
    if (graph.nodeCount() > 1000) {
      errors.push(new ValidationError(
        ErrorCode.MAX_DEPTH_EXCEEDED,
        'Graph exceeds maximum allowed nodes'
      ));
    }
    return errors;
  });
```

### Error Codes

```typescript
import { ErrorCode } from 'ison-graph-ts';

// Field errors
ErrorCode.REQUIRED_FIELD    // Required field is missing
ErrorCode.INVALID_TYPE      // Wrong data type
ErrorCode.MIN_VALUE         // Below minimum value
ErrorCode.MAX_VALUE         // Above maximum value
ErrorCode.MIN_LENGTH        // Below minimum length
ErrorCode.MAX_LENGTH        // Above maximum length
ErrorCode.PATTERN_MISMATCH  // Regex pattern not matched
ErrorCode.INVALID_EMAIL     // Invalid email format
ErrorCode.INVALID_ENUM      // Value not in allowed enum

// Reference errors
ErrorCode.REF_NOT_FOUND     // Referenced node doesn't exist
ErrorCode.REF_WRONG_TYPE    // Reference to wrong node type

// Edge errors
ErrorCode.SELF_LOOP         // Self-referential edge not allowed
ErrorCode.DUPLICATE_EDGE    // Duplicate edge exists
ErrorCode.CARDINALITY_VIOLATION  // Cardinality constraint violated
ErrorCode.INVALID_SOURCE_TYPE    // Wrong source node type
ErrorCode.INVALID_TARGET_TYPE    // Wrong target node type

// Graph errors
ErrorCode.CYCLE_DETECTED    // Cycle in acyclic edge type
ErrorCode.NOT_CONNECTED     // Graph not connected
ErrorCode.ORPHAN_NODE       // Node has no edges
```

## Types

```typescript
type NodeRef = [string, number | string];  // [type, id]
type EdgeKey = [string, NodeRef, NodeRef]; // [relType, source, target]
type Properties = Record<string, any>;

enum Direction {
  OUT = "out",
  IN = "in",
  BOTH = "both"
}

enum Cardinality {
  ONE_TO_ONE = "1:1",
  ONE_TO_MANY = "1:N",
  MANY_TO_ONE = "N:1",
  MANY_TO_MANY = "N:N"
}
```

## Error Handling

```typescript
import {
  GraphError,
  NodeNotFoundError,
  EdgeNotFoundError,
  DuplicateNodeError,
  DuplicateEdgeError
} from 'ison-graph-ts';

try {
  graph.addNode('person', 1, { name: 'Alice' });
  graph.addNode('person', 1, { name: 'Bob' }); // throws DuplicateNodeError
} catch (e) {
  if (e instanceof DuplicateNodeError) {
    console.log(`Node already exists: ${e.nodeRef}`);
  }
}

try {
  graph.getNode('person', 999); // throws NodeNotFoundError
} catch (e) {
  if (e instanceof NodeNotFoundError) {
    console.log(`Node not found: ${e.nodeRef}`);
  }
}
```

## ISON Format

```
nodes.person
id name age
1 Alice 30
2 Bob 25

edges.KNOWS
source target since
:person:1 :person:2 2020
```

## Complete Example

```typescript
import {
  ISONGraph,
  Direction,
  QueryEngine,
  GraphSchema,
  NodeType,
  EdgeType,
  StringField,
  IntField,
  Cardinality
} from 'ison-graph-ts';

// Define schema
const Person = new NodeType('person')
  .id(new IntField())
  .field('name', new StringField().required())
  .field('age', new IntField().min(0));

const Company = new NodeType('company')
  .id(new StringField())
  .field('name', new StringField().required());

const Knows = new EdgeType('KNOWS')
  .fromNode(Person)
  .toNode(Person)
  .noSelfLoop()
  .unique();

const WorksAt = new EdgeType('WORKS_AT')
  .fromNode(Person)
  .toNode(Company)
  .cardinality(Cardinality.MANY_TO_ONE);

const Schema = new GraphSchema('social')
  .nodeTypes(Person, Company)
  .edgeTypes(Knows, WorksAt);

// Create and populate graph
const graph = new ISONGraph('social');

graph.addNode('person', 1, { name: 'Alice', age: 30 });
graph.addNode('person', 2, { name: 'Bob', age: 25 });
graph.addNode('person', 3, { name: 'Carol', age: 35 });
graph.addNode('company', 'acme', { name: 'Acme Corp' });

graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
graph.addEdge('WORKS_AT', ['person', 1], ['company', 'acme']);
graph.addEdge('WORKS_AT', ['person', 2], ['company', 'acme']);

// Validate schema
const validation = Schema.validate(graph);
if (!validation.valid) {
  console.log('Validation errors:', validation.errors);
}

// Query with ISONQL
const engine = new QueryEngine(graph);

// Find people over 25
const adults = engine.execute('NODES person WHERE age > 25');
console.log('Adults:', adults.toList());

// Find friends of friends
const fof = graph.multiHop(['person', 1], 'KNOWS', 2);
console.log('Friends of friends:', fof);

// Find path between people
const path = graph.shortestPath(['person', 1], ['person', 3], 'KNOWS');
console.log('Path:', path?.toString());

// Serialize
const ison = graph.toIson();
console.log('ISON format:\n', ison);
```

## Visualization (new in 1.1.0)

Deterministic layout and dependency-free rendering, mirroring the Python
`ison_graph.viz` module - the same graph and seed produce bit-identical
coordinates in both languages (covered by a parity test).

```typescript
import { ISONGraph } from 'ison-graph-ts';
import { computeLayout, renderSvg, renderHtml } from 'ison-graph-ts/viz';
// (also available as a namespace: import { viz } from 'ison-graph-ts')

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
