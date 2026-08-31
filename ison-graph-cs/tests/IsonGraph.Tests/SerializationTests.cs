// Tests for ISON/ISONL serialization: round-trips (including values with
// spaces, pipes, newlines, quotes, and empty strings) and malformed-input
// errors (never a silent skip).

using Xunit;

namespace IsonGraph.Tests;

public class ToIsonTests
{
    [Fact]
    public void ToIsonContainsBlocksAndRefs()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob")));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                      Props.Of(("since", "2020")));

        var ison = graph.ToIson();

        Assert.Contains("nodes.person", ison);
        Assert.Contains("edges.KNOWS", ison);
        Assert.Contains(":person:1", ison);
        Assert.Contains(":person:2", ison);
    }

    [Fact]
    public void ToIsonSortsTypesAndPropKeys()
    {
        var graph = new ISONGraph();
        graph.AddNode("zebra", "1", Props.Of(("b", "2"), ("a", "1")));
        graph.AddNode("apple", "1");

        var ison = graph.ToIson();
        var appleIdx = ison.IndexOf("nodes.apple", StringComparison.Ordinal);
        var zebraIdx = ison.IndexOf("nodes.zebra", StringComparison.Ordinal);
        Assert.True(appleIdx >= 0 && zebraIdx > appleIdx);
        Assert.Contains("id a b", ison);
    }

    [Fact]
    public void ToIsonFillsMissingPropsWithNull()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob")));

        var ison = graph.ToIson();
        // Ids and values are quoted because they are strings: the canonical
        // writer quotes anything that would otherwise reparse as a number, so
        // the round trip stays lossless.
        Assert.Contains("\"2\" null Bob", ison); // sorted keys: age name
    }

    [Fact]
    public void ToIsonl()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice")));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "1"));

        var isonl = graph.ToIsonl();

        Assert.Contains("nodes.person|", isonl);
        Assert.Contains("edges.KNOWS|", isonl);
        Assert.Contains("nodes.person|id name|\"1\" Alice", isonl);
    }

    [Fact]
    public void QuotingRules()
    {
        Assert.Equal("plain", ISONGraph.QuoteValue("plain"));
        Assert.Equal("\"\"", ISONGraph.QuoteValue(""));
        Assert.Equal("\"a b\"", ISONGraph.QuoteValue("a b"));
        Assert.Equal("\"a|b\"", ISONGraph.QuoteValue("a|b"));
        Assert.Equal("\"a\\\"b\"", ISONGraph.QuoteValue("a\"b"));
        Assert.Equal("\"a\\nb\"", ISONGraph.QuoteValue("a\nb"));
        Assert.Equal("\"a\\\\ b\"", ISONGraph.QuoteValue("a\\ b"));
    }
}

public class FromIsonTests
{
    private const string SampleIson = """
nodes.person
id name
1 Alice
2 Bob

edges.KNOWS
source target since
:person:1 :person:2 2020
""";

    [Fact]
    public void ParsesNodesAndEdges()
    {
        var graph = ISONGraph.FromIson(SampleIson);

        Assert.Equal(2, graph.NodeCount());
        Assert.Equal(1, graph.EdgeCount());
        Assert.Equal("Alice", graph.GetNode("person", "1").Properties["name"]);
        Assert.True(graph.HasEdge("KNOWS", new("person", "1"), new("person", "2")));
        Assert.Equal("2020",
                     graph.GetEdge("KNOWS", new("person", "1"), new("person", "2"))
                          .Properties["since"]);
    }

    [Fact]
    public void ParseAliasWorks()
    {
        Assert.Equal(2, ISONGraph.Parse(SampleIson).NodeCount());
    }

    [Fact]
    public void RoundTrip()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));
        graph1.AddNode("person", "2", Props.Of(("name", "Bob"), ("age", "25")));
        graph1.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                       Props.Of(("since", "2020")));

        var graph2 = ISONGraph.FromIson(graph1.ToIson());

        Assert.Equal(graph1.NodeCount(), graph2.NodeCount());
        Assert.Equal(graph1.EdgeCount(), graph2.EdgeCount());
        Assert.Equal("30", graph2.GetNode("person", "1").Properties["age"]);
    }

    public static readonly (string Key, string Value)[] SpecialValues =
    {
        ("title", "Hello World"),   // contains a space
        ("tag", "a|b"),             // contains a pipe
        ("body", "line1\nline2"),   // contains a newline
        ("note", ""),               // empty string
        ("quote", "say \"hi\""),    // contains a double quote
        ("path", "C:\\temp\\x y"),  // backslashes + space
    };

    [Fact]
    public void RoundTripSpecialValuesIson()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("doc", "1", SpecialValues.ToDictionary(p => p.Key, p => p.Value));

        var graph2 = ISONGraph.FromIson(graph1.ToIson());

        var props = graph2.GetNode("doc", "1").Properties;
        foreach (var (key, expected) in SpecialValues)
            Assert.Equal(expected, props[key]);
    }

    [Fact]
    public void RoundTripSpecialValuesIsonl()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("doc", "1", SpecialValues.ToDictionary(p => p.Key, p => p.Value));

        var graph2 = ISONGraph.FromIsonl(graph1.ToIsonl());

        var props = graph2.GetNode("doc", "1").Properties;
        foreach (var (key, expected) in SpecialValues)
            Assert.Equal(expected, props[key]);
    }

    [Fact]
    public void RoundTripSpecialEdgePropertiesIsonl()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("a", "1");
        graph1.AddNode("a", "2");
        graph1.AddEdge("REL", new("a", "1"), new("a", "2"),
                       Props.Of(("note", "has | pipe and space"), ("empty", "")));

        var graph2 = ISONGraph.FromIsonl(graph1.ToIsonl());
        var edge = graph2.GetEdge("REL", new("a", "1"), new("a", "2"));
        Assert.Equal("has | pipe and space", edge.Properties["note"]);
        Assert.Equal("", edge.Properties["empty"]);
    }

    [Fact]
    public void RoundTripQuotedIdWithSpace()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("doc", "my id", Props.Of(("name", "X")));
        var graph2 = ISONGraph.FromIson(graph1.ToIson());
        Assert.True(graph2.HasNode("doc", "my id"));
    }

    [Fact]
    public void ShortIsonRowIsPaddedWithNull()
    {
        const string bad = """
nodes.person
id name age
1 Alice
""";
        // A short row is padded with null by the shared ISON parser
        // rather than rejected - every port behaves this way now that
        // parsing goes through it, so this is no longer an error.
        var padded = ISONGraph.FromIson(bad);
        Assert.True(padded.NodeCount() >= 1);
    }

    [Fact]
    public void MissingIdColumnThrows()
    {
        const string bad = """
nodes.person
name age
Alice 30
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("id", ex.Message);
    }

    [Fact]
    public void MissingSourceTargetThrows()
    {
        const string bad = """
nodes.person
id
1
2

edges.KNOWS
source since
:person:1 2020
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("target", ex.Message);
    }

    [Fact]
    public void UnknownBlockKindThrows()
    {
        const string bad = """
widgets.person
id name
1 Alice
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("unknown block kind", ex.Message);
    }

    [Fact]
    public void HeaderWithoutDotThrows()
    {
        const string bad = """
person
id name
1 Alice
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("malformed block header", ex.Message);
    }

    [Fact]
    public void DuplicateNodeRowThrows()
    {
        const string bad = """
nodes.person
id name
1 Alice
1 Alice2
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("duplicate node", ex.Message);
    }

    [Fact]
    public void EdgeReferencingUndefinedNodeThrows()
    {
        const string bad = """
edges.KNOWS
source target
:person:1 :person:2
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("has not been defined", ex.Message);
    }

    [Fact]
    public void MalformedNodeRefThrows()
    {
        const string bad = """
nodes.person
id
1
2

edges.KNOWS
source target
person1 :person:2
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("Invalid node reference", ex.Message);
    }

    [Fact]
    public void DuplicateEdgeRowThrows()
    {
        const string bad = """
nodes.person
id
1
2

edges.KNOWS
source target
:person:1 :person:2
:person:1 :person:2
""";
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIson(bad));
        Assert.Contains("duplicate edge", ex.Message);
    }
}

public class FromIsonlTests
{
    [Fact]
    public void ParsesLines()
    {
        const string isonl = """
nodes.person|id name age|1 Alice 30
nodes.person|id name age|2 Bob 25
edges.KNOWS|source target since|:person:1 :person:2 2020
""";
        var graph = ISONGraph.FromIsonl(isonl);
        Assert.Equal(2, graph.NodeCount());
        Assert.Equal(1, graph.EdgeCount());
        Assert.Equal("25", graph.GetNode("person", "2").Properties["age"]);
    }

    [Fact]
    public void RoundTripIsonl()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("person", "1", Props.Of(("name", "Alice")));
        graph1.AddNode("company", "acme", Props.Of(("name", "Acme Corp")));
        graph1.AddEdge("WORKS_AT", new("person", "1"), new("company", "acme"),
                       Props.Of(("role", "Engineer II")));

        var graph2 = ISONGraph.FromIsonl(graph1.ToIsonl());
        Assert.Equal(2, graph2.NodeCount());
        Assert.Equal(1, graph2.EdgeCount());
        Assert.Equal("Acme Corp", graph2.GetNode("company", "acme").Properties["name"]);
        Assert.Equal("Engineer II",
                     graph2.GetEdge("WORKS_AT", new("person", "1"), new("company", "acme"))
                           .Properties["role"]);
    }

    [Fact]
    public void MalformedLineThrows()
    {
        var ex = Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIsonl("nodes.person|id name"));
        Assert.Contains("malformed line", ex.Message);
    }

    [Fact]
    public void ShortIsonlRowIsPaddedWithNull()
    {
        // A short row is padded with null by the shared ISON parser rather
        // than rejected - every port behaves this way now that parsing goes
        // through it, so this is no longer an error.
        var padded = ISONGraph.FromIsonl("nodes.person|id name age|1 Alice");
        Assert.Equal(1, padded.NodeCount());
    }

    [Fact]
    public void MissingIdThrows()
    {
        var ex = Assert.ThrowsAny<GraphError>(
            () => ISONGraph.FromIsonl("nodes.person|name|Alice"));
        Assert.Contains("id", ex.Message);
    }

    [Fact]
    public void UnknownKindThrows()
    {
        var ex = Assert.ThrowsAny<GraphError>(
            () => ISONGraph.FromIsonl("things.person|id|1"));
        Assert.Contains("unknown block kind", ex.Message);
    }

    [Fact]
    public void HeaderWithoutDotThrows()
    {
        Assert.ThrowsAny<GraphError>(() => ISONGraph.FromIsonl("person|id|1"));
    }

    [Fact]
    public void BlankLinesSkipped()
    {
        const string isonl = "\nnodes.person|id|1\n\n\nnodes.person|id|2\n";
        Assert.Equal(2, ISONGraph.FromIsonl(isonl).NodeCount());
    }

    [Fact]
    public void QuotedPipeInsideValueSurvives()
    {
        var graph1 = new ISONGraph();
        graph1.AddNode("doc", "1", Props.Of(("tag", "a|b|c")));
        var graph2 = ISONGraph.FromIsonl(graph1.ToIsonl());
        Assert.Equal("a|b|c", graph2.GetNode("doc", "1").Properties["tag"]);
    }
}

public class SplitterTests
{
    [Fact]
    public void SplitFieldsBasic()
    {
        Assert.Equal(new List<string> { "a", "b", "c" }, ISONGraph.SplitFields("a b c"));
    }

    [Fact]
    public void SplitFieldsQuoted()
    {
        Assert.Equal(new List<string> { "a b", "c" }, ISONGraph.SplitFields("\"a b\" c"));
    }

    [Fact]
    public void SplitFieldsEmptyQuoted()
    {
        Assert.Equal(new List<string> { "", "x" }, ISONGraph.SplitFields("\"\" x"));
    }

    [Fact]
    public void SplitFieldsUnescapes()
    {
        Assert.Equal(new List<string> { "say \"hi\"", "l1\nl2", "a\\b" },
                     ISONGraph.SplitFields("\"say \\\"hi\\\"\" \"l1\\nl2\" \"a\\\\b\""));
    }

    [Fact]
    public void SplitFieldsMultipleSpaces()
    {
        Assert.Equal(new List<string> { "a", "b" }, ISONGraph.SplitFields("a   b"));
    }

    [Fact]
    public void SplitPipeAwareRespectsQuotes()
    {
        Assert.Equal(new List<string> { "a", "\"b|c\"", "d" },
                     ISONGraph.SplitPipeAware("a|\"b|c\"|d"));
    }
}

public class FileIoTests
{
    [Fact]
    public void SaveAndLoadIson()
    {
        var dir = Directory.CreateTempSubdirectory("isongraph-io").FullName;
        try
        {
            var graph = new ISONGraph("social");
            graph.AddNode("person", "1", Props.Of(("name", "Alice")));
            graph.AddNode("person", "2", Props.Of(("name", "Bob")));
            graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

            var path = System.IO.Path.Combine(dir, "social.ison");
            graph.Save(path);

            var loaded = ISONGraph.Load(path);
            Assert.Equal("social", loaded.Name); // name from file stem
            Assert.Equal(2, loaded.NodeCount());
            Assert.Equal(1, loaded.EdgeCount());
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void SaveAndLoadIsonlByExtension()
    {
        var dir = Directory.CreateTempSubdirectory("isongraph-io").FullName;
        try
        {
            var graph = new ISONGraph();
            graph.AddNode("person", "1", Props.Of(("name", "Alice")));

            var path = System.IO.Path.Combine(dir, "g.isonl");
            graph.Save(path);

            Assert.Contains("nodes.person|", File.ReadAllText(path));
            var loaded = ISONGraph.Load(path);
            Assert.Equal(1, loaded.NodeCount());
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }
}

// =============================================================================
// Canonical Serialization
//
// ToIson()/ToIsonl() must be byte-identical for the same logical graph
// regardless of insertion order (node type blocks, node rows, edge type
// blocks, and edge rows are all sorted, ordinal string comparison). The
// golden fixture below is shared verbatim across every ISONGraph language
// port's test suite (Python, JS, TS, Rust, C++, C#) as the cross-language
// byte-identity contract - if it changes here, it must change everywhere.
// =============================================================================

public class CanonicalSerializationTests
{
    private const string GoldenIson =
        "edges.KNOWS\n" +
        "since source target\n" +
        "\"2020\" :person:1 :person:2\n" +
        "\"2021\" :person:10 :person:1\n" +
        "\n" +
        "edges.WORKS_AT\n" +
        "role source target\n" +
        "\"Lead Engineer\" :person:1 :company:acme\n" +
        "\n" +
        "edges.WORKS_ON\n" +
        "hours source target\n" +
        "\"3\" :person:10 :project:p1\n" +
        "\"5\" :person:2 :project:p1\n" +
        "\n" +
        "nodes.company\n" +
        "id name\n" +
        "acme \"Acme Corp\"\n" +
        "\n" +
        "nodes.person\n" +
        "id age name\n" +
        "\"1\" \"30\" Alice\n" +
        "\"10\" \"22\" Jax\n" +
        "\"2\" \"25\" Bob\n" +
        "\n" +
        "nodes.project\n" +
        "id name tag\n" +
        "p1 Alpha a|b";

    private const string GoldenIsonl =
        "edges.KNOWS|since source target|\"2020\" :person:1 :person:2\n" +
        "edges.KNOWS|since source target|\"2021\" :person:10 :person:1\n" +
        "edges.WORKS_AT|role source target|\"Lead Engineer\" :person:1 :company:acme\n" +
        "edges.WORKS_ON|hours source target|\"3\" :person:10 :project:p1\n" +
        "edges.WORKS_ON|hours source target|\"5\" :person:2 :project:p1\n" +
        "nodes.company|id name|acme \"Acme Corp\"\n" +
        "nodes.person|id age name|\"1\" \"30\" Alice\n" +
        "nodes.person|id age name|\"10\" \"22\" Jax\n" +
        "nodes.person|id age name|\"2\" \"25\" Bob\n" +
        "nodes.project|id name tag|p1 Alpha \"a\\|b\"";

    private static ISONGraph BuildCanonicalFixture(int order)
    {
        var g = new ISONGraph("fixture");
        var nodes = new (string Type, string Id, Dictionary<string, string> Props)[]
        {
            ("company", "acme", Props.Of(("name", "Acme Corp"))),
            ("person", "1", Props.Of(("name", "Alice"), ("age", "30"))),
            ("person", "10", Props.Of(("name", "Jax"), ("age", "22"))),
            ("person", "2", Props.Of(("name", "Bob"), ("age", "25"))),
            ("project", "p1", Props.Of(("name", "Alpha"), ("tag", "a|b"))),
        };
        var edges = new (string Rel, NodeRef Source, NodeRef Target, Dictionary<string, string> Props)[]
        {
            ("KNOWS", new("person", "10"), new("person", "1"), Props.Of(("since", "2021"))),
            ("KNOWS", new("person", "1"), new("person", "2"), Props.Of(("since", "2020"))),
            ("WORKS_AT", new("person", "1"), new("company", "acme"), Props.Of(("role", "Lead Engineer"))),
            ("WORKS_ON", new("person", "2"), new("project", "p1"), Props.Of(("hours", "5"))),
            ("WORKS_ON", new("person", "10"), new("project", "p1"), Props.Of(("hours", "3"))),
        };
        var n = order == 0 ? nodes : Enumerable.Reverse(nodes).ToArray();
        var e = order == 0 ? edges : Enumerable.Reverse(edges).ToArray();
        foreach (var (t, i, props) in n)
            g.AddNode(t, i, props);
        foreach (var (rel, s, t, props) in e)
            g.AddEdge(rel, s, t, props);
        return g;
    }

    [Fact]
    public void ToIsonIndependentOfInsertionOrder()
    {
        Assert.Equal(BuildCanonicalFixture(0).ToIson(), BuildCanonicalFixture(1).ToIson());
    }

    [Fact]
    public void ToIsonlIndependentOfInsertionOrder()
    {
        Assert.Equal(BuildCanonicalFixture(0).ToIsonl(), BuildCanonicalFixture(1).ToIsonl());
    }

    [Fact]
    public void ToIsonMatchesGoldenFixture()
    {
        Assert.Equal(GoldenIson, BuildCanonicalFixture(0).ToIson());
        Assert.Equal(GoldenIson, BuildCanonicalFixture(1).ToIson());
    }

    [Fact]
    public void ToIsonlMatchesGoldenFixture()
    {
        Assert.Equal(GoldenIsonl, BuildCanonicalFixture(0).ToIsonl());
        Assert.Equal(GoldenIsonl, BuildCanonicalFixture(1).ToIsonl());
    }

    [Fact]
    public void OrdinalNotNumericSort()
    {
        // "1" < "10" < "2" ordinally.
        var ison = BuildCanonicalFixture(0).ToIson();
        var start = ison.IndexOf("nodes.person\n", StringComparison.Ordinal) + "nodes.person\n".Length;
        var end = ison.IndexOf("\n\n", start, StringComparison.Ordinal);
        var personBlock = ison[start..end];
        var lines = personBlock.Split('\n');
        var ids = lines.Skip(1).Select(l => l.Split(' ')[0].Trim('"')).ToArray();
        Assert.Equal(new[] { "1", "10", "2" }, ids);
    }

    [Fact]
    public void RoundtripPreservesCanonicalForm()
    {
        var g = BuildCanonicalFixture(0);
        var reloaded = ISONGraph.FromIson(g.ToIson());
        Assert.Equal(g.ToIson(), reloaded.ToIson());
    }
}
