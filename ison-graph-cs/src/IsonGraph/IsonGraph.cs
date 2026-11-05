// ISONGraph - A Token-Efficient Graph Store for C#
//
// An in-memory property graph store with ISON persistence.
// Supports multi-hop traversal, path finding, and a fluent API.
//
// Example:
//     var graph = new ISONGraph("social");
//     graph.AddNode("person", "1", new() { ["name"] = "Alice", ["age"] = "30" });
//     graph.AddNode("person", "2", new() { ["name"] = "Bob", ["age"] = "25" });
//     graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
//                   new() { ["since"] = "2020" });
//
//     var friends = graph.Neighbors(new("person", "1"), "KNOWS");
//     var fof = graph.MultiHop(new("person", "1"), "KNOWS", 2);
//
// Author: Mahesh Vaikri
// Version: 1.0.0

using System.Globalization;

namespace IsonGraph;

/// <summary>Library version.</summary>
public static class IsonGraphVersion
{
    public const string Version = "1.0.0";
}

// =============================================================================
// Types
// =============================================================================

/// <summary>Edge traversal direction.</summary>
public enum Direction
{
    Out,
    In,
    Both,
}

/// <summary>Node reference: (type, id).</summary>
public readonly record struct NodeRef(string Type, string Id)
{
    /// <summary>Stable string key "type:id".</summary>
    public string Key => Type + ":" + Id;

    /// <summary>ISON reference string ":type:id".</summary>
    public string ToIsonRef() => ":" + Type + ":" + Id;

    public override string ToString() => ":" + Type + ":" + Id;
}

/// <summary>Represents a graph node with properties.</summary>
/// <summary>
/// Helpers for reading typed property values.
/// </summary>
/// <remarks>
/// Properties used to be strings, so query filtering and schema validation
/// both worked on text. They still can - <see cref="ValueText"/> renders any
/// value the way it used to be stored - but a real number now compares as a
/// number rather than as a parse of its rendering.
/// </remarks>
public static class PropertyValue
{
    /// <summary>Render a property value as text.</summary>
    public static string ValueText(object? value) => value switch
    {
        null => string.Empty,
        bool b => b ? "true" : "false",
        IsonParser.Reference r => r.ToIson(),
        IFormattable f => f.ToString(null, CultureInfo.InvariantCulture),
        _ => value.ToString() ?? string.Empty,
    };

    /// <summary>
    /// Numeric view of a property: exact for a number, lenient for a string
    /// that parses, so a query written against string-stored numbers still
    /// matches.
    /// </summary>
    public static double? AsDouble(object? value) => value switch
    {
        long l => l,
        int i => i,
        double d => d,
        float f => f,
        string s when double.TryParse(s, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                                      CultureInfo.InvariantCulture, out var parsed) => parsed,
        _ => (double?)null,
    };
}

public sealed class Node
{
    public string Type { get; }
    public string Id { get; }
    public Dictionary<string, object?> Properties { get; }

    public Node(string type, string id, IDictionary<string, object?>? properties = null)
    {
        Type = type;
        Id = id;
        Properties = properties is null
            ? new Dictionary<string, object?>()
            : new Dictionary<string, object?>(properties);
    }

    /// <summary>Node reference (type, id).</summary>
    public NodeRef Ref => new(Type, Id);

    /// <summary>Stable string key "type:id".</summary>
    public string Key => Type + ":" + Id;

    /// <summary>ISON reference string ":type:id".</summary>
    public string ToIsonRef() => ":" + Type + ":" + Id;

    public override string ToString() => $"Node({Type}:{Id})";
}

/// <summary>Represents a graph edge with properties.</summary>
public sealed class Edge
{
    public string RelType { get; }
    public NodeRef Source { get; }
    public NodeRef Target { get; }
    public Dictionary<string, object?> Properties { get; }

    public Edge(string relType, NodeRef source, NodeRef target,
                IDictionary<string, object?>? properties = null)
    {
        RelType = relType;
        Source = source;
        Target = target;
        Properties = properties is null
            ? new Dictionary<string, object?>()
            : new Dictionary<string, object?>(properties);
    }

    /// <summary>Unique edge key "rel:sourceType:sourceId:targetType:targetId".</summary>
    public string Key => RelType + ":" + Source.Key + ":" + Target.Key;

    public override string ToString() => $"Edge({Source} -[{RelType}]-> {Target})";
}

/// <summary>Represents a path through the graph.</summary>
public sealed class Path
{
    public List<NodeRef> Nodes { get; }
    public List<Edge> Edges { get; }

    public Path(List<NodeRef> nodes, List<Edge> edges)
    {
        Nodes = nodes;
        Edges = edges;
    }

    /// <summary>Number of hops in the path.</summary>
    public int Length => Edges.Count;

    /// <summary>Starting node, or null for an empty path.</summary>
    public NodeRef? Start => Nodes.Count > 0 ? Nodes[0] : null;

    /// <summary>Ending node, or null for an empty path.</summary>
    public NodeRef? End => Nodes.Count > 0 ? Nodes[^1] : null;

    public override string ToString() =>
        "Path(" + string.Join(" -> ", Nodes.Select(n => n.ToIsonRef())) + ")";
}

// =============================================================================
// Exceptions
// =============================================================================

/// <summary>Base exception for graph errors.</summary>
public class GraphError : Exception
{
    public GraphError(string message) : base(message) { }
}

/// <summary>Node does not exist in the graph.</summary>
public sealed class NodeNotFoundError : GraphError
{
    public NodeRef NodeRef { get; }

    public NodeNotFoundError(NodeRef nodeRef)
        : base($"Node not found: :{nodeRef.Type}:{nodeRef.Id}")
    {
        NodeRef = nodeRef;
    }
}

/// <summary>Edge does not exist in the graph.</summary>
public sealed class EdgeNotFoundError : GraphError
{
    public string EdgeKey { get; }

    public EdgeNotFoundError(string edgeKey)
        : base($"Edge not found: {edgeKey}")
    {
        EdgeKey = edgeKey;
    }
}

/// <summary>Node already exists.</summary>
public sealed class DuplicateNodeError : GraphError
{
    public NodeRef NodeRef { get; }

    public DuplicateNodeError(NodeRef nodeRef)
        : base($"Node already exists: :{nodeRef.Type}:{nodeRef.Id}")
    {
        NodeRef = nodeRef;
    }
}

/// <summary>Edge already exists.</summary>
public sealed class DuplicateEdgeError : GraphError
{
    public string EdgeKey { get; }

    public DuplicateEdgeError(string edgeKey)
        : base($"Edge already exists: {edgeKey}")
    {
        EdgeKey = edgeKey;
    }
}

// =============================================================================
// ISONGraph - Main Graph Class
// =============================================================================

/// <summary>
/// In-memory property graph store with ISON persistence.
///
/// Features:
/// - Property graph model (nodes and edges with properties)
/// - Multiple node types and relationship types
/// - O(1) node lookup by (type, id)
/// - Multi-hop traversal
/// - Shortest path finding (BFS) and all-paths finding (iterative DFS)
/// - ISON/ISONL persistence
/// </summary>
public sealed partial class ISONGraph
{
    public string Name { get; set; }
    public bool Directed { get; }

    // Node storage: type -> id -> Node (lookup) plus explicit insertion order.
    private readonly Dictionary<string, Dictionary<string, Node>> _nodesByType = new();
    private readonly Dictionary<string, List<Node>> _nodeOrder = new();
    private readonly List<string> _nodeTypeOrder = new();

    // Edge storage: relType -> edges, plus explicit rel-type insertion order.
    private readonly Dictionary<string, List<Edge>> _edgesByType = new();
    private readonly List<string> _edgeTypeOrder = new();

    // Indexes: outgoing/incoming edges per node key.
    private readonly Dictionary<string, List<Edge>> _outEdges = new();
    private readonly Dictionary<string, List<Edge>> _inEdges = new();

    // Edge uniqueness set (edge keys).
    private readonly HashSet<string> _edgeSet = new();

    public ISONGraph(string name = "graph", bool directed = true)
    {
        Name = name;
        Directed = directed;
    }

    // =========================================================================
    // Node Operations
    // =========================================================================

    /// <summary>
    /// Reject ':' or '|' in a node type, node id, or relationship type. Both
    /// are structurally significant to the wire format (':' delimits
    /// <c>:type:id</c> references, '|' delimits ISONL columns); allowing
    /// them here would build a graph that throws on
    /// ToIson()/ToIsonl() round-trip instead of failing at construction.
    /// </summary>
    private static void CheckIdentifier(string kind, string value)
    {
        if (value.Contains(':') || value.Contains('|'))
            throw new ArgumentException($"{kind} must not contain ':' or '|': '{value}'");
    }

    /// <summary>
    /// Reject property values that change type on a round trip. ISON has no
    /// spelling for a non-finite float: NaN and infinity are written bare and
    /// read back as the <em>strings</em> "nan" / "inf", so the value changes
    /// type silently. Refused here, where the mistake is still visible.
    /// </summary>
    private static void CheckPropertyValues(string kind, IDictionary<string, object?>? properties)
    {
        if (properties is null) return;
        foreach (var (key, value) in properties)
        {
            var nonFinite = value switch
            {
                double d => !double.IsFinite(d),
                float f => !float.IsFinite(f),
                _ => false,
            };
            if (nonFinite)
                throw new ArgumentException(
                    $"{kind} '{key}' = {value} cannot be encoded: a float must be finite " +
                    "(NaN and infinity are read back as strings).");
        }
    }

    /// <summary>
    /// Add a node to the graph.
    /// Throws <see cref="ArgumentException"/> if the type or id contains ':' or '|',
    /// and <see cref="DuplicateNodeError"/> if the node already exists.
    /// </summary>
    public Node AddNode(string nodeType, string nodeId,
                        IDictionary<string, object?>? properties = null)
    {
        CheckIdentifier("Node type", nodeType);
        CheckIdentifier("Node id", nodeId);
        CheckPropertyValues("Node property", properties);

        if (!_nodesByType.TryGetValue(nodeType, out var typeNodes))
        {
            typeNodes = new Dictionary<string, Node>();
            _nodesByType[nodeType] = typeNodes;
            _nodeOrder[nodeType] = new List<Node>();
            _nodeTypeOrder.Add(nodeType);
        }

        if (typeNodes.ContainsKey(nodeId))
            throw new DuplicateNodeError(new NodeRef(nodeType, nodeId));

        var node = new Node(nodeType, nodeId, properties);
        typeNodes[nodeId] = node;
        _nodeOrder[nodeType].Add(node);
        return node;
    }

    /// <summary>Get a node by type and id. Throws <see cref="NodeNotFoundError"/>.</summary>
    public Node GetNode(string nodeType, string nodeId)
    {
        if (_nodesByType.TryGetValue(nodeType, out var typeNodes) &&
            typeNodes.TryGetValue(nodeId, out var node))
        {
            return node;
        }
        throw new NodeNotFoundError(new NodeRef(nodeType, nodeId));
    }

    /// <summary>Get a node by reference.</summary>
    public Node GetNode(NodeRef nodeRef) => GetNode(nodeRef.Type, nodeRef.Id);

    /// <summary>Check if a node exists.</summary>
    public bool HasNode(string nodeType, string nodeId) =>
        _nodesByType.TryGetValue(nodeType, out var typeNodes) && typeNodes.ContainsKey(nodeId);

    /// <summary>Check if a node exists by reference.</summary>
    public bool HasNode(NodeRef nodeRef) => HasNode(nodeRef.Type, nodeRef.Id);

    /// <summary>
    /// Remove a node and all its edges.
    /// Throws <see cref="NodeNotFoundError"/> if the node doesn't exist.
    /// </summary>
    public void RemoveNode(string nodeType, string nodeId)
    {
        var nodeRef = new NodeRef(nodeType, nodeId);
        if (!HasNode(nodeType, nodeId))
            throw new NodeNotFoundError(nodeRef);

        var nodeKey = nodeRef.Key;
        var toRemove = new List<Edge>();
        if (_outEdges.TryGetValue(nodeKey, out var outList)) toRemove.AddRange(outList);
        if (_inEdges.TryGetValue(nodeKey, out var inList)) toRemove.AddRange(inList);
        foreach (var edge in toRemove)
            RemoveEdgeInternal(edge);

        var typeNodes = _nodesByType[nodeType];
        var node = typeNodes[nodeId];
        typeNodes.Remove(nodeId);
        _nodeOrder[nodeType].Remove(node);
        if (typeNodes.Count == 0)
        {
            _nodesByType.Remove(nodeType);
            _nodeOrder.Remove(nodeType);
            _nodeTypeOrder.Remove(nodeType);
        }
    }

    /// <summary>Merge properties into an existing node and return it.</summary>
    public Node UpdateNode(string nodeType, string nodeId,
                           IDictionary<string, object?> properties)
    {
        CheckPropertyValues("Node property", properties);
        var node = GetNode(nodeType, nodeId);
        foreach (var (key, value) in properties)
            node.Properties[key] = value;
        return node;
    }

    /// <summary>Iterate over nodes, optionally filtered by type, in insertion order.</summary>
    public IEnumerable<Node> Nodes(string? nodeType = null)
    {
        if (nodeType is not null)
        {
            if (_nodeOrder.TryGetValue(nodeType, out var list))
            {
                foreach (var node in list)
                    yield return node;
            }
            yield break;
        }

        foreach (var type in _nodeTypeOrder)
        {
            foreach (var node in _nodeOrder[type])
                yield return node;
        }
    }

    /// <summary>Count nodes, optionally filtered by type.</summary>
    public int NodeCount(string? nodeType = null)
    {
        if (nodeType is not null)
            return _nodesByType.TryGetValue(nodeType, out var typeNodes) ? typeNodes.Count : 0;
        var count = 0;
        foreach (var typeNodes in _nodesByType.Values)
            count += typeNodes.Count;
        return count;
    }

    /// <summary>All node types, in insertion order.</summary>
    public List<string> NodeTypes() => new(_nodeTypeOrder);

    // =========================================================================
    // Edge Operations
    // =========================================================================

    /// <summary>
    /// Add an edge to the graph. Returns the forward edge; for undirected
    /// graphs the reverse edge is stored as well but not returned.
    /// Throws <see cref="ArgumentException"/> if relType contains ':' or '|',
    /// <see cref="NodeNotFoundError"/> if either endpoint doesn't exist,
    /// and <see cref="DuplicateEdgeError"/> if the edge already exists.
    /// </summary>
    public Edge AddEdge(string relType, NodeRef source, NodeRef target,
                        IDictionary<string, object?>? properties = null)
    {
        CheckIdentifier("Relationship type", relType);
        CheckPropertyValues("Edge property", properties);

        if (!HasNode(source))
            throw new NodeNotFoundError(source);
        if (!HasNode(target))
            throw new NodeNotFoundError(target);

        var edge = new Edge(relType, source, target, properties);
        var edgeKey = edge.Key;
        if (_edgeSet.Contains(edgeKey))
            throw new DuplicateEdgeError(edgeKey);

        StoreEdge(edge);

        // For undirected graphs, add the reverse edge.
        if (!Directed)
        {
            var reverse = new Edge(relType, target, source, properties);
            if (!_edgeSet.Contains(reverse.Key))
                StoreEdge(reverse);
        }

        return edge;
    }

    private void StoreEdge(Edge edge)
    {
        if (!_edgesByType.TryGetValue(edge.RelType, out var relEdges))
        {
            relEdges = new List<Edge>();
            _edgesByType[edge.RelType] = relEdges;
            _edgeTypeOrder.Add(edge.RelType);
        }
        relEdges.Add(edge);

        var sourceKey = edge.Source.Key;
        if (!_outEdges.TryGetValue(sourceKey, out var outList))
        {
            outList = new List<Edge>();
            _outEdges[sourceKey] = outList;
        }
        outList.Add(edge);

        var targetKey = edge.Target.Key;
        if (!_inEdges.TryGetValue(targetKey, out var inList))
        {
            inList = new List<Edge>();
            _inEdges[targetKey] = inList;
        }
        inList.Add(edge);

        _edgeSet.Add(edge.Key);
    }

    private void RemoveEdgeInternal(Edge edge)
    {
        var edgeKey = edge.Key;
        if (!_edgeSet.Remove(edgeKey))
            return;

        static void RemoveFirstByKey(List<Edge> list, string key)
        {
            var index = list.FindIndex(e => e.Key == key);
            if (index >= 0)
                list.RemoveAt(index);
        }

        if (_edgesByType.TryGetValue(edge.RelType, out var relEdges))
            RemoveFirstByKey(relEdges, edgeKey);
        if (_outEdges.TryGetValue(edge.Source.Key, out var outList))
            RemoveFirstByKey(outList, edgeKey);
        if (_inEdges.TryGetValue(edge.Target.Key, out var inList))
            RemoveFirstByKey(inList, edgeKey);
    }

    /// <summary>
    /// Remove an edge. On undirected graphs the auto-created reverse edge is
    /// removed too. Throws <see cref="EdgeNotFoundError"/> if the edge doesn't exist.
    /// </summary>
    public void RemoveEdge(string relType, NodeRef source, NodeRef target)
    {
        var edge = new Edge(relType, source, target);
        if (!_edgeSet.Contains(edge.Key))
            throw new EdgeNotFoundError(edge.Key);

        RemoveEdgeInternal(edge);

        if (!Directed)
            RemoveEdgeInternal(new Edge(relType, target, source));
    }

    /// <summary>Check if an edge exists.</summary>
    public bool HasEdge(string relType, NodeRef source, NodeRef target) =>
        _edgeSet.Contains(new Edge(relType, source, target).Key);

    /// <summary>
    /// Get an edge by its components. Throws <see cref="EdgeNotFoundError"/>.
    /// </summary>
    public Edge GetEdge(string relType, NodeRef source, NodeRef target)
    {
        var edgeKey = relType + ":" + source.Key + ":" + target.Key;
        if (_edgeSet.Contains(edgeKey) && _edgesByType.TryGetValue(relType, out var relEdges))
        {
            foreach (var edge in relEdges)
            {
                if (edge.Source == source && edge.Target == target)
                    return edge;
            }
        }
        throw new EdgeNotFoundError(edgeKey);
    }

    /// <summary>
    /// Iterate over edges with optional filters (rel type, source, target).
    /// </summary>
    public IEnumerable<Edge> Edges(string? relType = null, NodeRef? source = null,
                                   NodeRef? target = null)
    {
        IEnumerable<Edge> candidates;
        if (source is not null)
            candidates = _outEdges.TryGetValue(source.Value.Key, out var o) ? o : Enumerable.Empty<Edge>();
        else if (target is not null)
            candidates = _inEdges.TryGetValue(target.Value.Key, out var i) ? i : Enumerable.Empty<Edge>();
        else if (relType is not null)
            candidates = _edgesByType.TryGetValue(relType, out var r) ? r : Enumerable.Empty<Edge>();
        else
            candidates = AllEdgesInOrder();

        foreach (var edge in candidates)
        {
            if (relType is not null && edge.RelType != relType) continue;
            if (source is not null && edge.Source != source.Value) continue;
            if (target is not null && edge.Target != target.Value) continue;
            yield return edge;
        }
    }

    private IEnumerable<Edge> AllEdgesInOrder()
    {
        foreach (var relType in _edgeTypeOrder)
        {
            foreach (var edge in _edgesByType[relType])
                yield return edge;
        }
    }

    /// <summary>Count edges, optionally filtered by type.</summary>
    public int EdgeCount(string? relType = null)
    {
        if (relType is not null)
            return _edgesByType.TryGetValue(relType, out var relEdges) ? relEdges.Count : 0;
        return _edgeSet.Count;
    }

    /// <summary>All edge/relationship types, in insertion order.</summary>
    public List<string> EdgeTypes() => new(_edgeTypeOrder);

    // =========================================================================
    // Traversal Operations
    // =========================================================================

    /// <summary>Get neighboring node references.</summary>
    public List<NodeRef> Neighbors(NodeRef nodeRef, string? relType = null,
                                   Direction direction = Direction.Out)
    {
        var result = new List<NodeRef>();
        var nodeKey = nodeRef.Key;

        if (direction is Direction.Out or Direction.Both &&
            _outEdges.TryGetValue(nodeKey, out var outList))
        {
            foreach (var edge in outList)
            {
                if (relType is null || edge.RelType == relType)
                    result.Add(edge.Target);
            }
        }

        if (direction is Direction.In or Direction.Both &&
            _inEdges.TryGetValue(nodeKey, out var inList))
        {
            foreach (var edge in inList)
            {
                if (relType is null || edge.RelType == relType)
                    result.Add(edge.Source);
            }
        }

        return result;
    }

    /// <summary>Get nodes exactly N hops away.</summary>
    public List<NodeRef> MultiHop(NodeRef start, string? relType = null, int hops = 1,
                                  Direction direction = Direction.Out)
    {
        if (hops < 1)
            return new List<NodeRef> { start };

        var current = new HashSet<NodeRef> { start };
        var visited = new HashSet<NodeRef> { start };

        for (var i = 0; i < hops; i++)
        {
            var nextLevel = new HashSet<NodeRef>();
            foreach (var node in current)
            {
                foreach (var neighbor in Neighbors(node, relType, direction))
                {
                    if (!visited.Contains(neighbor))
                        nextLevel.Add(neighbor);
                }
            }
            visited.UnionWith(nextLevel);
            current = nextLevel;
        }

        return current.ToList();
    }

    /// <summary>Get nodes within a range of hops (inclusive bounds).</summary>
    public List<NodeRef> MultiHopRange(NodeRef start, string? relType = null,
                                       int minHops = 1, int maxHops = 3,
                                       Direction direction = Direction.Out)
    {
        var result = new HashSet<NodeRef>();
        var current = new HashSet<NodeRef> { start };
        var visited = new HashSet<NodeRef> { start };

        for (var hop = 1; hop <= maxHops; hop++)
        {
            var nextLevel = new HashSet<NodeRef>();
            foreach (var node in current)
            {
                foreach (var neighbor in Neighbors(node, relType, direction))
                {
                    if (!visited.Contains(neighbor))
                    {
                        nextLevel.Add(neighbor);
                        if (hop >= minHops)
                            result.Add(neighbor);
                    }
                }
            }
            visited.UnionWith(nextLevel);
            current = nextLevel;
            if (current.Count == 0)
                break;
        }

        return result.ToList();
    }

    /// <summary>
    /// Traverse the graph following a pattern of (relType, direction) steps,
    /// with an optional node filter applied at each step.
    /// </summary>
    public List<NodeRef> Traverse(NodeRef start,
                                  IEnumerable<(string RelType, Direction Direction)> pattern,
                                  Func<Node, bool>? filter = null)
    {
        var current = new HashSet<NodeRef> { start };

        foreach (var (relType, direction) in pattern)
        {
            var nextLevel = new HashSet<NodeRef>();
            foreach (var nodeRef in current)
            {
                foreach (var neighbor in Neighbors(nodeRef, relType, direction))
                {
                    if (filter is null)
                    {
                        nextLevel.Add(neighbor);
                    }
                    else if (HasNode(neighbor) && filter(GetNode(neighbor)))
                    {
                        nextLevel.Add(neighbor);
                    }
                }
            }
            current = nextLevel;
            if (current.Count == 0)
                break;
        }

        return current.ToList();
    }

    // =========================================================================
    // Path Finding
    // =========================================================================

    /// <summary>
    /// Find the shortest path between two nodes using BFS, or null if none
    /// exists within <paramref name="maxHops"/> hops.
    /// </summary>
    public Path? ShortestPath(NodeRef start, NodeRef end, string? relType = null,
                              int maxHops = 10, Direction direction = Direction.Out)
    {
        if (start == end)
            return new Path(new List<NodeRef> { start }, new List<Edge>());

        var visited = new HashSet<NodeRef> { start };
        var queue = new Queue<(NodeRef Current, List<NodeRef> Nodes, List<Edge> Edges)>();
        queue.Enqueue((start, new List<NodeRef> { start }, new List<Edge>()));

        while (queue.Count > 0)
        {
            var (current, pathNodes, pathEdges) = queue.Dequeue();

            // A path with N nodes has N-1 hops; expanding adds one more hop,
            // so only expand when the resulting path stays within maxHops.
            if (pathNodes.Count > maxHops)
                continue;

            if (direction != Direction.In &&
                _outEdges.TryGetValue(current.Key, out var outList))
            {
                foreach (var edge in outList)
                {
                    if (relType is not null && edge.RelType != relType) continue;
                    if (edge.Target == end)
                    {
                        var nodes = new List<NodeRef>(pathNodes) { edge.Target };
                        var edges = new List<Edge>(pathEdges) { edge };
                        return new Path(nodes, edges);
                    }
                    if (visited.Add(edge.Target))
                    {
                        var nodes = new List<NodeRef>(pathNodes) { edge.Target };
                        var edges = new List<Edge>(pathEdges) { edge };
                        queue.Enqueue((edge.Target, nodes, edges));
                    }
                }
            }

            if (direction is Direction.In or Direction.Both &&
                _inEdges.TryGetValue(current.Key, out var inList))
            {
                foreach (var edge in inList)
                {
                    if (relType is not null && edge.RelType != relType) continue;
                    if (edge.Source == end)
                    {
                        var nodes = new List<NodeRef>(pathNodes) { edge.Source };
                        var edges = new List<Edge>(pathEdges) { edge };
                        return new Path(nodes, edges);
                    }
                    if (visited.Add(edge.Source))
                    {
                        var nodes = new List<NodeRef>(pathNodes) { edge.Source };
                        var edges = new List<Edge>(pathEdges) { edge };
                        queue.Enqueue((edge.Source, nodes, edges));
                    }
                }
            }
        }

        return null;
    }

    /// <summary>
    /// Find all simple paths between two nodes using an iterative DFS with
    /// backtracking (explicit stack; deep graphs cannot overflow the call stack).
    /// </summary>
    public List<Path> AllPaths(NodeRef start, NodeRef end, string? relType = null,
                               int maxHops = 5, Direction direction = Direction.Out)
    {
        var paths = new List<Path>();

        List<Edge> EdgesFrom(NodeRef node)
        {
            var edgesToFollow = new List<Edge>();
            if (direction is Direction.Out or Direction.Both &&
                _outEdges.TryGetValue(node.Key, out var outList))
            {
                foreach (var edge in outList)
                {
                    if (relType is null || edge.RelType == relType)
                        edgesToFollow.Add(edge);
                }
            }
            if (direction is Direction.In or Direction.Both &&
                _inEdges.TryGetValue(node.Key, out var inList))
            {
                foreach (var edge in inList)
                {
                    if (relType is null || edge.RelType == relType)
                        edgesToFollow.Add(new Edge(edge.RelType, edge.Target, edge.Source,
                                                   edge.Properties));
                }
            }
            return edgesToFollow;
        }

        if (start == end)
            return new List<Path> { new(new List<NodeRef> { start }, new List<Edge>()) };

        // Iterative DFS with backtracking: one edge-enumerator frame per node
        // on the current path.
        var pathNodes = new List<NodeRef> { start };
        var pathEdges = new List<Edge>();
        var visited = new HashSet<NodeRef> { start };
        var stack = new List<IEnumerator<Edge>> { EdgesFrom(start).GetEnumerator() };

        while (stack.Count > 0)
        {
            var frame = stack[^1];
            if (!frame.MoveNext())
            {
                // Frame exhausted: backtrack (never pop the start node).
                stack.RemoveAt(stack.Count - 1);
                if (pathEdges.Count > 0)
                {
                    visited.Remove(pathNodes[^1]);
                    pathNodes.RemoveAt(pathNodes.Count - 1);
                    pathEdges.RemoveAt(pathEdges.Count - 1);
                }
                continue;
            }

            var edge = frame.Current;
            var nextNode = edge.Target;
            if (visited.Contains(nextNode))
                continue;

            visited.Add(nextNode);
            pathNodes.Add(nextNode);
            pathEdges.Add(edge);

            if (pathNodes.Count > maxHops + 1)
            {
                // Path too long: undo this step.
                visited.Remove(nextNode);
                pathNodes.RemoveAt(pathNodes.Count - 1);
                pathEdges.RemoveAt(pathEdges.Count - 1);
                continue;
            }

            if (nextNode == end)
            {
                paths.Add(new Path(new List<NodeRef>(pathNodes), new List<Edge>(pathEdges)));
                visited.Remove(nextNode);
                pathNodes.RemoveAt(pathNodes.Count - 1);
                pathEdges.RemoveAt(pathEdges.Count - 1);
                continue;
            }

            stack.Add(EdgesFrom(nextNode).GetEnumerator());
        }

        return paths;
    }

    /// <summary>Check if a path exists between two nodes.</summary>
    public bool PathExists(NodeRef start, NodeRef end, string? relType = null,
                           int maxHops = 10) =>
        ShortestPath(start, end, relType, maxHops) is not null;

    // =========================================================================
    // Graph Analysis
    // =========================================================================

    /// <summary>Count incoming edges.</summary>
    public int InDegree(NodeRef nodeRef) =>
        _inEdges.TryGetValue(nodeRef.Key, out var inList) ? inList.Count : 0;

    /// <summary>Count outgoing edges.</summary>
    public int OutDegree(NodeRef nodeRef) =>
        _outEdges.TryGetValue(nodeRef.Key, out var outList) ? outList.Count : 0;

    /// <summary>
    /// Total degree: in + out for directed graphs, unique incident edges for
    /// undirected graphs (the auto-added reverse twin is not counted twice).
    /// </summary>
    public int Degree(NodeRef nodeRef)
    {
        if (Directed)
            return InDegree(nodeRef) + OutDegree(nodeRef);

        var pairs = new HashSet<(NodeRef, NodeRef)>();
        void AddPair(Edge e)
        {
            var pair = string.CompareOrdinal(e.Source.Key, e.Target.Key) <= 0
                ? (e.Source, e.Target)
                : (e.Target, e.Source);
            pairs.Add(pair);
        }
        if (_outEdges.TryGetValue(nodeRef.Key, out var outList))
        {
            foreach (var e in outList) AddPair(e);
        }
        if (_inEdges.TryGetValue(nodeRef.Key, out var inList))
        {
            foreach (var e in inList) AddPair(e);
        }
        return pairs.Count;
    }

    /// <summary>Check if the graph is connected (ignoring edge direction).</summary>
    public bool IsConnected()
    {
        var totalNodes = NodeCount();
        if (totalNodes == 0)
            return true;

        NodeRef start = default;
        var found = false;
        foreach (var node in Nodes())
        {
            start = node.Ref;
            found = true;
            break;
        }
        if (!found)
            return true;

        var visited = new HashSet<NodeRef> { start };
        var queue = new Queue<NodeRef>();
        queue.Enqueue(start);

        while (queue.Count > 0)
        {
            var current = queue.Dequeue();
            foreach (var neighbor in Neighbors(current, null, Direction.Both))
            {
                if (visited.Add(neighbor))
                    queue.Enqueue(neighbor);
            }
        }

        return visited.Count == totalNodes;
    }

    /// <summary>
    /// Check if the graph has cycles (iterative, no recursion). For directed
    /// graphs this finds directed cycles; for undirected graphs it uses
    /// parent-edge tracking so a single undirected edge (stored as two
    /// directed edges) is not reported as a cycle.
    /// </summary>
    public bool HasCycle(string? relType = null) =>
        Directed ? HasCycleDirected(relType) : HasCycleUndirected(relType);

    private bool HasCycleDirected(string? relType)
    {
        // 0 = white (unvisited), 1 = gray (on stack), 2 = black (done)
        var color = new Dictionary<string, int>();

        foreach (var node in Nodes())
        {
            var startKey = node.Key;
            if (color.TryGetValue(startKey, out var c) && c != 0)
                continue;

            var stack = new List<(string Key, int Idx)>();
            color[startKey] = 1;
            stack.Add((startKey, 0));

            while (stack.Count > 0)
            {
                var (key, idx) = stack[^1];
                _outEdges.TryGetValue(key, out var outList);

                var descended = false;
                while (outList is not null && idx < outList.Count)
                {
                    var edge = outList[idx++];
                    stack[^1] = (key, idx);
                    if (relType is not null && edge.RelType != relType)
                        continue;

                    var targetKey = edge.Target.Key;
                    color.TryGetValue(targetKey, out var targetColor);

                    if (targetColor == 1)
                        return true; // back edge -> cycle
                    if (targetColor == 0)
                    {
                        color[targetKey] = 1;
                        stack.Add((targetKey, 0));
                        descended = true;
                        break;
                    }
                }

                if (!descended)
                {
                    color[stack[^1].Key] = 2;
                    stack.RemoveAt(stack.Count - 1);
                }
            }
        }
        return false;
    }

    private bool HasCycleUndirected(string? relType)
    {
        var visited = new HashSet<string>();

        foreach (var node in Nodes())
        {
            var startKey = node.Key;
            if (visited.Contains(startKey))
                continue;

            // Frame: (node key, edge index, key of the stored reverse of the entering edge)
            var stack = new List<(string Key, int Idx, string SkipEdgeKey)>();
            visited.Add(startKey);
            stack.Add((startKey, 0, ""));

            while (stack.Count > 0)
            {
                var (key, idx, skipEdgeKey) = stack[^1];
                _outEdges.TryGetValue(key, out var outList);

                var descended = false;
                while (outList is not null && idx < outList.Count)
                {
                    var edge = outList[idx++];
                    stack[^1] = (key, idx, skipEdgeKey);
                    if (relType is not null && edge.RelType != relType)
                        continue;
                    if (edge.Key == skipEdgeKey)
                        continue; // don't go back along the entering edge

                    var targetKey = edge.Target.Key;
                    if (visited.Contains(targetKey))
                        return true; // revisit via another edge -> cycle

                    visited.Add(targetKey);
                    // Reverse of (u -> v) as stored is rel:v:u
                    var skip = edge.RelType + ":" + edge.Target.Key + ":" + edge.Source.Key;
                    stack.Add((targetKey, 0, skip));
                    descended = true;
                    break;
                }

                if (!descended)
                    stack.RemoveAt(stack.Count - 1);
            }
        }
        return false;
    }

    /// <summary>Get all connected components (ignoring edge direction).</summary>
    public List<HashSet<NodeRef>> ConnectedComponents()
    {
        var visited = new HashSet<NodeRef>();
        var components = new List<HashSet<NodeRef>>();

        foreach (var node in Nodes())
        {
            if (visited.Contains(node.Ref))
                continue;

            var component = new HashSet<NodeRef>();
            var queue = new Queue<NodeRef>();
            queue.Enqueue(node.Ref);

            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                if (!visited.Add(current))
                    continue;
                component.Add(current);
                foreach (var neighbor in Neighbors(current, null, Direction.Both))
                {
                    if (!visited.Contains(neighbor))
                        queue.Enqueue(neighbor);
                }
            }

            components.Add(component);
        }

        return components;
    }

    // =========================================================================
    // Query Pattern Syntax
    // =========================================================================

    /// <summary>
    /// Execute a simple pattern query.
    ///
    /// Pattern syntax:
    ///   :type:id -[:REL]-> *           (single hop)
    ///   :type:id -[:REL*N]-> *         (N hops)
    ///   :type:id -[:REL*1..3]-> *      (1-3 hops range)
    /// </summary>
    public List<NodeRef> Query(string pattern)
    {
        var p = pattern.Trim();

        var hopMatch = System.Text.RegularExpressions.Regex.Match(
            p, @"^:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*$");
        if (hopMatch.Success)
        {
            return MultiHop(
                new NodeRef(hopMatch.Groups[1].Value, hopMatch.Groups[2].Value),
                hopMatch.Groups[3].Value,
                int.Parse(hopMatch.Groups[4].Value,
                          System.Globalization.CultureInfo.InvariantCulture));
        }

        var rangeMatch = System.Text.RegularExpressions.Regex.Match(
            p, @"^:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*$");
        if (rangeMatch.Success)
        {
            return MultiHopRange(
                new NodeRef(rangeMatch.Groups[1].Value, rangeMatch.Groups[2].Value),
                rangeMatch.Groups[3].Value,
                int.Parse(rangeMatch.Groups[4].Value,
                          System.Globalization.CultureInfo.InvariantCulture),
                int.Parse(rangeMatch.Groups[5].Value,
                          System.Globalization.CultureInfo.InvariantCulture));
        }

        var simpleMatch = System.Text.RegularExpressions.Regex.Match(
            p, @"^:(\w+):(\w+)\s*-\[:(\w+)\]->\s*\*$");
        if (simpleMatch.Success)
        {
            return Neighbors(
                new NodeRef(simpleMatch.Groups[1].Value, simpleMatch.Groups[2].Value),
                simpleMatch.Groups[3].Value);
        }

        throw new GraphError($"Invalid query pattern: {pattern}");
    }

    // =========================================================================
    // Fluent API Entry Point
    // =========================================================================

    /// <summary>Start a fluent traversal from a node.</summary>
    public GraphTraversal Start(NodeRef nodeRef) => new(this, nodeRef);

    public override string ToString() =>
        $"ISONGraph(name={Name}, nodes={NodeCount()}, edges={EdgeCount()})";
}

// =============================================================================
// Fluent Traversal API
// =============================================================================

/// <summary>Fluent API for graph traversal.</summary>
public sealed class GraphTraversal
{
    private readonly ISONGraph _graph;
    private HashSet<NodeRef> _current;
    private readonly HashSet<NodeRef> _visited;

    public GraphTraversal(ISONGraph graph, NodeRef start)
    {
        _graph = graph;
        _current = new HashSet<NodeRef> { start };
        _visited = new HashSet<NodeRef> { start };
    }

    /// <summary>Traverse one hop following edges.</summary>
    public GraphTraversal Hop(string? relType = null, Direction direction = Direction.Out,
                              Func<Node, bool>? where = null)
    {
        var nextLevel = new HashSet<NodeRef>();

        foreach (var nodeRef in _current)
        {
            foreach (var neighbor in _graph.Neighbors(nodeRef, relType, direction))
            {
                if (_visited.Contains(neighbor))
                    continue;
                if (where is null)
                {
                    nextLevel.Add(neighbor);
                }
                else if (_graph.HasNode(neighbor) && where(_graph.GetNode(neighbor)))
                {
                    nextLevel.Add(neighbor);
                }
            }
        }

        _visited.UnionWith(nextLevel);
        _current = nextLevel;
        return this;
    }

    /// <summary>Traverse N hops.</summary>
    public GraphTraversal Hops(int n, string? relType = null,
                               Direction direction = Direction.Out)
    {
        for (var i = 0; i < n; i++)
            Hop(relType, direction);
        return this;
    }

    /// <summary>Filter current nodes.</summary>
    public GraphTraversal Filter(Func<Node, bool> fn)
    {
        _current = _current
            .Where(r => _graph.HasNode(r) && fn(_graph.GetNode(r)))
            .ToHashSet();
        return this;
    }

    /// <summary>Return current node references.</summary>
    public List<NodeRef> Collect() => _current.ToList();

    /// <summary>Return current nodes as Node objects.</summary>
    public List<Node> CollectNodes() =>
        _current.Where(_graph.HasNode).Select(_graph.GetNode).ToList();

    /// <summary>Count current nodes.</summary>
    public int Count() => _current.Count;

    /// <summary>Get the first node reference, or null when empty.</summary>
    public NodeRef? First()
    {
        foreach (var nodeRef in _current)
            return nodeRef;
        return null;
    }
}
