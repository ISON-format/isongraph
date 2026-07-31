/**
 * ISONGraph - A Token-Efficient Graph Store for TypeScript
 *
 * A property graph implementation with ISON persistence.
 * Supports multi-hop traversal, path finding, and fluent API.
 *
 * @example
 * ```typescript
 * import { ISONGraph, Direction } from 'ison-graph-ts';
 *
 * const graph = new ISONGraph();
 * graph.addNode('person', 1, { name: 'Alice', age: 30 });
 * graph.addNode('person', 2, { name: 'Bob', age: 25 });
 * graph.addEdge('KNOWS', ['person', 1], ['person', 2], { since: 2020 });
 *
 * const friends = graph.neighbors(['person', 1], 'KNOWS');
 * const fof = graph.multiHop(['person', 1], 'KNOWS', 2);
 * ```
 *
 * @author Mahesh Vaikri
 * @version 1.0.0
 */

import { parse, Reference } from 'ison-ts';

export const VERSION = "1.0.0";

// =============================================================================
// Types
// =============================================================================

/** Node reference tuple: [type, id] */
export type NodeRef = [string, number | string];

/** Edge key tuple: [relType, source, target] */
export type EdgeKey = [string, NodeRef, NodeRef];

/** Node properties */
export type Properties = Record<string, any>;

/** Traversal direction */
export enum Direction {
  OUT = "out",
  IN = "in",
  BOTH = "both"
}

// =============================================================================
// Data Classes
// =============================================================================

/**
 * Represents a graph node with properties
 */
export class Node {
  constructor(
    public readonly type: string,
    public readonly id: number | string,
    public properties: Properties = {}
  ) {}

  /** Get node reference tuple */
  get ref(): NodeRef {
    return [this.type, this.id];
  }

  /** Convert to ISON reference string */
  toIsonRef(): string {
    return `:${this.type}:${this.id}`;
  }

  /** Create unique key for maps */
  get key(): string {
    return `${this.type}:${this.id}`;
  }

  toString(): string {
    return `Node(${this.type}:${this.id}, ${JSON.stringify(this.properties)})`;
  }
}

/**
 * Represents a graph edge with properties
 */
export class Edge {
  constructor(
    public readonly relType: string,
    public readonly source: NodeRef,
    public readonly target: NodeRef,
    public properties: Properties = {}
  ) {}

  /** Get edge key tuple */
  get edgeKey(): EdgeKey {
    return [this.relType, this.source, this.target];
  }

  /** Create unique string key for sets */
  get key(): string {
    return `${this.relType}:${this.source[0]}:${this.source[1]}:${this.target[0]}:${this.target[1]}`;
  }

  toString(): string {
    return `Edge(${nodeRefToString(this.source)} -[${this.relType}]-> ${nodeRefToString(this.target)})`;
  }
}

/**
 * Represents a path through the graph
 */
export class Path {
  constructor(
    public readonly nodes: NodeRef[],
    public readonly edges: Edge[]
  ) {}

  /** Number of hops in the path */
  get length(): number {
    return this.edges.length;
  }

  /** Starting node */
  get start(): NodeRef | null {
    return this.nodes.length > 0 ? this.nodes[0] : null;
  }

  /** Ending node */
  get end(): NodeRef | null {
    return this.nodes.length > 0 ? this.nodes[this.nodes.length - 1] : null;
  }

  toString(): string {
    const pathStr = this.nodes.map(n => `:${n[0]}:${n[1]}`).join(" -> ");
    return `Path(${pathStr})`;
  }
}

// =============================================================================
// Errors
// =============================================================================

export class GraphError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GraphError";
  }
}

export class NodeNotFoundError extends GraphError {
  constructor(public readonly nodeRef: NodeRef) {
    super(`Node not found: :${nodeRef[0]}:${nodeRef[1]}`);
    this.name = "NodeNotFoundError";
  }
}

export class EdgeNotFoundError extends GraphError {
  constructor(public readonly edgeKey: EdgeKey) {
    super(`Edge not found: ${edgeKey}`);
    this.name = "EdgeNotFoundError";
  }
}

export class DuplicateNodeError extends GraphError {
  constructor(public readonly nodeRef: NodeRef) {
    super(`Node already exists: :${nodeRef[0]}:${nodeRef[1]}`);
    this.name = "DuplicateNodeError";
  }
}

export class DuplicateEdgeError extends GraphError {
  constructor(public readonly edgeKey: EdgeKey) {
    super(`Edge already exists: ${edgeKey}`);
    this.name = "DuplicateEdgeError";
  }
}

/**
 * Node type, node id, or relationship type contains a reserved character.
 * ':' and '|' are structurally significant to the wire format (':' delimits
 * `:type:id` references, '|' delimits ISONL columns); allowing them in an
 * identifier makes the graph unparseable after a toIson()/toIsonl()
 * round-trip instead of just failing loudly here.
 */
export class InvalidIdentifierError extends GraphError {
  constructor(public readonly kind: string, public readonly value: string) {
    super(`${kind} must not contain ':' or '|': ${JSON.stringify(value)}`);
    this.name = "InvalidIdentifierError";
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

/** Convert NodeRef to string key */
function nodeRefToKey(ref: NodeRef): string {
  return `${ref[0]}:${ref[1]}`;
}

/** Convert NodeRef to display string */
function nodeRefToString(ref: NodeRef): string {
  return `:${ref[0]}:${ref[1]}`;
}

/** Compare two NodeRefs for equality */
function nodeRefsEqual(a: NodeRef, b: NodeRef): boolean {
  return a[0] === b[0] && String(a[1]) === String(b[1]);
}

/** Convert edge to unique key string */
function edgeToKey(relType: string, source: NodeRef, target: NodeRef): string {
  return `${relType}:${source[0]}:${source[1]}:${target[0]}:${target[1]}`;
}

/** Split an ISONL line into header|fields|values sections, quote-aware */
function splitIsonlSections(line: string): string[] {
  const sections: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"' && (i === 0 || line[i - 1] !== "\\")) {
      inQuotes = !inQuotes;
      current += ch;
    } else if (ch === "|" && !inQuotes) {
      sections.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  sections.push(current.trim());

  return sections;
}

// =============================================================================
// ISONGraph - Main Graph Class
// =============================================================================

/**
 * In-memory property graph store with ISON persistence.
 *
 * Features:
 * - Property graph model (nodes and edges with properties)
 * - Multiple node types and relationship types
 * - O(1) node lookup by (type, id)
 * - Multi-hop traversal
 * - Shortest path finding (BFS)
 * - All paths finding (DFS)
 * - ISON/ISONL persistence
 */
export class ISONGraph {
  /** Graph name */
  public name: string;

  /** Whether edges are directed */
  public directed: boolean;

  /** Node storage: Map<type, Map<id, Node>> */
  private _nodes: Map<string, Map<string | number, Node>> = new Map();

  /** Edge storage: Map<relType, Edge[]> */
  private _edges: Map<string, Edge[]> = new Map();

  /** Index: outgoing edges per node */
  private _outEdges: Map<string, Edge[]> = new Map();

  /** Index: incoming edges per node */
  private _inEdges: Map<string, Edge[]> = new Map();

  /** Edge uniqueness set */
  private _edgeSet: Set<string> = new Set();

  constructor(name: string = "graph", directed: boolean = true) {
    this.name = name;
    this.directed = directed;
  }

  // =========================================================================
  // Node Operations
  // =========================================================================

  /**
   * Reject ':' or '|' in a node type, node id, or relationship type. Both
   * are structurally significant to the wire format (':' delimits
   * `:type:id` references, '|' delimits ISONL columns); allowing them here
   * would build a graph that throws on toIson()/toIsonl() round-trip
   * instead of failing at construction.
   */
  private static _checkIdentifier(kind: string, value: string | number): void {
    const s = String(value);
    if (s.includes(':') || s.includes('|')) {
      throw new InvalidIdentifierError(kind, s);
    }
  }

  /**
   * Add a node to the graph.
   * @param nodeType Type of node (e.g., 'person', 'company')
   * @param nodeId Unique ID within the type
   * @param properties Node properties
   * @returns The created Node
   * @throws InvalidIdentifierError if nodeType or nodeId contains ':' or '|'
   * @throws DuplicateNodeError if node already exists
   */
  addNode(nodeType: string, nodeId: number | string, properties: Properties = {}): Node {
    ISONGraph._checkIdentifier('Node type', nodeType);
    ISONGraph._checkIdentifier('Node id', nodeId);

    if (!this._nodes.has(nodeType)) {
      this._nodes.set(nodeType, new Map());
    }

    const typeNodes = this._nodes.get(nodeType)!;
    if (typeNodes.has(nodeId)) {
      throw new DuplicateNodeError([nodeType, nodeId]);
    }

    const node = new Node(nodeType, nodeId, properties);
    typeNodes.set(nodeId, node);
    return node;
  }

  /**
   * Get a node by type and ID.
   * @throws NodeNotFoundError if node doesn't exist
   */
  getNode(nodeType: string, nodeId: number | string): Node {
    const typeNodes = this._nodes.get(nodeType);
    if (!typeNodes || !typeNodes.has(nodeId)) {
      throw new NodeNotFoundError([nodeType, nodeId]);
    }
    return typeNodes.get(nodeId)!;
  }

  /** Get node by reference tuple */
  getNodeByRef(ref: NodeRef): Node {
    return this.getNode(ref[0], ref[1]);
  }

  /** Check if node exists */
  hasNode(nodeType: string, nodeId: number | string): boolean {
    const typeNodes = this._nodes.get(nodeType);
    return typeNodes !== undefined && typeNodes.has(nodeId);
  }

  /**
   * Remove a node and all its edges.
   * @throws NodeNotFoundError if node doesn't exist
   */
  removeNode(nodeType: string, nodeId: number | string): void {
    const ref: NodeRef = [nodeType, nodeId];
    if (!this.hasNode(nodeType, nodeId)) {
      throw new NodeNotFoundError(ref);
    }

    const refKey = nodeRefToKey(ref);

    // Remove all edges connected to this node
    const outEdges = this._outEdges.get(refKey) || [];
    const inEdges = this._inEdges.get(refKey) || [];
    const edgesToRemove = [...outEdges, ...inEdges];

    for (const edge of edgesToRemove) {
      this._removeEdgeInternal(edge);
    }

    // Remove node
    const typeNodes = this._nodes.get(nodeType)!;
    typeNodes.delete(nodeId);
    if (typeNodes.size === 0) {
      this._nodes.delete(nodeType);
    }
  }

  /** Update node properties */
  updateNode(nodeType: string, nodeId: number | string, properties: Properties): Node {
    const node = this.getNode(nodeType, nodeId);
    Object.assign(node.properties, properties);
    return node;
  }

  /** Iterate over nodes, optionally filtered by type */
  *nodes(nodeType?: string): Generator<Node> {
    if (nodeType) {
      const typeNodes = this._nodes.get(nodeType);
      if (typeNodes) {
        yield* typeNodes.values();
      }
    } else {
      for (const typeNodes of this._nodes.values()) {
        yield* typeNodes.values();
      }
    }
  }

  /** Count nodes, optionally filtered by type */
  nodeCount(nodeType?: string): number {
    if (nodeType) {
      return this._nodes.get(nodeType)?.size ?? 0;
    }
    let count = 0;
    for (const typeNodes of this._nodes.values()) {
      count += typeNodes.size;
    }
    return count;
  }

  /** Get all node types in the graph */
  nodeTypes(): string[] {
    return Array.from(this._nodes.keys());
  }

  // =========================================================================
  // Edge Operations
  // =========================================================================

  /**
   * Add an edge to the graph.
   * @param relType Relationship type (e.g., 'KNOWS', 'WORKS_AT')
   * @param source Source node reference [type, id]
   * @param target Target node reference [type, id]
   * @param properties Edge properties
   * @returns The created Edge
   * @throws InvalidIdentifierError if relType contains ':' or '|'
   * @throws NodeNotFoundError if source or target doesn't exist
   * @throws DuplicateEdgeError if edge already exists
   */
  addEdge(relType: string, source: NodeRef, target: NodeRef, properties: Properties = {}): Edge {
    ISONGraph._checkIdentifier('Relationship type', relType);

    // Validate nodes exist
    if (!this.hasNode(source[0], source[1])) {
      throw new NodeNotFoundError(source);
    }
    if (!this.hasNode(target[0], target[1])) {
      throw new NodeNotFoundError(target);
    }

    const edgeKey = edgeToKey(relType, source, target);
    if (this._edgeSet.has(edgeKey)) {
      throw new DuplicateEdgeError([relType, source, target]);
    }

    const edge = new Edge(relType, source, target, properties);

    // Add to storage
    if (!this._edges.has(relType)) {
      this._edges.set(relType, []);
    }
    this._edges.get(relType)!.push(edge);

    const sourceKey = nodeRefToKey(source);
    const targetKey = nodeRefToKey(target);

    if (!this._outEdges.has(sourceKey)) {
      this._outEdges.set(sourceKey, []);
    }
    this._outEdges.get(sourceKey)!.push(edge);

    if (!this._inEdges.has(targetKey)) {
      this._inEdges.set(targetKey, []);
    }
    this._inEdges.get(targetKey)!.push(edge);

    this._edgeSet.add(edgeKey);

    // For undirected graphs, add reverse edge
    if (!this.directed) {
      const reverseKey = edgeToKey(relType, target, source);
      if (!this._edgeSet.has(reverseKey)) {
        const reverseEdge = new Edge(relType, target, source, properties);
        this._edges.get(relType)!.push(reverseEdge);

        if (!this._outEdges.has(targetKey)) {
          this._outEdges.set(targetKey, []);
        }
        this._outEdges.get(targetKey)!.push(reverseEdge);

        if (!this._inEdges.has(sourceKey)) {
          this._inEdges.set(sourceKey, []);
        }
        this._inEdges.get(sourceKey)!.push(reverseEdge);

        this._edgeSet.add(reverseKey);
      }
    }

    return edge;
  }

  /** Internal method to remove an edge */
  private _removeEdgeInternal(edge: Edge): void {
    const edgeKey = edge.key;
    if (!this._edgeSet.has(edgeKey)) {
      return;
    }

    this._edgeSet.delete(edgeKey);

    // Remove from _edges
    const relEdges = this._edges.get(edge.relType);
    if (relEdges) {
      const idx = relEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        relEdges.splice(idx, 1);
      }
    }

    // Remove from _outEdges
    const sourceKey = nodeRefToKey(edge.source);
    const outEdges = this._outEdges.get(sourceKey);
    if (outEdges) {
      const idx = outEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        outEdges.splice(idx, 1);
      }
    }

    // Remove from _inEdges
    const targetKey = nodeRefToKey(edge.target);
    const inEdges = this._inEdges.get(targetKey);
    if (inEdges) {
      const idx = inEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        inEdges.splice(idx, 1);
      }
    }
  }

  /** Remove an edge from the graph */
  removeEdge(relType: string, source: NodeRef, target: NodeRef): void {
    const edgeKey = edgeToKey(relType, source, target);
    if (!this._edgeSet.has(edgeKey)) {
      throw new EdgeNotFoundError([relType, source, target]);
    }

    const relEdges = this._edges.get(relType) || [];
    for (const edge of relEdges) {
      if (edge.key === edgeKey) {
        this._removeEdgeInternal(edge);
        break;
      }
    }

    // For undirected graphs, also remove the auto-added reverse edge
    if (!this.directed) {
      const reverseKey = edgeToKey(relType, target, source);
      if (this._edgeSet.has(reverseKey)) {
        const reverseEdges = this._edges.get(relType) || [];
        for (const edge of reverseEdges) {
          if (edge.key === reverseKey) {
            this._removeEdgeInternal(edge);
            break;
          }
        }
      }
    }
  }

  /** Check if edge exists */
  hasEdge(relType: string, source: NodeRef, target: NodeRef): boolean {
    return this._edgeSet.has(edgeToKey(relType, source, target));
  }

  /** Get an edge by its components */
  getEdge(relType: string, source: NodeRef, target: NodeRef): Edge {
    const edgeKey = edgeToKey(relType, source, target);
    if (!this._edgeSet.has(edgeKey)) {
      throw new EdgeNotFoundError([relType, source, target]);
    }

    const relEdges = this._edges.get(relType) || [];
    for (const edge of relEdges) {
      if (edge.key === edgeKey) {
        return edge;
      }
    }
    throw new EdgeNotFoundError([relType, source, target]);
  }

  /** Iterate over edges with optional filters */
  *edges(relType?: string, source?: NodeRef, target?: NodeRef): Generator<Edge> {
    let edgeList: Edge[];

    if (source) {
      edgeList = this._outEdges.get(nodeRefToKey(source)) || [];
    } else if (target) {
      edgeList = this._inEdges.get(nodeRefToKey(target)) || [];
    } else if (relType) {
      edgeList = this._edges.get(relType) || [];
    } else {
      edgeList = [];
      for (const edges of this._edges.values()) {
        edgeList.push(...edges);
      }
    }

    for (const edge of edgeList) {
      if (relType && edge.relType !== relType) continue;
      if (source && !nodeRefsEqual(edge.source, source)) continue;
      if (target && !nodeRefsEqual(edge.target, target)) continue;
      yield edge;
    }
  }

  /** Count edges, optionally filtered by type */
  edgeCount(relType?: string): number {
    if (relType) {
      return this._edges.get(relType)?.length ?? 0;
    }
    return this._edgeSet.size;
  }

  /** Get all edge/relationship types in the graph */
  edgeTypes(): string[] {
    return Array.from(this._edges.keys());
  }

  // =========================================================================
  // Traversal Operations
  // =========================================================================

  /**
   * Get neighboring nodes.
   * @param nodeRef Starting node reference
   * @param relType Filter by relationship type (optional)
   * @param direction OUT (default), IN, or BOTH
   * @returns List of neighbor node references
   */
  neighbors(
    nodeRef: NodeRef,
    relType?: string,
    direction: Direction = Direction.OUT
  ): NodeRef[] {
    const neighbors: NodeRef[] = [];
    const refKey = nodeRefToKey(nodeRef);

    if (direction === Direction.OUT || direction === Direction.BOTH) {
      const outEdges = this._outEdges.get(refKey) || [];
      for (const edge of outEdges) {
        if (relType === undefined || edge.relType === relType) {
          neighbors.push(edge.target);
        }
      }
    }

    if (direction === Direction.IN || direction === Direction.BOTH) {
      const inEdges = this._inEdges.get(refKey) || [];
      for (const edge of inEdges) {
        if (relType === undefined || edge.relType === relType) {
          neighbors.push(edge.source);
        }
      }
    }

    return neighbors;
  }

  /**
   * Get nodes N hops away.
   * @param start Starting node reference
   * @param relType Relationship type to follow (optional)
   * @param hops Number of hops (default: 1)
   * @param direction Traversal direction
   * @returns List of nodes exactly N hops away
   */
  multiHop(
    start: NodeRef,
    relType?: string,
    hops: number = 1,
    direction: Direction = Direction.OUT
  ): NodeRef[] {
    if (hops < 1) {
      return [start];
    }

    let current = new Set([nodeRefToKey(start)]);
    const visited = new Set([nodeRefToKey(start)]);
    const refMap = new Map<string, NodeRef>([[nodeRefToKey(start), start]]);

    for (let i = 0; i < hops; i++) {
      const nextLevel = new Set<string>();

      for (const key of current) {
        const nodeRef = refMap.get(key)!;
        const neighborRefs = this.neighbors(nodeRef, relType, direction);

        for (const neighbor of neighborRefs) {
          const neighborKey = nodeRefToKey(neighbor);
          if (!visited.has(neighborKey)) {
            nextLevel.add(neighborKey);
            refMap.set(neighborKey, neighbor);
          }
        }
      }

      for (const key of nextLevel) {
        visited.add(key);
      }
      current = nextLevel;
    }

    return Array.from(current).map(key => refMap.get(key)!);
  }

  /**
   * Get nodes within a range of hops.
   * @param start Starting node
   * @param relType Relationship type (optional)
   * @param minHops Minimum hops (inclusive)
   * @param maxHops Maximum hops (inclusive)
   * @param direction Traversal direction
   * @returns List of nodes within hop range
   */
  multiHopRange(
    start: NodeRef,
    relType?: string,
    minHops: number = 1,
    maxHops: number = 3,
    direction: Direction = Direction.OUT
  ): NodeRef[] {
    const result = new Set<string>();
    let current = new Set([nodeRefToKey(start)]);
    const visited = new Set([nodeRefToKey(start)]);
    const refMap = new Map<string, NodeRef>([[nodeRefToKey(start), start]]);

    for (let hop = 1; hop <= maxHops; hop++) {
      const nextLevel = new Set<string>();

      for (const key of current) {
        const nodeRef = refMap.get(key)!;
        const neighborRefs = this.neighbors(nodeRef, relType, direction);

        for (const neighbor of neighborRefs) {
          const neighborKey = nodeRefToKey(neighbor);
          if (!visited.has(neighborKey)) {
            nextLevel.add(neighborKey);
            refMap.set(neighborKey, neighbor);
            if (hop >= minHops) {
              result.add(neighborKey);
            }
          }
        }
      }

      for (const key of nextLevel) {
        visited.add(key);
      }
      current = nextLevel;

      if (current.size === 0) {
        break;
      }
    }

    return Array.from(result).map(key => refMap.get(key)!);
  }

  /**
   * Traverse graph following a pattern of relationship types.
   * @param start Starting node
   * @param pattern List of [relType, direction] tuples defining the path
   * @param filterFn Optional filter function applied at each step
   * @returns List of nodes reached after following the pattern
   */
  traverse(
    start: NodeRef,
    pattern: Array<[string, Direction]>,
    filterFn?: (node: Node) => boolean
  ): NodeRef[] {
    let current = new Set([nodeRefToKey(start)]);
    const refMap = new Map<string, NodeRef>([[nodeRefToKey(start), start]]);

    for (const [relType, direction] of pattern) {
      const nextLevel = new Set<string>();

      for (const key of current) {
        const nodeRef = refMap.get(key)!;
        const neighborRefs = this.neighbors(nodeRef, relType, direction);

        for (const neighbor of neighborRefs) {
          const neighborKey = nodeRefToKey(neighbor);
          if (filterFn === undefined) {
            nextLevel.add(neighborKey);
            refMap.set(neighborKey, neighbor);
          } else {
            const node = this.getNodeByRef(neighbor);
            if (filterFn(node)) {
              nextLevel.add(neighborKey);
              refMap.set(neighborKey, neighbor);
            }
          }
        }
      }

      current = nextLevel;
      if (current.size === 0) {
        break;
      }
    }

    return Array.from(current).map(key => refMap.get(key)!);
  }

  // =========================================================================
  // Path Finding
  // =========================================================================

  /**
   * Find shortest path between two nodes using BFS.
   * @param start Starting node
   * @param end Target node
   * @param relType Relationship type to follow (optional)
   * @param maxHops Maximum path length
   * @param direction Traversal direction
   * @returns Path object or null if no path exists
   */
  shortestPath(
    start: NodeRef,
    end: NodeRef,
    relType?: string,
    maxHops: number = 10,
    direction: Direction = Direction.OUT
  ): Path | null {
    if (nodeRefsEqual(start, end)) {
      return new Path([start], []);
    }

    const endKey = nodeRefToKey(end);
    const visited = new Set([nodeRefToKey(start)]);

    interface QueueItem {
      current: NodeRef;
      pathNodes: NodeRef[];
      pathEdges: Edge[];
    }

    const queue: QueueItem[] = [{ current: start, pathNodes: [start], pathEdges: [] }];

    while (queue.length > 0) {
      const { current, pathNodes, pathEdges } = queue.shift()!;

      // A path of N nodes has N-1 edges; only expand it while adding one
      // more edge stays within maxHops
      if (pathNodes.length > maxHops) {
        continue;
      }

      const currentKey = nodeRefToKey(current);

      if (direction !== Direction.IN) {
        const outEdges = this._outEdges.get(currentKey) || [];
        for (const edge of outEdges) {
          if (relType && edge.relType !== relType) continue;

          const targetKey = nodeRefToKey(edge.target);
          if (targetKey === endKey) {
            return new Path([...pathNodes, edge.target], [...pathEdges, edge]);
          }
          if (!visited.has(targetKey)) {
            visited.add(targetKey);
            queue.push({
              current: edge.target,
              pathNodes: [...pathNodes, edge.target],
              pathEdges: [...pathEdges, edge]
            });
          }
        }
      }

      if (direction === Direction.IN || direction === Direction.BOTH) {
        const inEdges = this._inEdges.get(currentKey) || [];
        for (const edge of inEdges) {
          if (relType && edge.relType !== relType) continue;

          const sourceKey = nodeRefToKey(edge.source);
          if (sourceKey === endKey) {
            return new Path([...pathNodes, edge.source], [...pathEdges, edge]);
          }
          if (!visited.has(sourceKey)) {
            visited.add(sourceKey);
            queue.push({
              current: edge.source,
              pathNodes: [...pathNodes, edge.source],
              pathEdges: [...pathEdges, edge]
            });
          }
        }
      }
    }

    return null;
  }

  /**
   * Find all paths between two nodes using DFS.
   * @param start Starting node
   * @param end Target node
   * @param relType Relationship type (optional)
   * @param maxHops Maximum path length
   * @param direction Traversal direction
   * @returns List of all valid paths
   */
  allPaths(
    start: NodeRef,
    end: NodeRef,
    relType?: string,
    maxHops: number = 5,
    direction: Direction = Direction.OUT
  ): Path[] {
    const paths: Path[] = [];
    const endKey = nodeRefToKey(end);

    const dfs = (
      current: NodeRef,
      pathNodes: NodeRef[],
      pathEdges: Edge[],
      visited: Set<string>
    ): void => {
      if (pathNodes.length > maxHops + 1) {
        return;
      }

      const currentKey = nodeRefToKey(current);
      if (currentKey === endKey) {
        paths.push(new Path([...pathNodes], [...pathEdges]));
        return;
      }

      const edgesToFollow: Edge[] = [];
      if (direction === Direction.OUT || direction === Direction.BOTH) {
        edgesToFollow.push(...(this._outEdges.get(currentKey) || []));
      }
      if (direction === Direction.IN || direction === Direction.BOTH) {
        const inEdges = this._inEdges.get(currentKey) || [];
        for (const e of inEdges) {
          edgesToFollow.push(new Edge(e.relType, e.target, e.source, e.properties));
        }
      }

      for (const edge of edgesToFollow) {
        if (relType && edge.relType !== relType) continue;

        const nextKey = nodeRefToKey(edge.target);
        if (!visited.has(nextKey)) {
          visited.add(nextKey);
          pathNodes.push(edge.target);
          pathEdges.push(edge);
          dfs(edge.target, pathNodes, pathEdges, visited);
          pathNodes.pop();
          pathEdges.pop();
          visited.delete(nextKey);
        }
      }
    };

    dfs(start, [start], [], new Set([nodeRefToKey(start)]));
    return paths;
  }

  /** Check if a path exists between two nodes */
  pathExists(
    start: NodeRef,
    end: NodeRef,
    relType?: string,
    maxHops: number = 10
  ): boolean {
    return this.shortestPath(start, end, relType, maxHops) !== null;
  }

  // =========================================================================
  // Graph Analysis
  // =========================================================================

  /** Count incoming edges */
  inDegree(nodeRef: NodeRef): number {
    return (this._inEdges.get(nodeRefToKey(nodeRef)) || []).length;
  }

  /** Count outgoing edges */
  outDegree(nodeRef: NodeRef): number {
    return (this._outEdges.get(nodeRefToKey(nodeRef)) || []).length;
  }

  /** Total degree */
  degree(nodeRef: NodeRef): number {
    if (this.directed) {
      return this.inDegree(nodeRef) + this.outDegree(nodeRef);
    } else {
      const edges = new Set<string>();
      for (const e of this._outEdges.get(nodeRefToKey(nodeRef)) || []) {
        const key = [nodeRefToKey(e.source), nodeRefToKey(e.target)].sort().join("|");
        edges.add(key);
      }
      for (const e of this._inEdges.get(nodeRefToKey(nodeRef)) || []) {
        const key = [nodeRefToKey(e.source), nodeRefToKey(e.target)].sort().join("|");
        edges.add(key);
      }
      return edges.size;
    }
  }

  /** Check if graph is connected */
  isConnected(): boolean {
    const allNodes = Array.from(this.nodes());
    if (allNodes.length === 0) {
      return true;
    }

    const start = allNodes[0].ref;
    const visited = new Set([nodeRefToKey(start)]);
    const queue = [start];

    while (queue.length > 0) {
      const current = queue.shift()!;
      for (const neighbor of this.neighbors(current, undefined, Direction.BOTH)) {
        const neighborKey = nodeRefToKey(neighbor);
        if (!visited.has(neighborKey)) {
          visited.add(neighborKey);
          queue.push(neighbor);
        }
      }
    }

    return visited.size === allNodes.length;
  }

  /** Check if graph has cycles */
  hasCycle(relType?: string): boolean {
    const visited = new Set<string>();

    if (!this.directed) {
      // Undirected: DFS with parent-edge tracking so the auto-added reverse
      // edge is not mistaken for a cycle when walking back along the edge
      // we arrived on.
      const undirectedEdgeId = (edge: Edge): string => {
        const a = nodeRefToKey(edge.source);
        const b = nodeRefToKey(edge.target);
        return `${edge.relType}|${[a, b].sort().join("|")}`;
      };

      const dfsUndirected = (nodeRef: NodeRef, incomingEdgeId: string | null): boolean => {
        const key = nodeRefToKey(nodeRef);
        visited.add(key);

        const outEdges = this._outEdges.get(key) || [];
        for (const edge of outEdges) {
          if (relType !== undefined && edge.relType !== relType) continue;
          const edgeId = undirectedEdgeId(edge);
          if (edgeId === incomingEdgeId) continue;
          const neighborKey = nodeRefToKey(edge.target);
          if (visited.has(neighborKey)) {
            return true;
          }
          if (dfsUndirected(edge.target, edgeId)) {
            return true;
          }
        }
        return false;
      };

      for (const node of this.nodes()) {
        if (!visited.has(node.key)) {
          if (dfsUndirected(node.ref, null)) {
            return true;
          }
        }
      }

      return false;
    }

    const recStack = new Set<string>();

    const dfs = (nodeRef: NodeRef): boolean => {
      const key = nodeRefToKey(nodeRef);
      visited.add(key);
      recStack.add(key);

      for (const neighbor of this.neighbors(nodeRef, relType)) {
        const neighborKey = nodeRefToKey(neighbor);
        if (!visited.has(neighborKey)) {
          if (dfs(neighbor)) {
            return true;
          }
        } else if (recStack.has(neighborKey)) {
          return true;
        }
      }

      recStack.delete(key);
      return false;
    };

    for (const node of this.nodes()) {
      if (!visited.has(node.key)) {
        if (dfs(node.ref)) {
          return true;
        }
      }
    }

    return false;
  }

  /** Get all connected components */
  connectedComponents(): Set<string>[] {
    const visited = new Set<string>();
    const components: Set<string>[] = [];

    for (const node of this.nodes()) {
      if (!visited.has(node.key)) {
        const component = new Set<string>();
        const queue = [node.ref];

        while (queue.length > 0) {
          const current = queue.shift()!;
          const currentKey = nodeRefToKey(current);

          if (!visited.has(currentKey)) {
            visited.add(currentKey);
            component.add(currentKey);

            for (const neighbor of this.neighbors(current, undefined, Direction.BOTH)) {
              if (!visited.has(nodeRefToKey(neighbor))) {
                queue.push(neighbor);
              }
            }
          }
        }

        components.push(component);
      }
    }

    return components;
  }

  // =========================================================================
  // Serialization (ISON/ISONL)
  // =========================================================================

  /** Convert value to ISON string representation */
  private _valueToIson(value: any): string {
    if (value === null || value === undefined) {
      return "null";
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    if (typeof value === "string") {
      // Standardized ISON quoting rule: double-quote when the value contains
      // a space, '|', '"', a newline, or is empty; escape '"' as \" and
      // newline as \n so fromIson/fromIsonl can reverse it losslessly.
      if (
        value === "" ||
        value.includes(" ") ||
        value.includes("|") ||
        value.includes('"') ||
        value.includes("\n")
      ) {
        const escaped = value.replace(/"/g, '\\"').replace(/\n/g, '\\n');
        return `"${escaped}"`;
      }
      return value;
    }
    return String(value);
  }

  /** Sorted node rows within a type block: ordinal comparison of String(id). */
  private static _sortedNodes(typeNodes: Map<string | number, Node>): Node[] {
    return Array.from(typeNodes.values()).sort((a, b) => {
      const ka = String(a.id), kb = String(b.id);
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }

  /** Sorted edge rows within a rel_type block: ordinal (sourceType, sourceId, targetType, targetId). */
  private static _sortedEdges(edges: Edge[]): Edge[] {
    return [...edges].sort((a, b) => {
      const ka = [a.source[0], String(a.source[1]), a.target[0], String(a.target[1])];
      const kb = [b.source[0], String(b.source[1]), b.target[0], String(b.target[1])];
      for (let i = 0; i < 4; i++) {
        if (ka[i] < kb[i]) return -1;
        if (ka[i] > kb[i]) return 1;
      }
      return 0;
    });
  }

  /**
   * Serialize graph to ISON format.
   *
   * Serialization is canonical: node type blocks, node rows within a block,
   * edge type blocks, and edge rows within a block are all sorted (ordinal
   * string comparison), independent of insertion order. The same logical
   * graph always serializes to the same bytes, regardless of construction
   * history.
   */
  toIson(): string {
    const blocks: string[] = [];

    // Serialize nodes by type
    const nodeTypes = Array.from(this._nodes.keys()).sort();
    for (const nodeType of nodeTypes) {
      const typeNodes = this._nodes.get(nodeType)!;
      if (typeNodes.size === 0) continue;
      const sortedTypeNodes = ISONGraph._sortedNodes(typeNodes);

      // Collect all property keys
      const propKeys = new Set<string>();
      for (const node of sortedTypeNodes) {
        for (const key of Object.keys(node.properties)) {
          propKeys.add(key);
        }
      }
      const sortedPropKeys = Array.from(propKeys).sort();

      // Build block
      const lines: string[] = [`nodes.${nodeType}`];
      lines.push(["id", ...sortedPropKeys].join(" "));

      for (const node of sortedTypeNodes) {
        const values = [String(node.id)];
        for (const key of sortedPropKeys) {
          values.push(this._valueToIson(node.properties[key]));
        }
        lines.push(values.join(" "));
      }

      blocks.push(lines.join("\n"));
    }

    // Serialize edges by type
    const edgeTypes = Array.from(this._edges.keys()).sort();
    for (const relType of edgeTypes) {
      const edges = this._edges.get(relType)!;
      if (edges.length === 0) continue;
      const sortedTypeEdges = ISONGraph._sortedEdges(edges);

      // Collect all property keys
      const propKeys = new Set<string>();
      for (const edge of sortedTypeEdges) {
        for (const key of Object.keys(edge.properties)) {
          propKeys.add(key);
        }
      }
      const sortedPropKeys = Array.from(propKeys).sort();

      // Build block
      const lines: string[] = [`edges.${relType}`];
      lines.push(["source", "target", ...sortedPropKeys].join(" "));

      for (const edge of sortedTypeEdges) {
        const sourceRef = `:${edge.source[0]}:${edge.source[1]}`;
        const targetRef = `:${edge.target[0]}:${edge.target[1]}`;
        const values = [sourceRef, targetRef];
        for (const key of sortedPropKeys) {
          values.push(this._valueToIson(edge.properties[key]));
        }
        lines.push(values.join(" "));
      }

      blocks.push(lines.join("\n"));
    }

    return blocks.join("\n\n");
  }

  /**
   * Serialize graph to ISONL streaming format.
   *
   * Row order is canonical, matching {@link toIson} - see there for the
   * exact ordering rule.
   */
  toIsonl(): string {
    const lines: string[] = [];

    // Serialize nodes (type blocks, then rows, both sorted)
    const nodeTypes = Array.from(this._nodes.keys()).sort();
    for (const nodeType of nodeTypes) {
      const typeNodes = this._nodes.get(nodeType)!;
      for (const node of ISONGraph._sortedNodes(typeNodes)) {
        const propKeys = Object.keys(node.properties).sort();
        const fields = ["id", ...propKeys];
        const values = [String(node.id), ...propKeys.map(k => this._valueToIson(node.properties[k]))];
        lines.push(`nodes.${node.type}|${fields.join(" ")}|${values.join(" ")}`);
      }
    }

    // Serialize edges (type blocks, then rows, both sorted)
    const edgeTypes = Array.from(this._edges.keys()).sort();
    for (const relType of edgeTypes) {
      const edges = this._edges.get(relType)!;
      for (const edge of ISONGraph._sortedEdges(edges)) {
        const propKeys = Object.keys(edge.properties).sort();
        const fields = ["source", "target", ...propKeys];
        const sourceRef = `:${edge.source[0]}:${edge.source[1]}`;
        const targetRef = `:${edge.target[0]}:${edge.target[1]}`;
        const values = [sourceRef, targetRef, ...propKeys.map(k => this._valueToIson(edge.properties[k]))];
        lines.push(`edges.${relType}|${fields.join(" ")}|${values.join(" ")}`);
      }
    }

    return lines.join("\n");
  }

  /**
   * Parse graph from ISON format.
   */
  static fromIson(text: string, name: string = "graph"): ISONGraph {
    const graph = new ISONGraph(name);
    const doc = parse(text);

    for (const block of doc.blocks) {
      if (block.kind === "nodes") {
        const nodeType = block.name;
        for (const row of block.rows) {
          const nodeId = row.id as number | string;
          const props: Properties = {};
          for (const [k, v] of Object.entries(row)) {
            if (k !== "id") {
              props[k] = v instanceof Reference ? [v.type, v.id] : v;
            }
          }
          graph.addNode(nodeType, nodeId, props);
        }
      } else if (block.kind === "edges") {
        const relType = block.name;
        for (const row of block.rows) {
          let source = row.source as any;
          let target = row.target as any;

          // Convert Reference objects to tuples
          if (source instanceof Reference) {
            const id = /^\d+$/.test(source.id) ? parseInt(source.id, 10) : source.id;
            source = [source.type, id] as NodeRef;
          }
          if (target instanceof Reference) {
            const id = /^\d+$/.test(target.id) ? parseInt(target.id, 10) : target.id;
            target = [target.type, id] as NodeRef;
          }

          const props: Properties = {};
          for (const [k, v] of Object.entries(row)) {
            if (k !== "source" && k !== "target") {
              props[k] = v instanceof Reference ? [v.type, v.id] : v;
            }
          }
          graph.addEdge(relType, source, target, props);
        }
      }
    }

    return graph;
  }

  /** Parse graph from ISONL format */
  static fromIsonl(text: string, name: string = "graph"): ISONGraph {
    // ison-ts's ISONL loader splits lines on '|' without quote awareness,
    // which corrupts quoted values containing '|'. Rebuild each ISONL line
    // as an ISON block (quote-aware split) and reuse the ISON parser so the
    // standardized quoting rule round-trips losslessly.
    const blockTexts: string[] = [];
    for (const rawLine of text.split("\n")) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const sections = splitIsonlSections(line);
      if (sections.length !== 3) {
        throw new GraphError(`Invalid ISONL line: ${rawLine}`);
      }
      blockTexts.push(`${sections[0]}\n${sections[1]}\n${sections[2]}`);
    }

    return ISONGraph.fromIson(blockTexts.join("\n\n"), name);
  }

  /** Alias for fromIson */
  static parse(text: string, name: string = "graph"): ISONGraph {
    return ISONGraph.fromIson(text, name);
  }

  // =========================================================================
  // Query Interface (Fluent API)
  // =========================================================================

  /**
   * Start a fluent traversal from a node.
   * @example
   * graph.start(['person', 1])
   *   .hop('KNOWS')
   *   .hop('WORKS_AT')
   *   .collect()
   */
  start(nodeRef: NodeRef): GraphTraversal {
    return new GraphTraversal(this, nodeRef);
  }

  /**
   * Execute a simple pattern query.
   *
   * Pattern syntax:
   *   :type:id -[:REL]-> *
   *   :type:id -[:REL*N]-> *  (N hops)
   *   :type:id -[:REL*1..3]-> *  (1-3 hops)
   */
  query(pattern: string): NodeRef[] {
    pattern = pattern.trim();

    // Match: :type:id -[:REL*N]-> *
    const hopMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*/);
    if (hopMatch) {
      const [, nodeType, nodeIdStr, relType, hopsStr] = hopMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.multiHop([nodeType, nodeId], relType, parseInt(hopsStr, 10));
    }

    // Match: :type:id -[:REL*N..M]-> *
    const rangeMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*/);
    if (rangeMatch) {
      const [, nodeType, nodeIdStr, relType, minStr, maxStr] = rangeMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.multiHopRange([nodeType, nodeId], relType, parseInt(minStr, 10), parseInt(maxStr, 10));
    }

    // Match: :type:id -[:REL]-> *
    const simpleMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\]->\s*\*/);
    if (simpleMatch) {
      const [, nodeType, nodeIdStr, relType] = simpleMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.neighbors([nodeType, nodeId], relType);
    }

    throw new Error(`Invalid query pattern: ${pattern}`);
  }

  toString(): string {
    return `ISONGraph(name=${this.name}, nodes=${this.nodeCount()}, edges=${this.edgeCount()})`;
  }
}

// =============================================================================
// Fluent Traversal API
// =============================================================================

/**
 * Fluent API for graph traversal
 */
export class GraphTraversal {
  private _graph: ISONGraph;
  private _current: Set<string>;
  private _visited: Set<string>;
  private _refMap: Map<string, NodeRef>;

  constructor(graph: ISONGraph, start: NodeRef) {
    this._graph = graph;
    const startKey = nodeRefToKey(start);
    this._current = new Set([startKey]);
    this._visited = new Set([startKey]);
    this._refMap = new Map([[startKey, start]]);
  }

  /**
   * Traverse one hop following edges.
   */
  hop(
    relType?: string,
    direction: Direction = Direction.OUT,
    where?: (node: Node) => boolean
  ): GraphTraversal {
    const nextLevel = new Set<string>();

    for (const key of this._current) {
      const nodeRef = this._refMap.get(key)!;
      const neighbors = this._graph.neighbors(nodeRef, relType, direction);

      for (const neighbor of neighbors) {
        const neighborKey = nodeRefToKey(neighbor);
        if (!this._visited.has(neighborKey)) {
          if (where === undefined) {
            nextLevel.add(neighborKey);
            this._refMap.set(neighborKey, neighbor);
          } else {
            const node = this._graph.getNodeByRef(neighbor);
            if (where(node)) {
              nextLevel.add(neighborKey);
              this._refMap.set(neighborKey, neighbor);
            }
          }
        }
      }
    }

    for (const key of nextLevel) {
      this._visited.add(key);
    }
    this._current = nextLevel;
    return this;
  }

  /** Traverse N hops */
  hops(
    n: number,
    relType?: string,
    direction: Direction = Direction.OUT
  ): GraphTraversal {
    for (let i = 0; i < n; i++) {
      this.hop(relType, direction);
    }
    return this;
  }

  /** Filter current nodes */
  filter(fn: (node: Node) => boolean): GraphTraversal {
    const filtered = new Set<string>();
    for (const key of this._current) {
      const ref = this._refMap.get(key)!;
      if (fn(this._graph.getNodeByRef(ref))) {
        filtered.add(key);
      }
    }
    this._current = filtered;
    return this;
  }

  /** Return current nodes as list */
  collect(): NodeRef[] {
    return Array.from(this._current).map(key => this._refMap.get(key)!);
  }

  /** Return current nodes as Node objects */
  collectNodes(): Node[] {
    return this.collect().map(ref => this._graph.getNodeByRef(ref));
  }

  /** Count current nodes */
  count(): number {
    return this._current.size;
  }

  /** Get first node or null */
  first(): NodeRef | null {
    const firstKey = this._current.values().next().value;
    return firstKey ? this._refMap.get(firstKey) ?? null : null;
  }
}

// =============================================================================
// Exports
// =============================================================================

export {
  nodeRefToKey,
  nodeRefToString,
  nodeRefsEqual,
  edgeToKey
};

// Query Module (ISONQL)
export * from './query';

// Schema Validation Module
export * from './schema';

// Visualization Module (deterministic layout + SVG/HTML rendering)
export * as viz from './viz';
