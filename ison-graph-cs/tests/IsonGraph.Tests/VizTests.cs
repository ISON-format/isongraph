// Tests for Viz - layout determinism, Python parity, SVG/HTML rendering.

using System.Xml.Linq;
using Xunit;

namespace IsonGraph.Tests;

public static class VizFixtures
{
    public static ISONGraph SocialGraph()
    {
        var g = new ISONGraph("social");
        g.AddNode("person", "1", new Dictionary<string, object?> { ["name"] = "Alice", ["age"] = "30" });
        g.AddNode("person", "2", new Dictionary<string, object?> { ["name"] = "Bob", ["age"] = "25" });
        g.AddNode("person", "3", new Dictionary<string, object?> { ["name"] = "Carol", ["age"] = "28" });
        g.AddNode("company", "100", new Dictionary<string, object?> { ["name"] = "TechCorp" });
        g.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                  new Dictionary<string, object?> { ["since"] = "2020" });
        g.AddEdge("KNOWS", new("person", "2"), new("person", "3"),
                  new Dictionary<string, object?> { ["since"] = "2021" });
        g.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"),
                  new Dictionary<string, object?> { ["role"] = "Engineer" });
        return g;
    }

    public static ISONGraph ParityGraph()
    {
        var g = new ISONGraph("parity");
        g.AddNode("person", "alice", new Dictionary<string, object?> { ["name"] = "Alice", ["age"] = "30" });
        g.AddNode("person", "bob", new Dictionary<string, object?> { ["name"] = "Bob", ["age"] = "25" });
        g.AddNode("person", "carol", new Dictionary<string, object?> { ["name"] = "Carol", ["age"] = "35" });
        g.AddNode("company", "acme", new Dictionary<string, object?> { ["name"] = "Acme" });
        g.AddNode("project", "p1", new Dictionary<string, object?> { ["name"] = "Alpha" });
        g.AddEdge("KNOWS", new("person", "alice"), new("person", "bob"));
        g.AddEdge("KNOWS", new("person", "bob"), new("person", "carol"));
        g.AddEdge("WORKS_AT", new("person", "alice"), new("company", "acme"));
        g.AddEdge("WORKS_ON", new("person", "carol"), new("project", "p1"));
        return g;
    }

    public static ISONGraph HubGraph()
    {
        var g = new ISONGraph("collide");
        g.AddNode("hub", "a");
        g.AddNode("hub", "b");
        for (var i = 1; i <= 4; i++)
        {
            g.AddNode("leaf", i.ToString());
            g.AddEdge("LINK", new("hub", "a"), new("leaf", i.ToString()));
            g.AddEdge("LINK", new("hub", "b"), new("leaf", i.ToString()));
        }
        return g;
    }
}

public class ComputeLayoutTests
{
    [Fact]
    public void DeterministicForSameSeed()
    {
        var g = VizFixtures.SocialGraph();
        var a = Viz.ComputeLayout(g, seed: 42);
        var b = Viz.ComputeLayout(g, seed: 42);
        Assert.Equal(a, b);
    }

    [Fact]
    public void DiffersAcrossSeeds()
    {
        var g = VizFixtures.SocialGraph();
        var a = Viz.ComputeLayout(g, seed: 1);
        var b = Viz.ComputeLayout(g, seed: 2);
        Assert.NotEqual(a, b);
    }

    [Fact]
    public void PositionsWithinBounds()
    {
        var layout = Viz.ComputeLayout(VizFixtures.SocialGraph(), width: 900, height: 600, margin: 60);
        foreach (var p in layout.Values)
        {
            Assert.InRange(p.X, 60.0, 840.0);
            Assert.InRange(p.Y, 60.0, 540.0);
        }
    }

    [Fact]
    public void AllNodesPlaced()
    {
        var g = VizFixtures.SocialGraph();
        var layout = Viz.ComputeLayout(g);
        var expected = g.Nodes().Select(n => n.Ref).ToHashSet();
        Assert.Equal(expected, layout.Keys.ToHashSet());
    }

    [Fact]
    public void EmptyGraph()
    {
        Assert.Empty(Viz.ComputeLayout(new ISONGraph("empty")));
    }

    [Fact]
    public void SingleNodeCentered()
    {
        var g = new ISONGraph("one");
        g.AddNode("thing", "1");
        var layout = Viz.ComputeLayout(g, width: 900, height: 600);
        Assert.Equal(new Point(450.0, 300.0), layout[new NodeRef("thing", "1")]);
    }

    [Fact]
    public void ConnectedNodesCloserThanAverage()
    {
        var g = new ISONGraph("clusters");
        for (var i = 1; i <= 6; i++)
            g.AddNode("n", i.ToString());
        g.AddEdge("LINK", new("n", "1"), new("n", "2"));
        var layout = Viz.ComputeLayout(g, seed: 7);

        double D(string a, string b)
        {
            var pa = layout[new NodeRef("n", a)];
            var pb = layout[new NodeRef("n", b)];
            return Math.Sqrt((pa.X - pb.X) * (pa.X - pb.X) + (pa.Y - pb.Y) * (pa.Y - pb.Y));
        }

        var total = 0.0;
        var count = 0;
        for (var a = 1; a <= 6; a++)
        {
            for (var b = a + 1; b <= 6; b++)
            {
                total += D(a.ToString(), b.ToString());
                count++;
            }
        }
        Assert.True(D("1", "2") < total / count);
    }

    [Fact]
    public void MatchesPythonImplementationBitForBit()
    {
        // Exact coordinates produced by Python ison_graph.viz.compute_layout
        // for the identical graph with default settings (900x600, 170
        // iterations, seed 42). Bit-for-bit parity is the contract.
        var layout = Viz.ComputeLayout(VizFixtures.ParityGraph());
        Assert.Equal(5, layout.Count);

        var acme = layout[new NodeRef("company", "acme")];
        Assert.Equal(60.0, acme.X);
        Assert.Equal(60.0, acme.Y);

        var alice = layout[new NodeRef("person", "alice")];
        Assert.Equal(293.3277424315421, alice.X);
        Assert.Equal(60.0, alice.Y);

        var bob = layout[new NodeRef("person", "bob")];
        Assert.Equal(377.3280362355162, bob.X);
        Assert.Equal(354.58580004430877, bob.Y);

        var carol = layout[new NodeRef("person", "carol")];
        Assert.Equal(601.3804168633184, carol.X);
        Assert.Equal(540.0, carol.Y);

        var p1 = layout[new NodeRef("project", "p1")];
        Assert.Equal(840.0, p1.X);
        Assert.Equal(540.0, p1.Y);
    }
}

public class CollisionPassTests
{
    [Fact]
    public void RadiiEnforceMinimumSpacing()
    {
        var g = VizFixtures.HubGraph();
        var radii = g.Nodes().ToDictionary(n => n.Ref, _ => 40.0);
        var layout = Viz.ComputeLayout(g, radii: radii, spacing: 2.6);
        var entries = layout.ToList();
        for (var i = 0; i < entries.Count; i++)
        {
            for (var j = i + 1; j < entries.Count; j++)
            {
                var (ka, pa) = entries[i];
                var (kb, pb) = entries[j];
                var d = Math.Sqrt((pa.X - pb.X) * (pa.X - pb.X) + (pa.Y - pb.Y) * (pa.Y - pb.Y));
                Assert.True(d >= (radii[ka] + radii[kb]) * 2.6 - 1e-6,
                            $"{ka} and {kb} are only {d} apart");
            }
        }
    }

    [Fact]
    public void NoRadiiOutputUnchanged()
    {
        var g = VizFixtures.HubGraph();
        Assert.Equal(Viz.ComputeLayout(g), Viz.ComputeLayout(g, radii: null));
    }

    [Fact]
    public void EmptyRadiiOutputUnchanged()
    {
        var g = VizFixtures.HubGraph();
        Assert.Equal(Viz.ComputeLayout(g),
                     Viz.ComputeLayout(g, radii: new Dictionary<NodeRef, double>()));
    }

    [Fact]
    public void CollisionIsDeterministic()
    {
        var g = VizFixtures.HubGraph();
        var radii = g.Nodes().ToDictionary(n => n.Ref, _ => 40.0);
        var a = Viz.ComputeLayout(g, radii: radii, spacing: 2.6);
        var b = Viz.ComputeLayout(g, radii: radii, spacing: 2.6);
        Assert.Equal(a, b);
    }

    [Fact]
    public void CoincidentNodesGetSeparated()
    {
        var g = new ISONGraph("pair");
        g.AddNode("n", "1");
        g.AddNode("n", "2");
        var radii = new Dictionary<NodeRef, double>
        {
            [new NodeRef("n", "1")] = 500.0,
            [new NodeRef("n", "2")] = 500.0,
        };
        var layout = Viz.ComputeLayout(g, radii: radii, spacing: 1.0);
        var pa = layout[new NodeRef("n", "1")];
        var pb = layout[new NodeRef("n", "2")];
        var d = Math.Sqrt((pa.X - pb.X) * (pa.X - pb.X) + (pa.Y - pb.Y) * (pa.Y - pb.Y));
        Assert.True(d > 0);
    }

    [Fact]
    public void MatchesPythonCollisionOutputBitForBit()
    {
        var g = VizFixtures.ParityGraph();
        var radii = g.Nodes().ToDictionary(n => n.Ref, _ => 48.0);
        var layout = Viz.ComputeLayout(g, radii: radii, spacing: 2.6);

        // Exact output of Python compute_layout(radii={...48}, spacing=2.6).
        var acme = layout[new NodeRef("company", "acme")];
        Assert.Equal(60.0, acme.X);
        Assert.Equal(60.0, acme.Y);

        var alice = layout[new NodeRef("person", "alice")];
        Assert.Equal(309.6, alice.X);
        Assert.Equal(60.0, alice.Y);

        var bob = layout[new NodeRef("person", "bob")];
        Assert.Equal(377.3280362355162, bob.X);
        Assert.Equal(354.58580004430877, bob.Y);

        var carol = layout[new NodeRef("person", "carol")];
        Assert.Equal(590.4000000000001, carol.X);
        Assert.Equal(540.0, carol.Y);

        var p1 = layout[new NodeRef("project", "p1")];
        Assert.Equal(840.0, p1.X);
        Assert.Equal(540.0, p1.Y);
    }
}

public class RenderSvgTests
{
    private static readonly XNamespace Svg = "http://www.w3.org/2000/svg";

    [Fact]
    public void WellFormedAndComplete()
    {
        var svg = Viz.RenderSvg(VizFixtures.SocialGraph());
        var root = XDocument.Parse(svg).Root!;
        var nodesGroup = root.Elements(Svg + "g")
            .First(g => (string?)g.Attribute("class") == "nodes");
        var circles = nodesGroup.Elements(Svg + "circle").ToList();
        var lines = root.Descendants(Svg + "line").ToList();
        Assert.Equal(4, circles.Count);
        Assert.Equal(3, lines.Count);
    }

    [Fact]
    public void LabelsAndLegend()
    {
        var svg = Viz.RenderSvg(VizFixtures.SocialGraph());
        Assert.Contains("Alice", svg);
        Assert.Contains("Bob", svg);
        Assert.Contains("Carol", svg);
        Assert.Contains("TechCorp", svg);
        Assert.Contains("person", svg);
        Assert.Contains("company", svg);
    }

    [Fact]
    public void TypesGetFixedSortedSlots()
    {
        // Sorted types: company -> slot 0, person -> slot 1.
        var svg = Viz.RenderSvg(VizFixtures.SocialGraph());
        Assert.Contains(Viz.LightPalette[0], svg);
        Assert.Contains(Viz.LightPalette[1], svg);
    }

    [Fact]
    public void MoreThanEightTypesFoldToOther()
    {
        var g = new ISONGraph("many");
        for (var i = 0; i < 10; i++)
        {
            g.AddNode($"type{i:D2}", "1",
                      new Dictionary<string, object?> { ["name"] = $"n{i}" });
        }
        Assert.Contains(Viz.OtherLight, Viz.RenderSvg(g));
    }

    [Fact]
    public void UndirectedDrawsEachEdgeOnceNoArrows()
    {
        var g = new ISONGraph("u", directed: false);
        g.AddNode("n", "1");
        g.AddNode("n", "2");
        g.AddEdge("LINK", new("n", "1"), new("n", "2"));
        var svg = Viz.RenderSvg(g);
        var root = XDocument.Parse(svg).Root!;
        Assert.Single(root.Descendants(Svg + "line"));
        Assert.DoesNotContain("marker-end", svg);
    }

    [Fact]
    public void DirectedHasArrowMarker()
    {
        Assert.Contains("marker-end=\"url(#arrow)\"", Viz.RenderSvg(VizFixtures.SocialGraph()));
    }

    [Fact]
    public void EdgeLabelsAndTitle()
    {
        var svg = Viz.RenderSvg(VizFixtures.SocialGraph(), edgeLabels: true, title: "My Graph");
        Assert.Contains("KNOWS", svg);
        Assert.Contains("My Graph", svg);
    }

    [Fact]
    public void LabelPropertyOverridesName()
    {
        var g = new ISONGraph("labels");
        g.AddNode("person", "1",
                  new Dictionary<string, object?> { ["name"] = "Alice", ["nick"] = "Al" });
        var svg = Viz.RenderSvg(g, labelProperty: "nick");
        Assert.Contains(">Al</text>", svg);
    }

    [Fact]
    public void LabelFallsBackToIdWithoutName()
    {
        var g = new ISONGraph("labels");
        g.AddNode("person", "id42");
        Assert.Contains("id42", Viz.RenderSvg(g));
    }

    [Fact]
    public void EscapesMarkupInValues()
    {
        var g = new ISONGraph("x");
        g.AddNode("a<b", "1",
                  new Dictionary<string, object?> { ["name"] = "Bad <script> & \"quotes\"" });
        var svg = Viz.RenderSvg(g);
        Assert.DoesNotContain("<script>", svg);
        XDocument.Parse(svg); // must stay well-formed
    }

    [Fact]
    public void EmptyGraphRenders()
    {
        var svg = Viz.RenderSvg(new ISONGraph("empty"));
        Assert.Contains("</svg>", svg);
        XDocument.Parse(svg);
    }

    [Fact]
    public void DegreeScaledRadii()
    {
        // Degrees in the social graph: person 1 and 2 -> 2, person 3 and
        // company -> 1, so dmin=1, dmax=2 and r = 6 + 10*(deg-dmin)/(dmax-dmin)
        // yields 6.0 for degree 1 and 16.0 for degree 2.
        var svg = Viz.RenderSvg(VizFixtures.SocialGraph());
        Assert.Contains("r=\"6.0\"", svg);
        Assert.Contains("r=\"16.0\"", svg);
    }
}

public class RenderHtmlTests
{
    [Fact]
    public void SelfContainedInteractive()
    {
        var html = Viz.RenderHtml(VizFixtures.SocialGraph());
        Assert.Contains("<script>", html);
        Assert.Contains("data-props", html);
        Assert.Contains("prefers-color-scheme: dark", html);
        Assert.DoesNotContain("http://", html.Replace("http://www.w3.org/2000/svg", ""));
        Assert.DoesNotContain("https://", html);
    }

    [Fact]
    public void LayoutSharedBetweenSvgAndHtml()
    {
        var g = VizFixtures.SocialGraph();
        var layout = Viz.ComputeLayout(g, seed: 9);
        var svg = Viz.RenderSvg(g, layout: layout);
        var html = Viz.RenderHtml(g, layout: layout);
        var p = layout[new NodeRef("person", "1")];
        var coord = $"cx=\"{p.X.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)}\" " +
                    $"cy=\"{p.Y.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)}\"";
        Assert.Contains(coord, svg);
        Assert.Contains(coord, html);
    }

    [Fact]
    public void HtmlStartsWithDoctype()
    {
        Assert.StartsWith("<!DOCTYPE html>", Viz.RenderHtml(VizFixtures.SocialGraph()));
    }

    [Fact]
    public void HtmlContainsThemePalettes()
    {
        var html = Viz.RenderHtml(VizFixtures.SocialGraph());
        Assert.Contains(Viz.LightPalette[0], html);
        Assert.Contains(Viz.DarkPalette[0], html);
        Assert.Contains(".t8,.t9,.t10,.t11,.t12,.t13,.t14,.t15", html);
    }
}

public class VizSaveTests
{
    [Fact]
    public void SaveSvgAndHtml()
    {
        var g = VizFixtures.SocialGraph();
        var dir = Directory.CreateTempSubdirectory("isongraph-viz").FullName;
        try
        {
            var svgPath = System.IO.Path.Combine(dir, "g.svg");
            var htmlPath = System.IO.Path.Combine(dir, "g.html");
            Viz.Save(g, svgPath);
            Viz.Save(g, htmlPath);
            Assert.StartsWith("<svg", File.ReadAllText(svgPath));
            Assert.StartsWith("<!DOCTYPE html>", File.ReadAllText(htmlPath));
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void SaveRejectsUnknownExtension()
    {
        var g = VizFixtures.SocialGraph();
        Assert.Throws<ArgumentException>(() => Viz.Save(g, "graph.png"));
    }
}
