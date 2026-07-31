/**
 * Tests for ison-graph-js
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  ISONGraph,
  Node,
  Edge,
  Path,
  Direction,
  GraphTraversal,
  NodeNotFoundError,
  EdgeNotFoundError,
  DuplicateNodeError,
  DuplicateEdgeError,
} from './index.js';

describe('ISONGraph', () => {
  let graph;

  beforeEach(() => {
    graph = new ISONGraph('test');
  });

  describe('Node Operations', () => {
    it('should add and get nodes', () => {
      const node = graph.addNode('person', 1, { name: 'Alice', age: 30 });
      expect(node.type).toBe('person');
      expect(node.id).toBe(1);
      expect(node.properties.name).toBe('Alice');

      const retrieved = graph.getNode('person', 1);
      expect(retrieved).toBe(node);
    });

    it('should throw on duplicate node', () => {
      graph.addNode('person', 1);
      expect(() => graph.addNode('person', 1)).toThrow(DuplicateNodeError);
    });

    it('should throw on getting non-existent node', () => {
      expect(() => graph.getNode('person', 999)).toThrow(NodeNotFoundError);
    });

    it('should check if node exists', () => {
      graph.addNode('person', 1);
      expect(graph.hasNode('person', 1)).toBe(true);
      expect(graph.hasNode('person', 999)).toBe(false);
    });

    it('should remove node and its edges', () => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);

      graph.removeNode('person', 1);
      expect(graph.hasNode('person', 1)).toBe(false);
      expect(graph.edgeCount()).toBe(0);
    });

    it('should update node properties', () => {
      graph.addNode('person', 1, { name: 'Alice' });
      graph.updateNode('person', 1, { age: 31 });

      const node = graph.getNode('person', 1);
      expect(node.properties.name).toBe('Alice');
      expect(node.properties.age).toBe(31);
    });

    it('should count nodes', () => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addNode('company', 100);

      expect(graph.nodeCount()).toBe(3);
      expect(graph.nodeCount('person')).toBe(2);
      expect(graph.nodeCount('company')).toBe(1);
    });

    it('should iterate nodes', () => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);

      const nodes = Array.from(graph.nodes('person'));
      expect(nodes.length).toBe(2);
    });

    it('should get node types', () => {
      graph.addNode('person', 1);
      graph.addNode('company', 100);

      const types = graph.nodeTypes();
      expect(types).toContain('person');
      expect(types).toContain('company');
    });
  });

  describe('Edge Operations', () => {
    beforeEach(() => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addNode('person', 3);
      graph.addNode('company', 100);
    });

    it('should add and get edges', () => {
      const edge = graph.addEdge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
      expect(edge.relType).toBe('KNOWS');
      expect(edge.source).toEqual(['person', 1]);
      expect(edge.target).toEqual(['person', 2]);
      expect(edge.properties.since).toBe(2020);

      const retrieved = graph.getEdge('KNOWS', ['person', 1], ['person', 2]);
      expect(retrieved.relType).toBe('KNOWS');
    });

    it('should throw on edge to non-existent node', () => {
      expect(() => graph.addEdge('KNOWS', ['person', 1], ['person', 999])).toThrow(NodeNotFoundError);
    });

    it('should throw on duplicate edge', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      expect(() => graph.addEdge('KNOWS', ['person', 1], ['person', 2])).toThrow(DuplicateEdgeError);
    });

    it('should check if edge exists', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      expect(graph.hasEdge('KNOWS', ['person', 1], ['person', 2])).toBe(true);
      expect(graph.hasEdge('KNOWS', ['person', 1], ['person', 3])).toBe(false);
    });

    it('should remove edge', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.removeEdge('KNOWS', ['person', 1], ['person', 2]);
      expect(graph.hasEdge('KNOWS', ['person', 1], ['person', 2])).toBe(false);
    });

    it('should count edges', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
      graph.addEdge('WORKS_AT', ['person', 1], ['company', 100]);

      expect(graph.edgeCount()).toBe(3);
      expect(graph.edgeCount('KNOWS')).toBe(2);
    });

    it('should iterate edges', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);

      const edges = Array.from(graph.edges('KNOWS'));
      expect(edges.length).toBe(2);
    });

    it('should get edge types', () => {
      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('WORKS_AT', ['person', 1], ['company', 100]);

      const types = graph.edgeTypes();
      expect(types).toContain('KNOWS');
      expect(types).toContain('WORKS_AT');
    });
  });

  describe('Traversal', () => {
    beforeEach(() => {
      // Create a small social network
      graph.addNode('person', 1, { name: 'Alice' });
      graph.addNode('person', 2, { name: 'Bob' });
      graph.addNode('person', 3, { name: 'Charlie' });
      graph.addNode('person', 4, { name: 'Diana' });
      graph.addNode('company', 100, { name: 'TechCorp' });

      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
      graph.addEdge('KNOWS', ['person', 3], ['person', 4]);
      graph.addEdge('WORKS_AT', ['person', 1], ['company', 100]);
      graph.addEdge('WORKS_AT', ['person', 2], ['company', 100]);
    });

    it('should get neighbors', () => {
      const friends = graph.neighbors(['person', 1], 'KNOWS');
      expect(friends.length).toBe(1);
      expect(friends[0]).toEqual(['person', 2]);
    });

    it('should get neighbors in both directions', () => {
      const connections = graph.neighbors(['person', 2], 'KNOWS', Direction.BOTH);
      expect(connections.length).toBe(2);
    });

    it('should get incoming neighbors', () => {
      const whoKnowsMe = graph.neighbors(['person', 2], 'KNOWS', Direction.IN);
      expect(whoKnowsMe.length).toBe(1);
      expect(whoKnowsMe[0]).toEqual(['person', 1]);
    });

    it('should multi-hop traverse', () => {
      const twoHops = graph.multiHop(['person', 1], 'KNOWS', 2);
      expect(twoHops.length).toBe(1);
      expect(twoHops[0]).toEqual(['person', 3]);
    });

    it('should multi-hop range traverse', () => {
      const oneToThreeHops = graph.multiHopRange(['person', 1], 'KNOWS', 1, 3);
      expect(oneToThreeHops.length).toBe(3);
    });

    it('should traverse pattern', () => {
      const companies = graph.traverse(
        ['person', 1],
        [['KNOWS', Direction.OUT], ['WORKS_AT', Direction.OUT]]
      );
      expect(companies.length).toBe(1);
      expect(companies[0]).toEqual(['company', 100]);
    });
  });

  describe('Path Finding', () => {
    beforeEach(() => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addNode('person', 3);
      graph.addNode('person', 4);

      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
      graph.addEdge('KNOWS', ['person', 3], ['person', 4]);
    });

    it('should find shortest path', () => {
      const path = graph.shortestPath(['person', 1], ['person', 3], 'KNOWS');
      expect(path).not.toBeNull();
      expect(path.length).toBe(2);
      expect(path.nodes.length).toBe(3);
    });

    it('should return null when no path exists', () => {
      graph.addNode('person', 5);
      const path = graph.shortestPath(['person', 1], ['person', 5]);
      expect(path).toBeNull();
    });

    it('should find all paths', () => {
      // Add alternative path
      graph.addEdge('KNOWS', ['person', 1], ['person', 3]);

      const paths = graph.allPaths(['person', 1], ['person', 3], 'KNOWS');
      expect(paths.length).toBe(2);
    });

    it('should check path existence', () => {
      expect(graph.pathExists(['person', 1], ['person', 4])).toBe(true);
      graph.addNode('person', 5);
      expect(graph.pathExists(['person', 1], ['person', 5])).toBe(false);
    });

    it('should respect maxHops boundary in shortestPath', () => {
      // maxHops=1 must not return a 2-hop path
      expect(graph.shortestPath(['person', 1], ['person', 3], 'KNOWS', 1)).toBeNull();

      const path = graph.shortestPath(['person', 1], ['person', 3], 'KNOWS', 2);
      expect(path).not.toBeNull();
      expect(path.length).toBe(2);
    });
  });

  describe('Graph Analysis', () => {
    beforeEach(() => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addNode('person', 3);

      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
    });

    it('should calculate degree', () => {
      expect(graph.outDegree(['person', 1])).toBe(1);
      expect(graph.inDegree(['person', 2])).toBe(1);
      expect(graph.outDegree(['person', 2])).toBe(1);
    });

    it('should check if connected', () => {
      expect(graph.isConnected()).toBe(true);

      graph.addNode('person', 4);
      expect(graph.isConnected()).toBe(false);
    });

    it('should detect cycles', () => {
      expect(graph.hasCycle()).toBe(false);

      graph.addEdge('KNOWS', ['person', 3], ['person', 1]);
      expect(graph.hasCycle()).toBe(true);
    });

    it('should find connected components', () => {
      graph.addNode('person', 4);
      graph.addNode('person', 5);
      graph.addEdge('KNOWS', ['person', 4], ['person', 5]);

      const components = graph.connectedComponents();
      expect(components.length).toBe(2);
    });
  });

  describe('Serialization', () => {
    beforeEach(() => {
      graph.addNode('person', 1, { name: 'Alice' });
      graph.addNode('person', 2, { name: 'Bob' });
      graph.addNode('company', 100, { name: 'TechCorp' });

      graph.addEdge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
      graph.addEdge('WORKS_AT', ['person', 1], ['company', 100]);
    });

    it('should serialize to ISON', () => {
      const ison = graph.toIson();
      expect(ison).toContain('nodes.person');
      expect(ison).toContain('edges.KNOWS');
      expect(ison).toContain('Alice');
    });

    it('should serialize to ISONL', () => {
      const isonl = graph.toIsonl();
      expect(isonl).toContain('nodes.person|');
      expect(isonl).toContain('edges.KNOWS|');
    });

    it('should parse from ISON', () => {
      const ison = graph.toIson();
      const parsed = ISONGraph.fromIson(ison);

      expect(parsed.nodeCount()).toBe(graph.nodeCount());
      expect(parsed.edgeCount()).toBe(graph.edgeCount());
    });

    it('should roundtrip ISONL', () => {
      const isonl = graph.toIsonl();
      const parsed = ISONGraph.fromIsonl(isonl);

      expect(parsed.nodeCount()).toBe(graph.nodeCount());
      expect(parsed.edgeCount()).toBe(graph.edgeCount());
    });

    it('should round-trip special string values through ISON', () => {
      const g = new ISONGraph();
      g.addNode('doc', 1, {
        spaced: 'hello world',
        piped: 'a|b',
        multiline: 'line1\nline2',
        empty: ''
      });

      const parsed = ISONGraph.fromIson(g.toIson());
      expect(parsed.getNode('doc', 1).properties).toEqual({
        spaced: 'hello world',
        piped: 'a|b',
        multiline: 'line1\nline2',
        empty: ''
      });
    });

    it('should round-trip special string values through ISONL', () => {
      const g = new ISONGraph();
      g.addNode('doc', 1, {
        spaced: 'hello world',
        piped: 'a|b',
        multiline: 'line1\nline2',
        empty: ''
      });

      const parsed = ISONGraph.fromIsonl(g.toIsonl());
      expect(parsed.getNode('doc', 1).properties).toEqual({
        spaced: 'hello world',
        piped: 'a|b',
        multiline: 'line1\nline2',
        empty: ''
      });
    });

    it('should convert Reference node properties to [type, id] tuples', () => {
      const ison = 'nodes.person\nid name manager\n1 Alice :person:2\n2 Bob null';
      const parsed = ISONGraph.fromIson(ison);

      expect(parsed.getNode('person', 1).properties.manager).toEqual(['person', '2']);
      expect(parsed.getNode('person', 2).properties.manager).toBeNull();
    });
  });

  describe('Fluent API', () => {
    beforeEach(() => {
      graph.addNode('person', 1, { name: 'Alice' });
      graph.addNode('person', 2, { name: 'Bob' });
      graph.addNode('person', 3, { name: 'Charlie' });
      graph.addNode('company', 100, { name: 'TechCorp' });

      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
      graph.addEdge('WORKS_AT', ['person', 2], ['company', 100]);
    });

    it('should traverse with fluent API', () => {
      const result = graph.start(['person', 1])
        .hop('KNOWS')
        .hop('WORKS_AT')
        .collect();

      expect(result.length).toBe(1);
      expect(result[0]).toEqual(['company', 100]);
    });

    it('should filter with fluent API', () => {
      const result = graph.start(['person', 1])
        .hop('KNOWS')
        .filter(n => n.properties.name === 'Bob')
        .collect();

      expect(result.length).toBe(1);
    });

    it('should count with fluent API', () => {
      const count = graph.start(['person', 1])
        .hops(2, 'KNOWS')
        .count();

      expect(count).toBe(1);
    });

    it('should collect nodes with fluent API', () => {
      const nodes = graph.start(['person', 1])
        .hop('KNOWS')
        .collectNodes();

      expect(nodes.length).toBe(1);
      expect(nodes[0].properties.name).toBe('Bob');
    });
  });

  describe('Undirected Graphs', () => {
    it('should remove both directions of an undirected edge', () => {
      const g = new ISONGraph('undirected', false);
      g.addNode('person', 1);
      g.addNode('person', 2);
      g.addEdge('KNOWS', ['person', 1], ['person', 2]);

      expect(g.hasEdge('KNOWS', ['person', 1], ['person', 2])).toBe(true);
      expect(g.hasEdge('KNOWS', ['person', 2], ['person', 1])).toBe(true);

      g.removeEdge('KNOWS', ['person', 1], ['person', 2]);

      expect(g.hasEdge('KNOWS', ['person', 1], ['person', 2])).toBe(false);
      expect(g.hasEdge('KNOWS', ['person', 2], ['person', 1])).toBe(false);
      expect(g.edgeCount()).toBe(0);
      expect(Array.from(g.edges()).length).toBe(0);
    });

    it('should not report a cycle for a single undirected edge', () => {
      const g = new ISONGraph('undirected', false);
      g.addNode('person', 1);
      g.addNode('person', 2);
      g.addEdge('KNOWS', ['person', 1], ['person', 2]);

      expect(g.hasCycle()).toBe(false);
    });

    it('should not report a cycle for an undirected chain', () => {
      const g = new ISONGraph('undirected', false);
      g.addNode('person', 1);
      g.addNode('person', 2);
      g.addNode('person', 3);
      g.addEdge('KNOWS', ['person', 1], ['person', 2]);
      g.addEdge('KNOWS', ['person', 2], ['person', 3]);

      expect(g.hasCycle()).toBe(false);
    });

    it('should detect a real cycle in an undirected graph', () => {
      const g = new ISONGraph('undirected', false);
      g.addNode('person', 1);
      g.addNode('person', 2);
      g.addNode('person', 3);
      g.addEdge('KNOWS', ['person', 1], ['person', 2]);
      g.addEdge('KNOWS', ['person', 2], ['person', 3]);
      g.addEdge('KNOWS', ['person', 3], ['person', 1]);

      expect(g.hasCycle()).toBe(true);
    });
  });

  describe('Query Pattern', () => {
    beforeEach(() => {
      graph.addNode('person', 1);
      graph.addNode('person', 2);
      graph.addNode('person', 3);
      graph.addNode('person', 4);

      graph.addEdge('KNOWS', ['person', 1], ['person', 2]);
      graph.addEdge('KNOWS', ['person', 2], ['person', 3]);
      graph.addEdge('KNOWS', ['person', 3], ['person', 4]);
    });

    it('should execute simple query', () => {
      const result = graph.query(':person:1 -[:KNOWS]-> *');
      expect(result.length).toBe(1);
    });

    it('should execute N-hop query', () => {
      const result = graph.query(':person:1 -[:KNOWS*2]-> *');
      expect(result.length).toBe(1);
      expect(result[0]).toEqual(['person', 3]);
    });

    it('should execute range query', () => {
      const result = graph.query(':person:1 -[:KNOWS*1..3]-> *');
      expect(result.length).toBe(3);
    });
  });
});

// =============================================================================
// Canonical Serialization
//
// toIson()/toIsonl() must be byte-identical for the same logical graph
// regardless of insertion order (node type blocks, node rows, edge type
// blocks, and edge rows are all sorted, ordinal string comparison). The
// golden fixture below is shared verbatim across every ISONGraph language
// port's test suite (Python, JS, TS, Rust, C++, C#) as the cross-language
// byte-identity contract - if it changes here, it must change everywhere.
// =============================================================================

const CANONICAL_GOLDEN_ISON =
  'nodes.company\n' +
  'id name\n' +
  'acme "Acme Corp"\n' +
  '\n' +
  'nodes.person\n' +
  'id age name\n' +
  '1 30 Alice\n' +
  '10 22 Jax\n' +
  '2 25 Bob\n' +
  '\n' +
  'nodes.project\n' +
  'id name tag\n' +
  'p1 Alpha "a|b"\n' +
  '\n' +
  'edges.KNOWS\n' +
  'source target since\n' +
  ':person:1 :person:2 2020\n' +
  ':person:10 :person:1 2021\n' +
  '\n' +
  'edges.WORKS_AT\n' +
  'source target role\n' +
  ':person:1 :company:acme "Lead Engineer"\n' +
  '\n' +
  'edges.WORKS_ON\n' +
  'source target hours\n' +
  ':person:10 :project:p1 3\n' +
  ':person:2 :project:p1 5';

const CANONICAL_GOLDEN_ISONL =
  'nodes.company|id name|acme "Acme Corp"\n' +
  'nodes.person|id age name|1 30 Alice\n' +
  'nodes.person|id age name|10 22 Jax\n' +
  'nodes.person|id age name|2 25 Bob\n' +
  'nodes.project|id name tag|p1 Alpha "a|b"\n' +
  'edges.KNOWS|source target since|:person:1 :person:2 2020\n' +
  'edges.KNOWS|source target since|:person:10 :person:1 2021\n' +
  'edges.WORKS_AT|source target role|:person:1 :company:acme "Lead Engineer"\n' +
  'edges.WORKS_ON|source target hours|:person:10 :project:p1 3\n' +
  'edges.WORKS_ON|source target hours|:person:2 :project:p1 5';

function buildCanonicalFixture(order) {
  const g = new ISONGraph('fixture');
  const nodes = [
    ['company', 'acme', { name: 'Acme Corp' }],
    ['person', '1', { name: 'Alice', age: '30' }],
    ['person', '10', { name: 'Jax', age: '22' }],
    ['person', '2', { name: 'Bob', age: '25' }],
    ['project', 'p1', { name: 'Alpha', tag: 'a|b' }],
  ];
  const edges = [
    ['KNOWS', ['person', '10'], ['person', '1'], { since: '2021' }],
    ['KNOWS', ['person', '1'], ['person', '2'], { since: '2020' }],
    ['WORKS_AT', ['person', '1'], ['company', 'acme'], { role: 'Lead Engineer' }],
    ['WORKS_ON', ['person', '2'], ['project', 'p1'], { hours: '5' }],
    ['WORKS_ON', ['person', '10'], ['project', 'p1'], { hours: '3' }],
  ];
  const seqN = order === 0 ? nodes : [...nodes].reverse();
  const seqE = order === 0 ? edges : [...edges].reverse();
  for (const [t, i, props] of seqN) g.addNode(t, i, props);
  for (const [rel, s, t, props] of seqE) g.addEdge(rel, s, t, props);
  return g;
}

describe('Canonical Serialization', () => {
  it('toIson is independent of insertion order', () => {
    expect(buildCanonicalFixture(0).toIson()).toBe(buildCanonicalFixture(1).toIson());
  });

  it('toIsonl is independent of insertion order', () => {
    expect(buildCanonicalFixture(0).toIsonl()).toBe(buildCanonicalFixture(1).toIsonl());
  });

  it('toIson matches the shared cross-language golden fixture', () => {
    expect(buildCanonicalFixture(0).toIson()).toBe(CANONICAL_GOLDEN_ISON);
    expect(buildCanonicalFixture(1).toIson()).toBe(CANONICAL_GOLDEN_ISON);
  });

  it('toIsonl matches the shared cross-language golden fixture', () => {
    expect(buildCanonicalFixture(0).toIsonl()).toBe(CANONICAL_GOLDEN_ISONL);
    expect(buildCanonicalFixture(1).toIsonl()).toBe(CANONICAL_GOLDEN_ISONL);
  });

  it('sorts ids ordinally, not numerically ("1" < "10" < "2")', () => {
    const ison = buildCanonicalFixture(0).toIson();
    const personBlock = ison.split('nodes.person\n')[1].split('\n\n')[0];
    const ids = personBlock.split('\n').slice(1).map(line => line.split(' ')[0]);
    expect(ids).toEqual(['1', '10', '2']);
  });

  it('round-trip preserves canonical form', () => {
    const g = buildCanonicalFixture(0);
    const reloaded = ISONGraph.fromIson(g.toIson());
    expect(reloaded.toIson()).toBe(g.toIson());
  });
});

describe('Node', () => {
  it('should create node with properties', () => {
    const node = new Node('person', 1, { name: 'Alice' });
    expect(node.type).toBe('person');
    expect(node.id).toBe(1);
    expect(node.ref).toEqual(['person', 1]);
    expect(node.toIsonRef()).toBe(':person:1');
  });
});

describe('Edge', () => {
  it('should create edge with properties', () => {
    const edge = new Edge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
    expect(edge.relType).toBe('KNOWS');
    expect(edge.source).toEqual(['person', 1]);
    expect(edge.target).toEqual(['person', 2]);
  });
});

describe('Path', () => {
  it('should track path properties', () => {
    const path = new Path(
      [['person', 1], ['person', 2], ['person', 3]],
      [
        new Edge('KNOWS', ['person', 1], ['person', 2]),
        new Edge('KNOWS', ['person', 2], ['person', 3])
      ]
    );

    expect(path.length).toBe(2);
    expect(path.start).toEqual(['person', 1]);
    expect(path.end).toEqual(['person', 3]);
  });
});
