// ISONGraph Visualization - deterministic layout and SVG/HTML rendering.
//
// Three-stage pipeline:
// 1. Graph data - an ISONGraph instance.
// 2. Layout     - ComputeLayout() runs a seeded, deterministic force
//    simulation and assigns every node an (x, y) coordinate.
// 3. Rendering  - RenderSvg() / RenderHtml() turn those coordinates into a
//    standalone SVG image or a self-contained interactive HTML page.
//
// The layout algorithm and PRNG mirror ison_graph.viz.compute_layout (Python)
// exactly: the same graph, size, and seed produce bit-identical geometry in
// both languages. The PRNG is a portable 32-bit LCG
// (state * 1664525 + 1013904223 mod 2^32).

using System.Globalization;
using System.Text;

namespace IsonGraph;

/// <summary>A layout position.</summary>
public readonly record struct Point(double X, double Y);

/// <summary>Deterministic layout and SVG/HTML rendering for ISONGraph.</summary>
public static class Viz
{
    // Categorical palette (validated: CVD-safe adjacent pairs, both modes).
    // Types get slots in sorted order; past 8 types fall back to OTHER.
    public static readonly IReadOnlyList<string> LightPalette = new[]
    {
        "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
        "#e87ba4", "#008300", "#4a3aa7", "#e34948",
    };

    public static readonly IReadOnlyList<string> DarkPalette = new[]
    {
        "#3987e5", "#d95926", "#199e70", "#c98500",
        "#d55181", "#008300", "#9085e9", "#e66767",
    };

    public const string OtherLight = "#7a7975";
    public const string OtherDark = "#8f8e89";

    private const string SurfaceLight = "#fcfcfb";
    private const string SurfaceDark = "#1a1a19";
    private const string InkPrimary = "#0b0b0b";
    private const string InkSecondary = "#52514e";
    private const string InkPrimaryDark = "#ffffff";
    private const string InkSecondaryDark = "#c3c2b7";
    private const string EdgeLight = "#d7d6d2";
    private const string EdgeDark = "#3a3936";

    // =========================================================================
    // Stage 2: Layout
    // =========================================================================

    private static int CompareRefs(NodeRef a, NodeRef b)
    {
        var c = string.CompareOrdinal(a.Type, b.Type);
        return c != 0 ? c : string.CompareOrdinal(a.Id, b.Id);
    }

    /// <summary>
    /// Compute a deterministic force-directed layout (Fruchterman-Reingold).
    ///
    /// Repulsion between every node pair, spring attraction along edges, and a
    /// linear cooling schedule. The seed fixes the initial positions, so the
    /// same graph, size, and seed always yield the same coordinates - across
    /// processes and across language ports: the PRNG is a portable 32-bit LCG
    /// (state * 1664525 + 1013904223 mod 2^32).
    ///
    /// When <paramref name="radii"/> maps node refs to visual radii, a
    /// deterministic collision pass runs after the simulation, pushing every
    /// pair apart until their centers are at least (rA + rB) * spacing apart.
    /// Omitting radii leaves the output byte-identical to the plain layout.
    /// </summary>
    public static Dictionary<NodeRef, Point> ComputeLayout(
        ISONGraph graph,
        int width = 900,
        int height = 600,
        int iterations = 170,
        int seed = 42,
        int margin = 60,
        IReadOnlyDictionary<NodeRef, double>? radii = null,
        double spacing = 1.0)
    {
        var refs = graph.Nodes().Select(node => node.Ref).ToList();
        refs.Sort(CompareRefs);

        var n = refs.Count;
        var result = new Dictionary<NodeRef, Point>();
        if (n == 0)
            return result;
        if (n == 1)
        {
            result[refs[0]] = new Point(width / 2.0, height / 2.0);
            return result;
        }

        var state = unchecked((uint)seed);
        double Rand()
        {
            unchecked
            {
                state = state * 1664525u + 1013904223u;
            }
            return state / 4294967296.0;
        }

        var innerW = Math.Max(1.0, width - 2.0 * margin);
        var innerH = Math.Max(1.0, height - 2.0 * margin);

        var posX = new double[n];
        var posY = new double[n];
        var indexOf = new Dictionary<NodeRef, int>();
        for (var i = 0; i < n; i++)
        {
            indexOf[refs[i]] = i;
            posX[i] = margin + Rand() * innerW;
            posY[i] = margin + Rand() * innerH;
        }

        // Springs: unordered node pairs connected by at least one edge.
        // Deduped via a set but iterated in sorted order - float accumulation
        // order must be deterministic for cross-language parity.
        var springSet = new HashSet<(int A, int B)>();
        foreach (var edge in graph.Edges())
        {
            if (edge.Source == edge.Target)
                continue;
            if (!indexOf.TryGetValue(edge.Source, out var ia) ||
                !indexOf.TryGetValue(edge.Target, out var ib))
            {
                continue;
            }
            springSet.Add(ia <= ib ? (ia, ib) : (ib, ia));
        }
        var springs = springSet.ToList();
        springs.Sort((p, q) => p.A != q.A ? p.A.CompareTo(q.A) : p.B.CompareTo(q.B));

        var area = innerW * innerH;
        var k = Math.Sqrt(area / n);
        var temp = Math.Min(innerW, innerH) / 10.0;
        var cool = temp / (iterations + 1);

        var dispX = new double[n];
        var dispY = new double[n];

        for (var iter = 0; iter < iterations; iter++)
        {
            for (var i = 0; i < n; i++)
            {
                dispX[i] = 0.0;
                dispY[i] = 0.0;
            }

            // Repulsion: every pair pushes apart with k^2 / d.
            for (var i = 0; i < n; i++)
            {
                var xi = posX[i];
                var yi = posY[i];
                for (var j = i + 1; j < n; j++)
                {
                    var dx = xi - posX[j];
                    var dy = yi - posY[j];
                    var dist = Math.Sqrt(dx * dx + dy * dy);
                    if (dist == 0.0)
                        dist = 0.01;
                    var force = (k * k) / dist;
                    var fx = (dx / dist) * force;
                    var fy = (dy / dist) * force;
                    dispX[i] += fx;
                    dispY[i] += fy;
                    dispX[j] -= fx;
                    dispY[j] -= fy;
                }
            }

            // Attraction: connected pairs pull together with d^2 / k.
            foreach (var (a, b) in springs)
            {
                var dx = posX[a] - posX[b];
                var dy = posY[a] - posY[b];
                var dist = Math.Sqrt(dx * dx + dy * dy);
                if (dist == 0.0)
                    dist = 0.01;
                var force = (dist * dist) / k;
                var fx = (dx / dist) * force;
                var fy = (dy / dist) * force;
                dispX[a] -= fx;
                dispY[a] -= fy;
                dispX[b] += fx;
                dispY[b] += fy;
            }

            // Move, capped by temperature; clamp into the frame.
            for (var i = 0; i < n; i++)
            {
                var dx = dispX[i];
                var dy = dispY[i];
                var dist = Math.Sqrt(dx * dx + dy * dy);
                if (dist == 0.0)
                    dist = 0.01;
                var step = Math.Min(dist, temp);
                var x = posX[i] + (dx / dist) * step;
                var y = posY[i] + (dy / dist) * step;
                posX[i] = Math.Min(width - margin, Math.Max(margin, x));
                posY[i] = Math.Min(height - margin, Math.Max(margin, y));
            }

            temp = Math.Max(0.01, temp - cool);
        }

        // Deterministic collision pass: separate every pair to at least
        // (rA + rB) * spacing. Sorted pair order keeps this reproducible
        // across processes and language ports.
        if (radii is { Count: > 0 })
        {
            var rad = new double[n];
            for (var i = 0; i < n; i++)
                rad[i] = radii.TryGetValue(refs[i], out var r) ? r : 0.0;

            for (var sweep = 0; sweep < 50; sweep++)
            {
                var moved = false;
                for (var i = 0; i < n; i++)
                {
                    for (var j = i + 1; j < n; j++)
                    {
                        var minD = (rad[i] + rad[j]) * spacing;
                        if (minD <= 0.0)
                            continue;
                        var dx = posX[j] - posX[i];
                        var dy = posY[j] - posY[i];
                        var dist = Math.Sqrt(dx * dx + dy * dy);
                        if (dist >= minD)
                            continue;
                        double ux, uy;
                        if (dist < 1e-9)
                        {
                            ux = 1.0;
                            uy = 0.0;
                        }
                        else
                        {
                            ux = dx / dist;
                            uy = dy / dist;
                        }
                        var push = (minD - dist) / 2.0;
                        posX[i] = Math.Min(width - margin, Math.Max(margin, posX[i] - ux * push));
                        posY[i] = Math.Min(height - margin, Math.Max(margin, posY[i] - uy * push));
                        posX[j] = Math.Min(width - margin, Math.Max(margin, posX[j] + ux * push));
                        posY[j] = Math.Min(height - margin, Math.Max(margin, posY[j] + uy * push));
                        moved = true;
                    }
                }
                if (!moved)
                    break;
            }
        }

        for (var i = 0; i < n; i++)
            result[refs[i]] = new Point(posX[i], posY[i]);
        return result;
    }

    // =========================================================================
    // Stage 3: Rendering
    // =========================================================================

    private static string F(double value) => value.ToString("F1", CultureInfo.InvariantCulture);

    private static string EscapeXml(string s) =>
        s.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");

    private static string QuoteAttr(string s) =>
        "\"" + EscapeXml(s).Replace("\"", "&quot;") + "\"";

    private static string JsonEscape(string s)
    {
        var sb = new StringBuilder();
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < ' ')
                        sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    else
                        sb.Append(c);
                    break;
            }
        }
        return sb.ToString();
    }

    private static string PropsJson(IReadOnlyDictionary<string, object?> properties)
    {
        var sb = new StringBuilder("{");
        var first = true;
        foreach (var (key, value) in properties)
        {
            if (!first)
                sb.Append(", ");
            first = false;
            sb.Append('"').Append(JsonEscape(key)).Append("\": \"")
              .Append(JsonEscape(PropertyValue.ValueText(value))).Append('"');
        }
        sb.Append('}');
        return sb.ToString();
    }

    /// <summary>Assign each node type a palette slot in sorted order (fixed, never cycled).</summary>
    private static Dictionary<string, int> TypeSlots(ISONGraph graph)
    {
        var types = graph.NodeTypes();
        types.Sort(StringComparer.Ordinal);
        var slots = new Dictionary<string, int>();
        for (var i = 0; i < types.Count; i++)
            slots[types[i]] = i;
        return slots;
    }

    private static string FillFor(int slot, IReadOnlyList<string> palette, string other) =>
        slot < palette.Count ? palette[slot] : other;

    private static double Radius(int degree, int dmin, int dmax)
    {
        if (dmax <= dmin)
            return 9.0;
        return 6.0 + 10.0 * (degree - dmin) / (dmax - dmin);
    }

    private static string NodeLabel(Node node, string? labelProperty)
    {
        if (labelProperty is not null &&
            node.Properties.TryGetValue(labelProperty, out var custom))
        {
            return PropertyValue.ValueText(custom);
        }
        if (node.Properties.TryGetValue("name", out var name))
            return PropertyValue.ValueText(name);
        return node.Id;
    }

    /// <summary>Edges to draw: for undirected graphs, skip the auto-added reverse twin.</summary>
    private static IEnumerable<Edge> VisibleEdges(ISONGraph graph)
    {
        var seen = new HashSet<(string, NodeRef, NodeRef)>();
        foreach (var edge in graph.Edges())
        {
            if (!graph.Directed)
            {
                var key = CompareRefs(edge.Source, edge.Target) <= 0
                    ? (edge.RelType, edge.Source, edge.Target)
                    : (edge.RelType, edge.Target, edge.Source);
                if (!seen.Add(key))
                    continue;
            }
            yield return edge;
        }
    }

    /// <summary>
    /// Build the SVG body. With classed=true marks carry CSS classes and no
    /// inline colors (for themable HTML); otherwise light-mode colors are
    /// inlined so the file stands alone.
    /// </summary>
    private static string BuildSvg(
        ISONGraph graph,
        IReadOnlyDictionary<NodeRef, Point> layout,
        int width,
        int height,
        string? title,
        string? labelProperty,
        bool edgeLabels,
        bool classed)
    {
        var slots = TypeSlots(graph);
        var degrees = new Dictionary<NodeRef, int>();
        foreach (var node in graph.Nodes())
            degrees[node.Ref] = graph.Degree(node.Ref);
        var dmin = degrees.Count > 0 ? degrees.Values.Min() : 0;
        var dmax = degrees.Count > 0 ? degrees.Values.Max() : 0;
        var directed = graph.Directed;

        var parts = new List<string>
        {
            $"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" " +
            $"viewBox=\"0 0 {width} {height}\" role=\"img\" " +
            $"aria-label={QuoteAttr(title ?? graph.Name)}>",
        };

        parts.Add(classed
            ? $"<rect class=\"surface\" width=\"{width}\" height=\"{height}\"/>"
            : $"<rect width=\"{width}\" height=\"{height}\" fill=\"{SurfaceLight}\"/>");

        if (directed)
        {
            var arrowFill = classed ? "" : $" fill=\"{EdgeLight}\"";
            parts.Add(
                "<defs><marker id=\"arrow\" viewBox=\"0 0 10 10\" refX=\"10\" refY=\"5\" " +
                "markerWidth=\"7\" markerHeight=\"7\" orient=\"auto-start-reverse\">" +
                $"<path d=\"M 0 0 L 10 5 L 0 10 z\" class=\"edge-arrow\"{arrowFill}/></marker></defs>");
        }

        // Edges under nodes.
        parts.Add("<g class=\"edges\">");
        foreach (var edge in VisibleEdges(graph))
        {
            if (!layout.TryGetValue(edge.Source, out var ps) ||
                !layout.TryGetValue(edge.Target, out var pt))
            {
                continue;
            }
            var x1 = ps.X;
            var y1 = ps.Y;
            var x2 = pt.X;
            var y2 = pt.Y;
            // Shorten toward the target so arrowheads sit on the node rim.
            if (directed)
            {
                var r2 = Radius(degrees.GetValueOrDefault(edge.Target), dmin, dmax) + 3.0;
                var ddx = x2 - x1;
                var ddy = y2 - y1;
                var dist = Math.Sqrt(ddx * ddx + ddy * ddy);
                if (dist == 0.0)
                    dist = 1.0;
                x2 -= (x2 - x1) / dist * r2;
                y2 -= (y2 - y1) / dist * r2;
            }
            var stroke = classed ? "" : $" stroke=\"{EdgeLight}\"";
            var marker = directed ? " marker-end=\"url(#arrow)\"" : "";
            parts.Add(
                $"<line class=\"edge\" x1=\"{F(x1)}\" y1=\"{F(y1)}\" x2=\"{F(x2)}\" y2=\"{F(y2)}\"" +
                $"{stroke} stroke-width=\"2\"{marker}/>");
            if (edgeLabels)
            {
                var mx = (x1 + x2) / 2.0;
                var my = (y1 + y2) / 2.0;
                var fill = classed ? "" : $" fill=\"{InkSecondary}\"";
                parts.Add(
                    $"<text class=\"edge-label\" x=\"{F(mx)}\" y=\"{F(my - 4)}\" " +
                    $"font-size=\"10\" text-anchor=\"middle\"{fill}>{EscapeXml(edge.RelType)}</text>");
            }
        }
        parts.Add("</g>");

        // Nodes with a 2px surface ring, labels in ink (never the series color).
        parts.Add("<g class=\"nodes\">");
        foreach (var node in graph.Nodes())
        {
            if (!layout.TryGetValue(node.Ref, out var p))
                continue;
            var x = p.X;
            var y = p.Y;
            var slot = slots.GetValueOrDefault(node.Type);
            var r = Radius(degrees.GetValueOrDefault(node.Ref), dmin, dmax);
            var label = NodeLabel(node, labelProperty);
            var data = "";
            string paint;
            if (classed)
            {
                var props = PropsJson(node.Properties);
                data = $" data-ref={QuoteAttr($"{node.Type}:{node.Id}")} data-props={QuoteAttr(props)}";
                paint = $" class=\"node t{slot}\"";
            }
            else
            {
                var fill = FillFor(slot, LightPalette, OtherLight);
                paint = $" class=\"node\" fill=\"{fill}\" stroke=\"{SurfaceLight}\"";
            }
            parts.Add(
                $"<circle{paint} cx=\"{F(x)}\" cy=\"{F(y)}\" r=\"{F(r)}\" stroke-width=\"2\"{data}/>");
            var labelFill = classed ? "" : $" fill=\"{InkSecondary}\"";
            parts.Add(
                $"<text class=\"node-label\" x=\"{F(x)}\" y=\"{F(y + r + 13)}\" font-size=\"12\" " +
                $"font-family=\"system-ui, sans-serif\" text-anchor=\"middle\"{labelFill}>" +
                $"{EscapeXml(label)}</text>");
        }
        parts.Add("</g>");

        // Legend: one chip per type, primary ink text.
        parts.Add("<g class=\"legend\">");
        var lx = 16.0;
        var ly = 24.0;
        var sortedTypes = slots.Keys.ToList();
        sortedTypes.Sort(StringComparer.Ordinal);
        foreach (var t in sortedTypes)
        {
            var slot = slots[t];
            var chip = classed
                ? $"<circle class=\"t{slot}\" cx=\"{F(lx)}\" cy=\"{F(ly - 4)}\" r=\"6\"/>"
                : $"<circle cx=\"{F(lx)}\" cy=\"{F(ly - 4)}\" r=\"6\" " +
                  $"fill=\"{FillFor(slot, LightPalette, OtherLight)}\"/>";
            var fill = classed ? "" : $" fill=\"{InkPrimary}\"";
            parts.Add(chip);
            parts.Add(
                $"<text class=\"legend-label\" x=\"{F(lx + 12)}\" y=\"{F(ly)}\" font-size=\"12\" " +
                $"font-family=\"system-ui, sans-serif\"{fill}>{EscapeXml(t)}</text>");
            lx += 24 + 7.2 * t.Length;
        }
        parts.Add("</g>");

        if (title is not null)
        {
            var fill = classed ? "" : $" fill=\"{InkPrimary}\"";
            parts.Add(
                $"<text class=\"title\" x=\"{F(width / 2.0)}\" y=\"{F(height - 14.0)}\" font-size=\"13\" " +
                $"font-family=\"system-ui, sans-serif\" text-anchor=\"middle\"{fill}>{EscapeXml(title)}</text>");
        }

        parts.Add("</svg>");
        return string.Join("\n", parts);
    }

    /// <summary>
    /// Render the graph to a standalone SVG string (light theme, inline
    /// colors). If <paramref name="layout"/> is omitted it is computed with
    /// <see cref="ComputeLayout"/> using width, height, and seed.
    /// </summary>
    public static string RenderSvg(
        ISONGraph graph,
        IReadOnlyDictionary<NodeRef, Point>? layout = null,
        int width = 900,
        int height = 600,
        string? title = null,
        string? labelProperty = null,
        bool edgeLabels = false,
        int seed = 42)
    {
        layout ??= ComputeLayout(graph, width: width, height: height, seed: seed);
        return BuildSvg(graph, layout, width, height, title, labelProperty, edgeLabels,
                        classed: false);
    }

    private static string ThemeCss(IReadOnlyList<string> palette, string other, string surface,
                                   string ink1, string ink2, string edge)
    {
        var rules = new List<string>();
        rules.Add(".surface{fill:" + surface + "}");
        rules.Add(".edge{stroke:" + edge + "} .edge-arrow{fill:" + edge + "}");
        rules.Add(".node{stroke:" + surface + "}");
        rules.Add(".node-label,.edge-label{fill:" + ink2 + "}");
        rules.Add(".legend-label,.title{fill:" + ink1 + "}");
        for (var i = 0; i < palette.Count; i++)
            rules.Add(".t" + i + "{fill:" + palette[i] + "}");
        rules.Add(".t8,.t9,.t10,.t11,.t12,.t13,.t14,.t15{fill:" + other + "}");
        return string.Join("\n", rules);
    }

    /// <summary>
    /// Render the graph to a self-contained interactive HTML page: light and
    /// dark themes (follows the OS setting), hover tooltips with node
    /// properties, and wheel-zoom / drag-pan. No external resources.
    /// </summary>
    public static string RenderHtml(
        ISONGraph graph,
        IReadOnlyDictionary<NodeRef, Point>? layout = null,
        int width = 900,
        int height = 600,
        string? title = null,
        string? labelProperty = null,
        bool edgeLabels = false,
        int seed = 42)
    {
        layout ??= ComputeLayout(graph, width: width, height: height, seed: seed);
        var name = title ?? graph.Name;
        var svg = BuildSvg(graph, layout, width, height, title, labelProperty, edgeLabels,
                           classed: true);

        var light = ThemeCss(LightPalette, OtherLight, SurfaceLight,
                             InkPrimary, InkSecondary, EdgeLight);
        var dark = ThemeCss(DarkPalette, OtherDark, SurfaceDark,
                            InkPrimaryDark, InkSecondaryDark, EdgeDark);

        return $$"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{EscapeXml(name)}}</title>
<style>
html,body{margin:0;height:100%;background:{{SurfaceLight}}}
body{display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif}
#wrap{position:relative;max-width:100%;overflow:hidden}
svg{display:block;max-width:100%;height:auto;cursor:grab}
svg:active{cursor:grabbing}
.node{stroke-width:2px;cursor:pointer}
#tip{position:absolute;display:none;pointer-events:none;background:{{InkPrimary}};color:{{SurfaceLight}};
padding:6px 10px;border-radius:6px;font-size:12px;max-width:280px;line-height:1.5;z-index:2}
{{light}}
@media (prefers-color-scheme: dark){
html,body{background:{{SurfaceDark}}}
#tip{background:{{InkPrimaryDark}};color:{{SurfaceDark}}}
{{dark}}
}
</style>
</head>
<body>
<div id="wrap">
{{svg}}
<div id="tip"></div>
</div>
<script>
(function () {
  var svg = document.querySelector('svg');
  var tip = document.getElementById('tip');
  var vb = svg.viewBox.baseVal;
  var view = {x: vb.x, y: vb.y, w: vb.width, h: vb.height};

  function apply() {
    svg.setAttribute('viewBox', view.x + ' ' + view.y + ' ' + view.w + ' ' + view.h);
  }

  svg.addEventListener('wheel', function (e) {
    e.preventDefault();
    var factor = e.deltaY < 0 ? 0.9 : 1.1;
    var rect = svg.getBoundingClientRect();
    var mx = view.x + (e.clientX - rect.left) / rect.width * view.w;
    var my = view.y + (e.clientY - rect.top) / rect.height * view.h;
    view.w *= factor; view.h *= factor;
    view.x = mx - (mx - view.x) * factor;
    view.y = my - (my - view.y) * factor;
    apply();
  }, {passive: false});

  var drag = null;
  svg.addEventListener('pointerdown', function (e) {
    drag = {x: e.clientX, y: e.clientY};
    svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', function (e) {
    if (!drag) return;
    var rect = svg.getBoundingClientRect();
    view.x -= (e.clientX - drag.x) / rect.width * view.w;
    view.y -= (e.clientY - drag.y) / rect.height * view.h;
    drag = {x: e.clientX, y: e.clientY};
    apply();
  });
  svg.addEventListener('pointerup', function () { drag = null; });

  document.querySelectorAll('.node').forEach(function (c) {
    c.addEventListener('mouseenter', function (e) {
      var props = JSON.parse(c.getAttribute('data-props') || '{}');
      var lines = ['<strong>' + c.getAttribute('data-ref') + '</strong>'];
      Object.keys(props).forEach(function (k) {
        lines.push(k + ': ' + String(props[k]));
      });
      tip.innerHTML = lines.join('<br>');
      tip.style.display = 'block';
    });
    c.addEventListener('mousemove', function (e) {
      var wrap = document.getElementById('wrap').getBoundingClientRect();
      tip.style.left = (e.clientX - wrap.left + 14) + 'px';
      tip.style.top = (e.clientY - wrap.top + 14) + 'px';
    });
    c.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
  });
})();
</script>
</body>
</html>

""";
    }

    /// <summary>
    /// Render to a file; the format is chosen by extension (.svg or .html/.htm).
    /// </summary>
    public static void Save(
        ISONGraph graph,
        string path,
        IReadOnlyDictionary<NodeRef, Point>? layout = null,
        int width = 900,
        int height = 600,
        string? title = null,
        string? labelProperty = null,
        bool edgeLabels = false,
        int seed = 42)
    {
        var lower = path.ToLowerInvariant();
        string content;
        if (lower.EndsWith(".html", StringComparison.Ordinal) ||
            lower.EndsWith(".htm", StringComparison.Ordinal))
        {
            content = RenderHtml(graph, layout, width, height, title, labelProperty,
                                 edgeLabels, seed);
        }
        else if (lower.EndsWith(".svg", StringComparison.Ordinal))
        {
            content = RenderSvg(graph, layout, width, height, title, labelProperty,
                                edgeLabels, seed);
        }
        else
        {
            throw new ArgumentException($"Unsupported output extension: {path} (use .svg or .html)");
        }
        File.WriteAllText(path, content, new UTF8Encoding(false));
    }
}
