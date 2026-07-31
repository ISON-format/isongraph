/**
 * ISONGraph - A Token-Efficient Graph Store for JavaScript
 *
 * A property graph implementation with ISON persistence.
 * Supports multi-hop traversal, path finding, and fluent API.
 *
 * @example
 * ```javascript
 * import { ISONGraph, Direction } from 'ison-graph-js';
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

import { loads as parse, Reference, loadsISONL as loadsIsonl } from 'ison-parser';

export const VERSION = "1.0.0";

// =============================================================================
// Types
// =============================================================================

/** Traversal direction */
export const Direction = {
  OUT: "out",
  IN: "in",
  BOTH: "both"
};

// =============================================================================
// Data Classes
// =============================================================================

/**
 * Represents a graph node with properties
 */
export class Node {
  constructor(type, id, properties = {}) {
    this.type = type;
    this.id = id;
    this.properties = properties;
  }

  /** Get node reference tuple */
  get ref() {
    return [this.type, this.id];
  }

  /** Convert to ISON reference string */
  toIsonRef() {
    return `:${this.type}:${this.id}`;
  }

  /** Create unique key for maps */
  get key() {
    return `${this.type}:${this.id}`;
  }

  toString() {
    return `Node(${this.type}:${this.id}, ${JSON.stringify(this.properties)})`;
  }
}

/**
 * Represents a graph edge with properties
 */
export class Edge {
  constructor(relType, source, target, properties = {}) {
    this.relType = relType;
    this.source = source;
    this.target = target;
    this.properties = properties;
  }

  /** Get edge key tuple */
  get edgeKey() {
    return [this.relType, this.source, this.target];
  }

  /** Create unique string key for sets */
  get key() {
    return `${this.relType}:${this.source[0]}:${this.source[1]}:${this.target[0]}:${this.target[1]}`;
  }

  toString() {
    return `Edge(${nodeRefToString(this.source)} -[${this.relType}]-> ${nodeRefToString(this.target)})`;
  }
}

/**
 * Represents a path through the graph
 */
export class Path {
  constructor(nodes, edges) {
    this.nodes = nodes;
    this.edges = edges;
  }

  /** Number of hops in the path */
  get length() {
    return this.edges.length;
  }

  /** Starting node */
  get start() {
    return this.nodes.length > 0 ? this.nodes[0] : null;
  }

  /** Ending node */
  get end() {
    return this.nodes.length > 0 ? this.nodes[this.nodes.length - 1] : null;
  }

  toString() {
    const pathStr = this.nodes.map(n => `:${n[0]}:${n[1]}`).join(" -> ");
    return `Path(${pathStr})`;
  }
}

// =============================================================================
// Errors
// =============================================================================

export class GraphError extends Error {
  constructor(message) {
    super(message);
    this.name = "GraphError";
  }
}

export class NodeNotFoundError extends GraphError {
  constructor(nodeRef) {
    super(`Node not found: :${nodeRef[0]}:${nodeRef[1]}`);
    this.name = "NodeNotFoundError";
    this.nodeRef = nodeRef;
  }
}

export class EdgeNotFoundError extends GraphError {
  constructor(edgeKey) {
    super(`Edge not found: ${edgeKey}`);
    this.name = "EdgeNotFoundError";
    this.edgeKey = edgeKey;
  }
}

export class DuplicateNodeError extends GraphError {
  constructor(nodeRef) {
    super(`Node already exists: :${nodeRef[0]}:${nodeRef[1]}`);
    this.name = "DuplicateNodeError";
    this.nodeRef = nodeRef;
  }
}

export class DuplicateEdgeError extends GraphError {
  constructor(edgeKey) {
    super(`Edge already exists: ${edgeKey}`);
    this.name = "DuplicateEdgeError";
    this.edgeKey = edgeKey;
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

/** Convert NodeRef to string key */
function nodeRefToKey(ref) {
  return `${ref[0]}:${ref[1]}`;
}

/** Convert NodeRef to display string */
function nodeRefToString(ref) {
  return `:${ref[0]}:${ref[1]}`;
}

/** Compare two NodeRefs for equality */
function nodeRefsEqual(a, b) {
  return a[0] === b[0] && String(a[1]) === String(b[1]);
}

/** Convert edge to unique key string */
function edgeToKey(relType, source, target) {
  return `${relType}:${source[0]}:${source[1]}:${target[0]}:${target[1]}`;
}

// =============================================================================
// ISONGraph - Main Graph Class
// =============================================================================

/**
 * In-memory property graph store with ISON persistence.
 */
export class ISONGraph {
  constructor(name = "graph", directed = true) {
    this.name = name;
    this.directed = directed;
    this._nodes = new Map();
    this._edges = new Map();
    this._outEdges = new Map();
    this._inEdges = new Map();
    this._edgeSet = new Set();
  }

  // =========================================================================
  // Node Operations
  // =========================================================================

  addNode(nodeType, nodeId, properties = {}) {
    if (!this._nodes.has(nodeType)) {
      this._nodes.set(nodeType, new Map());
    }

    const typeNodes = this._nodes.get(nodeType);
    if (typeNodes.has(nodeId)) {
      throw new DuplicateNodeError([nodeType, nodeId]);
    }

    const node = new Node(nodeType, nodeId, properties);
    typeNodes.set(nodeId, node);
    return node;
  }

  getNode(nodeType, nodeId) {
    const typeNodes = this._nodes.get(nodeType);
    if (!typeNodes || !typeNodes.has(nodeId)) {
      throw new NodeNotFoundError([nodeType, nodeId]);
    }
    return typeNodes.get(nodeId);
  }

  getNodeByRef(ref) {
    return this.getNode(ref[0], ref[1]);
  }

  hasNode(nodeType, nodeId) {
    const typeNodes = this._nodes.get(nodeType);
    return typeNodes !== undefined && typeNodes.has(nodeId);
  }

  removeNode(nodeType, nodeId) {
    const ref = [nodeType, nodeId];
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
    const typeNodes = this._nodes.get(nodeType);
    typeNodes.delete(nodeId);
    if (typeNodes.size === 0) {
      this._nodes.delete(nodeType);
    }
  }

  updateNode(nodeType, nodeId, properties) {
    const node = this.getNode(nodeType, nodeId);
    Object.assign(node.properties, properties);
    return node;
  }

  *nodes(nodeType) {
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

  nodeCount(nodeType) {
    if (nodeType) {
      return this._nodes.get(nodeType)?.size ?? 0;
    }
    let count = 0;
    for (const typeNodes of this._nodes.values()) {
      count += typeNodes.size;
    }
    return count;
  }

  nodeTypes() {
    return Array.from(this._nodes.keys());
  }

  // =========================================================================
  // Edge Operations
  // =========================================================================

  addEdge(relType, source, target, properties = {}) {
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

    if (!this._edges.has(relType)) {
      this._edges.set(relType, []);
    }
    this._edges.get(relType).push(edge);

    const sourceKey = nodeRefToKey(source);
    const targetKey = nodeRefToKey(target);

    if (!this._outEdges.has(sourceKey)) {
      this._outEdges.set(sourceKey, []);
    }
    this._outEdges.get(sourceKey).push(edge);

    if (!this._inEdges.has(targetKey)) {
      this._inEdges.set(targetKey, []);
    }
    this._inEdges.get(targetKey).push(edge);

    this._edgeSet.add(edgeKey);

    // For undirected graphs, add reverse edge
    if (!this.directed) {
      const reverseKey = edgeToKey(relType, target, source);
      if (!this._edgeSet.has(reverseKey)) {
        const reverseEdge = new Edge(relType, target, source, properties);
        this._edges.get(relType).push(reverseEdge);

        if (!this._outEdges.has(targetKey)) {
          this._outEdges.set(targetKey, []);
        }
        this._outEdges.get(targetKey).push(reverseEdge);

        if (!this._inEdges.has(sourceKey)) {
          this._inEdges.set(sourceKey, []);
        }
        this._inEdges.get(sourceKey).push(reverseEdge);

        this._edgeSet.add(reverseKey);
      }
    }

    return edge;
  }

  _removeEdgeInternal(edge) {
    const edgeKey = edge.key;
    if (!this._edgeSet.has(edgeKey)) {
      return;
    }

    this._edgeSet.delete(edgeKey);

    const relEdges = this._edges.get(edge.relType);
    if (relEdges) {
      const idx = relEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        relEdges.splice(idx, 1);
      }
    }

    const sourceKey = nodeRefToKey(edge.source);
    const outEdges = this._outEdges.get(sourceKey);
    if (outEdges) {
      const idx = outEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        outEdges.splice(idx, 1);
      }
    }

    const targetKey = nodeRefToKey(edge.target);
    const inEdges = this._inEdges.get(targetKey);
    if (inEdges) {
      const idx = inEdges.findIndex(e => e.key === edgeKey);
      if (idx !== -1) {
        inEdges.splice(idx, 1);
      }
    }
  }

  removeEdge(relType, source, target) {
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

  hasEdge(relType, source, target) {
    return this._edgeSet.has(edgeToKey(relType, source, target));
  }

  getEdge(relType, source, target) {
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

  *edges(relType, source, target) {
    let edgeList;

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

  edgeCount(relType) {
    if (relType) {
      return this._edges.get(relType)?.length ?? 0;
    }
    return this._edgeSet.size;
  }

  edgeTypes() {
    return Array.from(this._edges.keys());
  }

  // =========================================================================
  // Traversal Operations
  // =========================================================================

  neighbors(nodeRef, relType, direction = Direction.OUT) {
    const neighbors = [];
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

  multiHop(start, relType, hops = 1, direction = Direction.OUT) {
    if (hops < 1) {
      return [start];
    }

    let current = new Set([nodeRefToKey(start)]);
    const visited = new Set([nodeRefToKey(start)]);
    const refMap = new Map([[nodeRefToKey(start), start]]);

    for (let i = 0; i < hops; i++) {
      const nextLevel = new Set();

      for (const key of current) {
        const nodeRef = refMap.get(key);
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

    return Array.from(current).map(key => refMap.get(key));
  }

  multiHopRange(start, relType, minHops = 1, maxHops = 3, direction = Direction.OUT) {
    const result = new Set();
    let current = new Set([nodeRefToKey(start)]);
    const visited = new Set([nodeRefToKey(start)]);
    const refMap = new Map([[nodeRefToKey(start), start]]);

    for (let hop = 1; hop <= maxHops; hop++) {
      const nextLevel = new Set();

      for (const key of current) {
        const nodeRef = refMap.get(key);
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

    return Array.from(result).map(key => refMap.get(key));
  }

  traverse(start, pattern, filterFn) {
    let current = new Set([nodeRefToKey(start)]);
    const refMap = new Map([[nodeRefToKey(start), start]]);

    for (const [relType, direction] of pattern) {
      const nextLevel = new Set();

      for (const key of current) {
        const nodeRef = refMap.get(key);
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

    return Array.from(current).map(key => refMap.get(key));
  }

  // =========================================================================
  // Path Finding
  // =========================================================================

  shortestPath(start, end, relType, maxHops = 10, direction = Direction.OUT) {
    if (nodeRefsEqual(start, end)) {
      return new Path([start], []);
    }

    const endKey = nodeRefToKey(end);
    const visited = new Set([nodeRefToKey(start)]);

    const queue = [{ current: start, pathNodes: [start], pathEdges: [] }];

    while (queue.length > 0) {
      const { current, pathNodes, pathEdges } = queue.shift();

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

  allPaths(start, end, relType, maxHops = 5, direction = Direction.OUT) {
    const paths = [];
    const endKey = nodeRefToKey(end);

    const dfs = (current, pathNodes, pathEdges, visited) => {
      if (pathNodes.length > maxHops + 1) {
        return;
      }

      const currentKey = nodeRefToKey(current);
      if (currentKey === endKey) {
        paths.push(new Path([...pathNodes], [...pathEdges]));
        return;
      }

      const edgesToFollow = [];
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

  pathExists(start, end, relType, maxHops = 10) {
    return this.shortestPath(start, end, relType, maxHops) !== null;
  }

  // =========================================================================
  // Graph Analysis
  // =========================================================================

  inDegree(nodeRef) {
    return (this._inEdges.get(nodeRefToKey(nodeRef)) || []).length;
  }

  outDegree(nodeRef) {
    return (this._outEdges.get(nodeRefToKey(nodeRef)) || []).length;
  }

  degree(nodeRef) {
    if (this.directed) {
      return this.inDegree(nodeRef) + this.outDegree(nodeRef);
    } else {
      const edges = new Set();
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

  isConnected() {
    const allNodes = Array.from(this.nodes());
    if (allNodes.length === 0) {
      return true;
    }

    const start = allNodes[0].ref;
    const visited = new Set([nodeRefToKey(start)]);
    const queue = [start];

    while (queue.length > 0) {
      const current = queue.shift();
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

  hasCycle(relType) {
    const visited = new Set();

    if (!this.directed) {
      // Undirected: DFS with parent-edge tracking so the auto-added reverse
      // edge is not mistaken for a cycle when walking back along the edge
      // we arrived on.
      const undirectedEdgeId = (edge) => {
        const a = nodeRefToKey(edge.source);
        const b = nodeRefToKey(edge.target);
        return `${edge.relType}|${[a, b].sort().join("|")}`;
      };

      const dfs = (nodeRef, incomingEdgeId) => {
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
          if (dfs(edge.target, edgeId)) {
            return true;
          }
        }
        return false;
      };

      for (const node of this.nodes()) {
        if (!visited.has(node.key)) {
          if (dfs(node.ref, null)) {
            return true;
          }
        }
      }

      return false;
    }

    const recStack = new Set();

    const dfs = (nodeRef) => {
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

  connectedComponents() {
    const visited = new Set();
    const components = [];

    for (const node of this.nodes()) {
      if (!visited.has(node.key)) {
        const component = new Set();
        const queue = [node.ref];

        while (queue.length > 0) {
          const current = queue.shift();
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

  _valueToIson(value) {
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
  static _sortedNodes(typeNodes) {
    return Array.from(typeNodes.values()).sort((a, b) => {
      const ka = String(a.id), kb = String(b.id);
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }

  /** Sorted edge rows within a rel_type block: ordinal (sourceType, sourceId, targetType, targetId). */
  static _sortedEdges(edges) {
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
  toIson() {
    const blocks = [];

    const nodeTypes = Array.from(this._nodes.keys()).sort();
    for (const nodeType of nodeTypes) {
      const typeNodes = this._nodes.get(nodeType);
      if (typeNodes.size === 0) continue;
      const sortedTypeNodes = ISONGraph._sortedNodes(typeNodes);

      const propKeys = new Set();
      for (const node of sortedTypeNodes) {
        for (const key of Object.keys(node.properties)) {
          propKeys.add(key);
        }
      }
      const sortedPropKeys = Array.from(propKeys).sort();

      const lines = [`nodes.${nodeType}`];
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

    const edgeTypes = Array.from(this._edges.keys()).sort();
    for (const relType of edgeTypes) {
      const edges = this._edges.get(relType);
      if (edges.length === 0) continue;
      const sortedTypeEdges = ISONGraph._sortedEdges(edges);

      const propKeys = new Set();
      for (const edge of sortedTypeEdges) {
        for (const key of Object.keys(edge.properties)) {
          propKeys.add(key);
        }
      }
      const sortedPropKeys = Array.from(propKeys).sort();

      const lines = [`edges.${relType}`];
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
   * Row order is canonical, matching {@link ISONGraph#toIson} - see there
   * for the exact ordering rule.
   */
  toIsonl() {
    const lines = [];

    const nodeTypes = Array.from(this._nodes.keys()).sort();
    for (const nodeType of nodeTypes) {
      const typeNodes = this._nodes.get(nodeType);
      for (const node of ISONGraph._sortedNodes(typeNodes)) {
        const propKeys = Object.keys(node.properties).sort();
        const fields = ["id", ...propKeys];
        const values = [String(node.id), ...propKeys.map(k => this._valueToIson(node.properties[k]))];
        lines.push(`nodes.${node.type}|${fields.join(" ")}|${values.join(" ")}`);
      }
    }

    const edgeTypes = Array.from(this._edges.keys()).sort();
    for (const relType of edgeTypes) {
      const edges = this._edges.get(relType);
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

  static fromIson(text, name = "graph") {
    const graph = new ISONGraph(name);
    const doc = parse(text);

    for (const block of doc.blocks) {
      if (block.kind === "nodes") {
        const nodeType = block.name;
        for (const row of block.rows) {
          const nodeId = row.id;
          const props = {};
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
          let source = row.source;
          let target = row.target;

          // Convert Reference objects to tuples
          if (source instanceof Reference) {
            const id = /^\d+$/.test(source.id) ? parseInt(source.id, 10) : source.id;
            source = [source.type, id];
          }
          if (target instanceof Reference) {
            const id = /^\d+$/.test(target.id) ? parseInt(target.id, 10) : target.id;
            target = [target.type, id];
          }

          const props = {};
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

  static fromIsonl(text, name = "graph") {
    const graph = new ISONGraph(name);
    const doc = loadsIsonl(text);

    for (const block of doc.blocks) {
      if (block.kind === "nodes") {
        const nodeType = block.name;
        for (const row of block.rows) {
          const nodeId = row.id;
          const props = {};
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
          let source = row.source;
          let target = row.target;

          if (source instanceof Reference) {
            const id = /^\d+$/.test(source.id) ? parseInt(source.id, 10) : source.id;
            source = [source.type, id];
          }
          if (target instanceof Reference) {
            const id = /^\d+$/.test(target.id) ? parseInt(target.id, 10) : target.id;
            target = [target.type, id];
          }

          const props = {};
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

  static parse(text, name = "graph") {
    return ISONGraph.fromIson(text, name);
  }

  // =========================================================================
  // Query Interface (Fluent API)
  // =========================================================================

  start(nodeRef) {
    return new GraphTraversal(this, nodeRef);
  }

  query(pattern) {
    pattern = pattern.trim();

    const hopMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*/);
    if (hopMatch) {
      const [, nodeType, nodeIdStr, relType, hopsStr] = hopMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.multiHop([nodeType, nodeId], relType, parseInt(hopsStr, 10));
    }

    const rangeMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*/);
    if (rangeMatch) {
      const [, nodeType, nodeIdStr, relType, minStr, maxStr] = rangeMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.multiHopRange([nodeType, nodeId], relType, parseInt(minStr, 10), parseInt(maxStr, 10));
    }

    const simpleMatch = pattern.match(/:(\w+):(\w+)\s*-\[:(\w+)\]->\s*\*/);
    if (simpleMatch) {
      const [, nodeType, nodeIdStr, relType] = simpleMatch;
      const nodeId = /^\d+$/.test(nodeIdStr) ? parseInt(nodeIdStr, 10) : nodeIdStr;
      return this.neighbors([nodeType, nodeId], relType);
    }

    throw new Error(`Invalid query pattern: ${pattern}`);
  }

  toString() {
    return `ISONGraph(name=${this.name}, nodes=${this.nodeCount()}, edges=${this.edgeCount()})`;
  }
}

// =============================================================================
// Fluent Traversal API
// =============================================================================

export class GraphTraversal {
  constructor(graph, start) {
    this._graph = graph;
    const startKey = nodeRefToKey(start);
    this._current = new Set([startKey]);
    this._visited = new Set([startKey]);
    this._refMap = new Map([[startKey, start]]);
  }

  hop(relType, direction = Direction.OUT, where) {
    const nextLevel = new Set();

    for (const key of this._current) {
      const nodeRef = this._refMap.get(key);
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

  hops(n, relType, direction = Direction.OUT) {
    for (let i = 0; i < n; i++) {
      this.hop(relType, direction);
    }
    return this;
  }

  filter(fn) {
    const filtered = new Set();
    for (const key of this._current) {
      const ref = this._refMap.get(key);
      if (fn(this._graph.getNodeByRef(ref))) {
        filtered.add(key);
      }
    }
    this._current = filtered;
    return this;
  }

  collect() {
    return Array.from(this._current).map(key => this._refMap.get(key));
  }

  collectNodes() {
    return this.collect().map(ref => this._graph.getNodeByRef(ref));
  }

  count() {
    return this._current.size;
  }

  first() {
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
export * from './query.js';

// Schema Validation Module
export * from './schema.js';

// Visualization Module (deterministic layout + SVG/HTML rendering)
export * as viz from './viz.js';
