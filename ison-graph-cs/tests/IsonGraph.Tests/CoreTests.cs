// Tests for the ISONGraph core: CRUD, traversal, path finding, analysis,
// undirected behaviors, fluent traversal, and pattern queries.

using Xunit;

namespace IsonGraph.Tests;

internal static class Props
{
    public static Dictionary<string, string> Of(params (string Key, string Value)[] pairs) =>
        pairs.ToDictionary(p => p.Key, p => p.Value);
}

public class NodeTests
{
    [Fact]
    public void AddNode()
    {
        var graph = new ISONGraph();
        var node = graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));

        Assert.Equal("person", node.Type);
        Assert.Equal("1", node.Id);
        Assert.Equal("Alice", node.Properties["name"]);
        Assert.Equal("30", node.Properties["age"]);
    }

    [Fact]
    public void GetNode()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice")));
        Assert.Equal("Alice", graph.GetNode("person", "1").Properties["name"]);
        Assert.Equal("Alice", graph.GetNode(new NodeRef("person", "1")).Properties["name"]);
    }

    [Fact]
    public void GetNodeNotFound()
    {
        var graph = new ISONGraph();
        Assert.Throws<NodeNotFoundError>(() => graph.GetNode("person", "999"));
    }

    [Fact]
    public void HasNode()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");

        Assert.True(graph.HasNode("person", "1"));
        Assert.False(graph.HasNode("person", "2"));
        Assert.False(graph.HasNode("company", "1"));
    }

    [Fact]
    public void DuplicateNodeError()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        Assert.Throws<DuplicateNodeError>(() => graph.AddNode("person", "1"));
    }

    [Fact]
    public void NodeTypeWithColonRejected()
    {
        var graph = new ISONGraph();
        var ex = Assert.Throws<ArgumentException>(() => graph.AddNode("per:son", "1"));
        Assert.Contains(":", ex.Message);
    }

    [Fact]
    public void NodeIdWithColonRejected()
    {
        var graph = new ISONGraph();
        Assert.Throws<ArgumentException>(() => graph.AddNode("person", "1:2"));
    }

    // ':' and '|' are structurally significant to the wire format
    // ('type:id' references, ISONL columns); allowing them in a node type,
    // node id, or relationship type builds a graph that throws on
    // ToIson()/ToIsonl() round-trip instead of failing loudly at
    // construction.
    [Fact]
    public void NodeTypeWithPipeRejected()
    {
        var graph = new ISONGraph();
        var ex = Assert.Throws<ArgumentException>(() => graph.AddNode("per|son", "1"));
        Assert.Contains("|", ex.Message);
    }

    [Fact]
    public void NodeIdWithPipeRejected()
    {
        var graph = new ISONGraph();
        Assert.Throws<ArgumentException>(() => graph.AddNode("person", "1|2"));
    }

    [Fact]
    public void EdgeRelTypeWithColonOrPipeRejected()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        Assert.Throws<ArgumentException>(() =>
            graph.AddEdge("KN:OWS", new("person", "1"), new("person", "2")));
        Assert.Throws<ArgumentException>(() =>
            graph.AddEdge("KN|OWS", new("person", "1"), new("person", "2")));
        Assert.Equal(0, graph.EdgeCount());
    }

    [Fact]
    public void ValidIdentifiersWithSpacesStillAllowed()
    {
        var graph = new ISONGraph();
        graph.AddNode("a type", "an id-1");
        graph.AddNode("b", "2");
        var edge = graph.AddEdge("shares border with", new("a type", "an id-1"), new("b", "2"));
        Assert.Equal("shares border with", edge.RelType);
    }

    [Fact]
    public void RemoveNode()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        graph.RemoveNode("person", "1");

        Assert.False(graph.HasNode("person", "1"));
        Assert.Equal(0, graph.EdgeCount()); // edges removed with the node
    }

    [Fact]
    public void RemoveNodeNotFound()
    {
        var graph = new ISONGraph();
        Assert.Throws<NodeNotFoundError>(() => graph.RemoveNode("person", "1"));
    }

    [Fact]
    public void RemoveNodeDropsEmptyType()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.RemoveNode("person", "1");
        Assert.Empty(graph.NodeTypes());
        Assert.Equal(0, graph.NodeCount("person"));
    }

    [Fact]
    public void UpdateNode()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));

        graph.UpdateNode("person", "1", Props.Of(("age", "31"), ("email", "alice@example.com")));

        var node = graph.GetNode("person", "1");
        Assert.Equal("31", node.Properties["age"]);
        Assert.Equal("alice@example.com", node.Properties["email"]);
        Assert.Equal("Alice", node.Properties["name"]);
    }

    [Fact]
    public void UpdateNodeNotFound()
    {
        var graph = new ISONGraph();
        Assert.Throws<NodeNotFoundError>(
            () => graph.UpdateNode("person", "1", Props.Of(("a", "b"))));
    }

    [Fact]
    public void NodeCount()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "1");

        Assert.Equal(3, graph.NodeCount());
        Assert.Equal(2, graph.NodeCount("person"));
        Assert.Equal(1, graph.NodeCount("company"));
        Assert.Equal(0, graph.NodeCount("missing"));
    }

    [Fact]
    public void NodeTypes()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("company", "1");
        graph.AddNode("post", "1");

        Assert.Equal(new HashSet<string> { "person", "company", "post" },
                     graph.NodeTypes().ToHashSet());
    }

    [Fact]
    public void NodesIterationFiltersByType()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "1");

        Assert.Equal(2, graph.Nodes("person").Count());
        Assert.Equal(3, graph.Nodes().Count());
        Assert.Empty(graph.Nodes("missing"));
    }

    [Fact]
    public void NodeRefHelpers()
    {
        var nodeRef = new NodeRef("person", "1");
        Assert.Equal("person:1", nodeRef.Key);
        Assert.Equal(":person:1", nodeRef.ToIsonRef());
        Assert.Equal(":person:1", nodeRef.ToString());
    }
}

public class EdgeTests
{
    [Fact]
    public void AddEdge()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");

        var edge = graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                                 Props.Of(("since", "2020")));

        Assert.Equal("KNOWS", edge.RelType);
        Assert.Equal(new NodeRef("person", "1"), edge.Source);
        Assert.Equal(new NodeRef("person", "2"), edge.Target);
        Assert.Equal("2020", edge.Properties["since"]);
    }

    [Fact]
    public void EdgeRequiresNodes()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        Assert.Throws<NodeNotFoundError>(
            () => graph.AddEdge("KNOWS", new("person", "1"), new("person", "999")));
        Assert.Throws<NodeNotFoundError>(
            () => graph.AddEdge("KNOWS", new("person", "999"), new("person", "1")));
    }

    [Fact]
    public void DuplicateEdgeError()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.Throws<DuplicateEdgeError>(
            () => graph.AddEdge("KNOWS", new("person", "1"), new("person", "2")));
    }

    [Fact]
    public void HasEdge()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.True(graph.HasEdge("KNOWS", new("person", "1"), new("person", "2")));
        Assert.False(graph.HasEdge("KNOWS", new("person", "2"), new("person", "1")));
    }

    [Fact]
    public void GetEdge()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                      Props.Of(("since", "2020")));

        var edge = graph.GetEdge("KNOWS", new("person", "1"), new("person", "2"));
        Assert.Equal("2020", edge.Properties["since"]);
        Assert.Throws<EdgeNotFoundError>(
            () => graph.GetEdge("KNOWS", new("person", "2"), new("person", "1")));
    }

    [Fact]
    public void RemoveEdge()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        graph.RemoveEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.False(graph.HasEdge("KNOWS", new("person", "1"), new("person", "2")));
        Assert.Throws<EdgeNotFoundError>(
            () => graph.RemoveEdge("KNOWS", new("person", "1"), new("person", "2")));
    }

    [Fact]
    public void UndirectedAddsReverseEdge()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.True(graph.HasEdge("KNOWS", new("person", "1"), new("person", "2")));
        Assert.True(graph.HasEdge("KNOWS", new("person", "2"), new("person", "1")));
        Assert.Equal(2, graph.EdgeCount());
    }

    [Fact]
    public void RemoveEdgeUndirectedRemovesBothDirections()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        graph.RemoveEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.False(graph.HasEdge("KNOWS", new("person", "1"), new("person", "2")));
        Assert.False(graph.HasEdge("KNOWS", new("person", "2"), new("person", "1")));
        Assert.Equal(0, graph.EdgeCount());
    }

    [Fact]
    public void RemoveEdgeUndirectedByReverseDirection()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        // Removing via the reverse direction also removes both.
        graph.RemoveEdge("KNOWS", new("person", "2"), new("person", "1"));
        Assert.Equal(0, graph.EdgeCount());
    }

    [Fact]
    public void EdgeCount()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "1");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "1"));

        Assert.Equal(2, graph.EdgeCount());
        Assert.Equal(1, graph.EdgeCount("KNOWS"));
        Assert.Equal(1, graph.EdgeCount("WORKS_AT"));
        Assert.Equal(0, graph.EdgeCount("MISSING"));
    }

    [Fact]
    public void EdgeTypes()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "1");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "1"));

        Assert.Equal(new HashSet<string> { "KNOWS", "WORKS_AT" },
                     graph.EdgeTypes().ToHashSet());
    }

    [Fact]
    public void EdgesFilters()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
        graph.AddEdge("LIKES", new("person", "1"), new("person", "3"));

        Assert.Equal(3, graph.Edges().Count());
        Assert.Equal(2, graph.Edges("KNOWS").Count());
        Assert.Equal(2, graph.Edges(source: new NodeRef("person", "1")).Count());
        Assert.Single(graph.Edges("KNOWS", source: new NodeRef("person", "1")));
        Assert.Equal(2, graph.Edges(target: new NodeRef("person", "3")).Count());
    }

    [Fact]
    public void SelfLoopAllowed()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "1"));
        Assert.True(graph.HasEdge("KNOWS", new("person", "1"), new("person", "1")));
    }
}

public class TraversalTests
{
    private readonly ISONGraph _graph;

    public TraversalTests()
    {
        // Chain: 1 -> 2 -> 3 -> 4 -> 5
        _graph = new ISONGraph();
        for (var i = 1; i <= 5; i++)
            _graph.AddNode("person", i.ToString(), Props.Of(("name", $"Person{i}")));
        for (var i = 1; i <= 4; i++)
            _graph.AddEdge("KNOWS", new("person", i.ToString()), new("person", (i + 1).ToString()));
    }

    [Fact]
    public void Neighbors()
    {
        var neighbors = _graph.Neighbors(new("person", "2"), "KNOWS");
        Assert.Equal(new List<NodeRef> { new("person", "3") }, neighbors);
    }

    [Fact]
    public void NeighborsIncoming()
    {
        var neighbors = _graph.Neighbors(new("person", "2"), "KNOWS", Direction.In);
        Assert.Equal(new List<NodeRef> { new("person", "1") }, neighbors);
    }

    [Fact]
    public void NeighborsBoth()
    {
        var neighbors = _graph.Neighbors(new("person", "2"), "KNOWS", Direction.Both);
        Assert.Equal(new HashSet<NodeRef> { new("person", "1"), new("person", "3") },
                     neighbors.ToHashSet());
    }

    [Fact]
    public void NeighborsOfUnknownNodeEmpty()
    {
        Assert.Empty(_graph.Neighbors(new("person", "999")));
    }

    [Fact]
    public void MultiHop1()
    {
        Assert.Equal(new List<NodeRef> { new("person", "2") },
                     _graph.MultiHop(new("person", "1"), "KNOWS", 1));
    }

    [Fact]
    public void MultiHop2()
    {
        Assert.Equal(new List<NodeRef> { new("person", "3") },
                     _graph.MultiHop(new("person", "1"), "KNOWS", 2));
    }

    [Fact]
    public void MultiHop3()
    {
        Assert.Equal(new List<NodeRef> { new("person", "4") },
                     _graph.MultiHop(new("person", "1"), "KNOWS", 3));
    }

    [Fact]
    public void MultiHopZeroReturnsStart()
    {
        Assert.Equal(new List<NodeRef> { new("person", "1") },
                     _graph.MultiHop(new("person", "1"), "KNOWS", 0));
    }

    [Fact]
    public void MultiHopRange()
    {
        var result = _graph.MultiHopRange(new("person", "1"), "KNOWS", 1, 3);
        Assert.Equal(
            new HashSet<NodeRef> { new("person", "2"), new("person", "3"), new("person", "4") },
            result.ToHashSet());
    }

    [Fact]
    public void MultiHopRangeMinBound()
    {
        var result = _graph.MultiHopRange(new("person", "1"), "KNOWS", 2, 3);
        Assert.Equal(new HashSet<NodeRef> { new("person", "3"), new("person", "4") },
                     result.ToHashSet());
    }

    [Fact]
    public void TraversePattern()
    {
        _graph.AddNode("company", "100", Props.Of(("name", "Acme")));
        _graph.AddEdge("WORKS_AT", new("person", "2"), new("company", "100"));

        var result = _graph.Traverse(
            new("person", "1"),
            new[] { ("KNOWS", Direction.Out), ("WORKS_AT", Direction.Out) });
        Assert.Equal(new List<NodeRef> { new("company", "100") }, result);
    }

    [Fact]
    public void TraversePatternWithFilter()
    {
        var result = _graph.Traverse(
            new("person", "1"),
            new[] { ("KNOWS", Direction.Out) },
            node => node.Properties.GetValueOrDefault("name") == "Person2");
        Assert.Equal(new List<NodeRef> { new("person", "2") }, result);

        var none = _graph.Traverse(
            new("person", "1"),
            new[] { ("KNOWS", Direction.Out) },
            _ => false);
        Assert.Empty(none);
    }
}

public class PathFindingTests
{
    private readonly ISONGraph _graph;

    public PathFindingTests()
    {
        // 1 -> 2 -> 3
        //      |    |
        //      v    v
        //      4 -> 5
        _graph = new ISONGraph();
        for (var i = 1; i <= 5; i++)
            _graph.AddNode("person", i.ToString());
        _graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        _graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
        _graph.AddEdge("KNOWS", new("person", "2"), new("person", "4"));
        _graph.AddEdge("KNOWS", new("person", "3"), new("person", "5"));
        _graph.AddEdge("KNOWS", new("person", "4"), new("person", "5"));
    }

    [Fact]
    public void ShortestPath()
    {
        var path = _graph.ShortestPath(new("person", "1"), new("person", "5"));

        Assert.NotNull(path);
        Assert.Equal(3, path.Length);
        Assert.Equal(new NodeRef("person", "1"), path.Start);
        Assert.Equal(new NodeRef("person", "5"), path.End);
    }

    [Fact]
    public void ShortestPathSameNode()
    {
        var path = _graph.ShortestPath(new("person", "1"), new("person", "1"));
        Assert.NotNull(path);
        Assert.Equal(0, path.Length);
    }

    [Fact]
    public void NoPath()
    {
        _graph.AddNode("person", "99");
        Assert.Null(_graph.ShortestPath(new("person", "1"), new("person", "99")));
    }

    [Fact]
    public void PathExists()
    {
        Assert.True(_graph.PathExists(new("person", "1"), new("person", "5")));
        Assert.False(_graph.PathExists(new("person", "5"), new("person", "1"))); // directed
    }

    [Fact]
    public void AllPaths()
    {
        var paths = _graph.AllPaths(new("person", "1"), new("person", "5"));
        Assert.Equal(2, paths.Count); // 1->2->3->5 and 1->2->4->5
        foreach (var path in paths)
        {
            Assert.Equal(new NodeRef("person", "1"), path.Start);
            Assert.Equal(new NodeRef("person", "5"), path.End);
            Assert.Equal(3, path.Length);
        }
    }

    [Fact]
    public void AllPathsMaxHopsPrunes()
    {
        Assert.Empty(_graph.AllPaths(new("person", "1"), new("person", "5"), maxHops: 2));
        Assert.Equal(2, _graph.AllPaths(new("person", "1"), new("person", "5"), maxHops: 3).Count);
    }

    [Fact]
    public void AllPathsSameNode()
    {
        var paths = _graph.AllPaths(new("person", "1"), new("person", "1"));
        Assert.Single(paths);
        Assert.Equal(0, paths[0].Length);
    }

    [Fact]
    public void ShortestPathMaxHopsBoundary()
    {
        // 1 -> 2 -> 3 needs 2 hops; maxHops must be a strict upper bound.
        Assert.Null(_graph.ShortestPath(new("person", "1"), new("person", "3"), maxHops: 1));

        var path = _graph.ShortestPath(new("person", "1"), new("person", "3"), maxHops: 2);
        Assert.NotNull(path);
        Assert.Equal(2, path.Length);

        // A direct edge is still found with maxHops = 1.
        var direct = _graph.ShortestPath(new("person", "1"), new("person", "2"), maxHops: 1);
        Assert.NotNull(direct);
        Assert.Equal(1, direct.Length);
    }

    [Fact]
    public void ShortestPathRelTypeFilter()
    {
        _graph.AddEdge("BLOCKS", new("person", "1"), new("person", "5"));
        var viaKnows = _graph.ShortestPath(new("person", "1"), new("person", "5"), "KNOWS");
        Assert.NotNull(viaKnows);
        Assert.Equal(3, viaKnows.Length);

        var viaBlocks = _graph.ShortestPath(new("person", "1"), new("person", "5"), "BLOCKS");
        Assert.NotNull(viaBlocks);
        Assert.Equal(1, viaBlocks.Length);
    }

    [Fact]
    public void ShortestPathDirectionIn()
    {
        var path = _graph.ShortestPath(new("person", "5"), new("person", "1"),
                                       direction: Direction.In);
        Assert.NotNull(path);
        Assert.Equal(3, path.Length);
    }
}

public class GraphAnalysisTests
{
    [Fact]
    public void Degrees()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "3"));

        Assert.Equal(2, graph.OutDegree(new("person", "1")));
        Assert.Equal(0, graph.InDegree(new("person", "1")));
        Assert.Equal(1, graph.InDegree(new("person", "2")));
        Assert.Equal(2, graph.Degree(new("person", "1")));
    }

    [Fact]
    public void UndirectedDegreeCountsUniqueEdges()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "3"));

        // The reverse twin does not double the degree.
        Assert.Equal(2, graph.Degree(new("person", "1")));
        Assert.Equal(1, graph.Degree(new("person", "2")));
    }

    [Fact]
    public void IsConnected()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.True(graph.IsConnected());

        graph.AddNode("person", "99");
        Assert.False(graph.IsConnected());
    }

    [Fact]
    public void EmptyGraphIsConnected()
    {
        Assert.True(new ISONGraph().IsConnected());
    }

    [Fact]
    public void HasCycleDirected()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));

        Assert.False(graph.HasCycle());

        graph.AddEdge("KNOWS", new("person", "3"), new("person", "1"));
        Assert.True(graph.HasCycle());
    }

    [Fact]
    public void HasCyclePerRelType()
    {
        var graph = new ISONGraph();
        graph.AddNode("n", "1");
        graph.AddNode("n", "2");
        graph.AddEdge("A", new("n", "1"), new("n", "2"));
        graph.AddEdge("A", new("n", "2"), new("n", "1")); // cycle via A only
        graph.AddEdge("B", new("n", "1"), new("n", "2"));

        Assert.True(graph.HasCycle("A"));
        Assert.False(graph.HasCycle("B"));
        Assert.True(graph.HasCycle());
    }

    [Fact]
    public void HasCycleSelfLoop()
    {
        var graph = new ISONGraph();
        graph.AddNode("n", "1");
        graph.AddEdge("LOOP", new("n", "1"), new("n", "1"));
        Assert.True(graph.HasCycle());
    }

    [Fact]
    public void HasCycleUndirectedSingleEdgeIsNotCycle()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        Assert.False(graph.HasCycle());

        // An acyclic undirected chain is not a cycle either.
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
        Assert.False(graph.HasCycle());
    }

    [Fact]
    public void HasCycleUndirectedTriangle()
    {
        var graph = new ISONGraph(directed: false);
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
        graph.AddEdge("KNOWS", new("person", "3"), new("person", "1"));

        Assert.True(graph.HasCycle());
    }

    [Fact]
    public void ConnectedComponents()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("person", "3");
        graph.AddNode("person", "4");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "3"), new("person", "4"));

        var components = graph.ConnectedComponents();
        Assert.Equal(2, components.Count);
        Assert.All(components, c => Assert.Equal(2, c.Count));
    }

    [Fact]
    public void ConnectedComponentsEmptyGraph()
    {
        Assert.Empty(new ISONGraph().ConnectedComponents());
    }
}

public class DeepGraphTests
{
    // Deep chain: iterative DFS must not overflow the call stack.
    private const int Depth = 2000;

    private static ISONGraph BuildChain()
    {
        var graph = new ISONGraph();
        for (var i = 1; i <= Depth; i++)
            graph.AddNode("node", i.ToString());
        for (var i = 1; i < Depth; i++)
            graph.AddEdge("NEXT", new("node", i.ToString()), new("node", (i + 1).ToString()));
        return graph;
    }

    [Fact]
    public void HasCycleDeepChain()
    {
        var graph = BuildChain();
        Assert.False(graph.HasCycle());

        graph.AddEdge("NEXT", new("node", Depth.ToString()), new("node", "1"));
        Assert.True(graph.HasCycle());
    }

    [Fact]
    public void AllPathsDeepChain()
    {
        var graph = BuildChain();
        var paths = graph.AllPaths(new("node", "1"), new("node", Depth.ToString()),
                                   maxHops: Depth);
        Assert.Single(paths);
        Assert.Equal(Depth - 1, paths[0].Length);
    }

    [Fact]
    public void HasCycleDeepChainUndirected()
    {
        var graph = new ISONGraph(directed: false);
        for (var i = 1; i <= Depth; i++)
            graph.AddNode("node", i.ToString());
        for (var i = 1; i < Depth; i++)
            graph.AddEdge("NEXT", new("node", i.ToString()), new("node", (i + 1).ToString()));
        Assert.False(graph.HasCycle());
    }
}

public class FluentTraversalTests
{
    private readonly ISONGraph _graph;

    public FluentTraversalTests()
    {
        _graph = new ISONGraph();
        _graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));
        _graph.AddNode("person", "2", Props.Of(("name", "Bob"), ("age", "25")));
        _graph.AddNode("person", "3", Props.Of(("name", "Charlie"), ("age", "35")));
        _graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        _graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
    }

    [Fact]
    public void Hop()
    {
        var result = _graph.Start(new("person", "1")).Hop("KNOWS").Collect();
        Assert.Equal(new List<NodeRef> { new("person", "2") }, result);
    }

    [Fact]
    public void Hops()
    {
        var result = _graph.Start(new("person", "1")).Hops(2, "KNOWS").Collect();
        Assert.Equal(new List<NodeRef> { new("person", "3") }, result);
    }

    [Fact]
    public void FilterKeepsMatching()
    {
        var result = _graph.Start(new("person", "1"))
            .Hop("KNOWS")
            .Hop("KNOWS")
            .Filter(n => int.Parse(n.Properties.GetValueOrDefault("age", "0")) > 30)
            .Collect();

        Assert.Equal(new List<NodeRef> { new("person", "3") }, result);
    }

    [Fact]
    public void CollectNodes()
    {
        var nodes = _graph.Start(new("person", "1")).Hop("KNOWS").CollectNodes();
        Assert.Single(nodes);
        Assert.Equal("Bob", nodes[0].Properties["name"]);
    }

    [Fact]
    public void CountAndFirst()
    {
        var traversal = _graph.Start(new("person", "1")).Hop("KNOWS");
        Assert.Equal(1, traversal.Count());
        Assert.Equal(new NodeRef("person", "2"), traversal.First());
    }

    [Fact]
    public void FirstOnEmptyIsNull()
    {
        var traversal = _graph.Start(new("person", "3")).Hop("KNOWS");
        Assert.Equal(0, traversal.Count());
        Assert.Null(traversal.First());
    }

    [Fact]
    public void HopWithWherePredicate()
    {
        var result = _graph.Start(new("person", "1"))
            .Hop("KNOWS", Direction.Out, n => n.Properties["name"] == "Nobody")
            .Collect();
        Assert.Empty(result);
    }
}

public class QueryPatternTests
{
    private readonly ISONGraph _graph;

    public QueryPatternTests()
    {
        _graph = new ISONGraph();
        for (var i = 1; i <= 4; i++)
            _graph.AddNode("person", i.ToString());
        _graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        _graph.AddEdge("KNOWS", new("person", "2"), new("person", "3"));
        _graph.AddEdge("KNOWS", new("person", "3"), new("person", "4"));
    }

    [Fact]
    public void SimpleQuery()
    {
        Assert.Equal(new List<NodeRef> { new("person", "2") },
                     _graph.Query(":person:1 -[:KNOWS]-> *"));
    }

    [Fact]
    public void MultiHopQuery()
    {
        Assert.Equal(new List<NodeRef> { new("person", "3") },
                     _graph.Query(":person:1 -[:KNOWS*2]-> *"));
    }

    [Fact]
    public void RangeQuery()
    {
        var result = _graph.Query(":person:1 -[:KNOWS*1..2]-> *");
        Assert.Equal(new HashSet<NodeRef> { new("person", "2"), new("person", "3") },
                     result.ToHashSet());
    }

    [Fact]
    public void InvalidPatternThrows()
    {
        Assert.ThrowsAny<GraphError>(() => _graph.Query("nonsense"));
    }
}
