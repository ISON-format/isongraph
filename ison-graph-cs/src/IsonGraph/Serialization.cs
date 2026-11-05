// ISONGraph serialization: ISON / ISONL formats.
//
// Self-contained, quote-aware graph-format parser (zero dependencies).
//
// Standardized quoting rule (shared by all ISON language ports): a value is
// wrapped in double quotes when it contains a space, '|', '"', a newline, or
// is the empty string. Embedded '"' is escaped as \", newline as \n, and
// backslash as \\; the loaders reverse this exactly so round-trips are
// lossless. Malformed input throws a descriptive GraphError - never a silent
// skip.

using System.Text;
using IsonParser;

namespace IsonGraph;

public sealed partial class ISONGraph
{
    // =========================================================================
    // Quoting helpers
    // =========================================================================

    /// <summary>
    /// Quote a value for ISON/ISONL output: double-quote when the value is
    /// empty or contains a space, '|', '"', or a newline; escape '"' as \",
    /// newline as \n, and backslash as \\.
    /// </summary>
    internal static string QuoteValue(string value)
    {
        var needsQuoting = value.Length == 0;
        foreach (var c in value)
        {
            if (c is ' ' or '|' or '"' or '\n')
            {
                needsQuoting = true;
                break;
            }
        }
        if (!needsQuoting)
            return value;

        var sb = new StringBuilder(value.Length + 2);
        sb.Append('"');
        foreach (var c in value)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\n': sb.Append("\\n"); break;
                case '\\': sb.Append("\\\\"); break;
                default: sb.Append(c); break;
            }
        }
        sb.Append('"');
        return sb.ToString();
    }

    /// <summary>
    /// Split a row on whitespace, respecting double quotes and unescaping
    /// \" \n \\ inside quoted sections. A bare "" yields an empty field.
    /// </summary>
    internal static List<string> SplitFields(string s)
    {
        var result = new List<string>();
        var current = new StringBuilder();
        var inQuotes = false;
        var hasToken = false; // true once a token started (so "" yields an empty field)

        for (var i = 0; i < s.Length; i++)
        {
            var c = s[i];
            if (inQuotes)
            {
                if (c == '\\' && i + 1 < s.Length)
                {
                    var next = s[i + 1];
                    switch (next)
                    {
                        case '"': current.Append('"'); i++; break;
                        case 'n': current.Append('\n'); i++; break;
                        case '\\': current.Append('\\'); i++; break;
                        default: current.Append(c); break;
                    }
                }
                else if (c == '"')
                {
                    inQuotes = false;
                }
                else
                {
                    current.Append(c);
                }
            }
            else if (c == '"')
            {
                inQuotes = true;
                hasToken = true;
            }
            else if (c is ' ' or '\t')
            {
                if (hasToken)
                {
                    result.Add(current.ToString());
                    current.Clear();
                    hasToken = false;
                }
            }
            else
            {
                current.Append(c);
                hasToken = true;
            }
        }
        if (hasToken)
            result.Add(current.ToString());
        return result;
    }

    /// <summary>Split on '|' while respecting double-quoted sections (ISONL lines).</summary>
    internal static List<string> SplitPipeAware(string s)
    {
        var result = new List<string>();
        var current = new StringBuilder();
        var inQuotes = false;

        for (var i = 0; i < s.Length; i++)
        {
            var c = s[i];
            if (inQuotes && c == '\\' && i + 1 < s.Length)
            {
                current.Append(c);
                current.Append(s[i + 1]);
                i++;
            }
            else if (c == '"')
            {
                inQuotes = !inQuotes;
                current.Append(c);
            }
            else if (c == '|' && !inQuotes)
            {
                result.Add(current.ToString());
                current.Clear();
            }
            else
            {
                current.Append(c);
            }
        }
        result.Add(current.ToString());
        return result;
    }

    /// <summary>Parse a node reference string ":type:id".</summary>
    internal static NodeRef ParseNodeRefString(string s)
    {
        if (s.Length == 0 || s[0] != ':')
            throw new GraphError($"Invalid node reference: {s}");
        var secondColon = s.IndexOf(':', 1);
        if (secondColon < 0)
            throw new GraphError($"Invalid node reference: {s}");
        return new NodeRef(s[1..secondColon], s[(secondColon + 1)..]);
    }

    private static readonly StringComparer OrdinalComparer = StringComparer.Ordinal;

    // =========================================================================
    // ISON Serialization
    // =========================================================================

    /// <summary>
    /// Serialize the graph to ISON format:
    ///
    ///     nodes.{type}
    ///     id {property fields...}
    ///     {id} {property values...}
    ///
    ///     edges.{REL}
    ///     source target {property fields...}
    ///     :type:id :type:id {property values...}
    /// </summary>
    /// <summary>Node rows within a type block, sorted by Id (ordinal string compare).</summary>
    private static List<Node> SortedNodes(List<Node> typeNodes)
    {
        var sorted = new List<Node>(typeNodes);
        sorted.Sort((a, b) => string.CompareOrdinal(a.Id, b.Id));
        return sorted;
    }

    /// <summary>
    /// Edge rows within a rel_type block, sorted by
    /// (Source.Type, Source.Id, Target.Type, Target.Id) - ordinal.
    /// </summary>
    private static List<Edge> SortedEdges(List<Edge> edges)
    {
        var sorted = new List<Edge>(edges);
        sorted.Sort((a, b) =>
        {
            var cmp = string.CompareOrdinal(a.Source.Type, b.Source.Type);
            if (cmp != 0) return cmp;
            cmp = string.CompareOrdinal(a.Source.Id, b.Source.Id);
            if (cmp != 0) return cmp;
            cmp = string.CompareOrdinal(a.Target.Type, b.Target.Type);
            if (cmp != 0) return cmp;
            return string.CompareOrdinal(a.Target.Id, b.Target.Id);
        });
        return sorted;
    }

    /// <summary>
    /// Build the ISON Document this graph serializes to.
    /// </summary>
    /// <remarks>
    /// ISONGraph decides <em>what</em> to emit - which blocks, which rows,
    /// which columns - and hands every byte-level decision to Ison.Parser's
    /// canonical writer: quoting, escaping, delimiters, column layout, and
    /// the final block and row order.
    ///
    /// This used to be hand-rolled here, which meant ISON syntax had two
    /// implementations per language that had to agree forever. They did not:
    /// the id column was written unquoted, so a node id containing a space
    /// produced output that would not reparse.
    /// </remarks>
    /// <summary>
    /// Written into <c>meta.graph</c> by the Python <c>MultiGraph</c>. This
    /// port has no multigraph, so loading such a document would silently drop
    /// its parallel edges; it is refused instead.
    /// </summary>
    public const string MultigraphFormat = "ison-graph-multigraph-v1";

    private Document BuildDocument()
    {
        var doc = new Document();

        // Directedness is graph semantics: an undirected graph that reloads as
        // directed silently changes traversal, degree and cycle results, and
        // its two mirror rows become two distinct edges. Written only when it
        // departs from the default so every directed graph keeps its bytes.
        if (!Directed)
        {
            var meta = new Block("meta", "graph");
            meta.Fields.Add("directed");
            meta.Rows.Add(new Dictionary<string, object?> { ["directed"] = false });
            doc.Blocks.Add(meta);
        }

        var nodeTypes = new List<string>(_nodeTypeOrder);
        nodeTypes.Sort(OrdinalComparer);
        foreach (var nodeType in nodeTypes)
        {
            var typeNodes = _nodeOrder[nodeType];
            if (typeNodes.Count == 0) continue;

            var propKeys = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var node in typeNodes)
                foreach (var key in node.Properties.Keys)
                    propKeys.Add(key);

            var block = new Block("nodes", nodeType);
            block.Fields.Add("id");
            foreach (var key in propKeys) block.Fields.Add(key);

            foreach (var node in typeNodes)
            {
                var row = new Dictionary<string, object?> { ["id"] = node.Id };
                foreach (var key in propKeys)
                    row[key] = node.Properties.TryGetValue(key, out var v) ? v : null;
                block.Rows.Add(row);
            }
            doc.Blocks.Add(block);
        }

        var relTypes = new List<string>(_edgeTypeOrder);
        relTypes.Sort(OrdinalComparer);
        foreach (var relType in relTypes)
        {
            var edges = _edgesByType[relType];
            if (edges.Count == 0) continue;

            var propKeys = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var edge in edges)
                foreach (var key in edge.Properties.Keys)
                    propKeys.Add(key);

            var block = new Block("edges", relType);
            block.Fields.Add("source");
            block.Fields.Add("target");
            foreach (var key in propKeys) block.Fields.Add(key);

            foreach (var edge in edges)
            {
                var row = new Dictionary<string, object?>
                {
                    ["source"] = new Reference(edge.Source.Id, edge.Source.Type),
                    ["target"] = new Reference(edge.Target.Id, edge.Target.Type),
                };
                foreach (var key in propKeys)
                    row[key] = edge.Properties.TryGetValue(key, out var v) ? v : null;
                block.Rows.Add(row);
            }
            doc.Blocks.Add(block);
        }

        return doc;
    }

    /// <summary>
    /// Serialize to canonical ISON (ISONCS). The same logical graph always
    /// serializes to the same bytes regardless of construction order.
    /// </summary>
    public string ToIson() => IsonParser.Ison.DumpsCanonical(BuildDocument());

    /// <summary>
    /// Serialize to canonical ISONL. Row order matches <see cref="ToIson"/>.
    /// </summary>
    public string ToIsonl() => IsonParser.Ison.DumpsCanonicalIsonl(BuildDocument());

    /// <summary>
    /// Node ids are identifiers rather than values, so they are always text.
    /// Property values keep whatever type the parser produced - flattening
    /// them here was what made this port emit every value quoted.
    /// </summary>
    private static string? IdText(object? value) => value switch
    {
        null => null,
        Reference r => r.ToIson(),
        bool b => b ? "true" : "false",
        _ => value.ToString(),
    };

    private static ISONGraph BuildFromDocument(Document doc, string name)
    {
        // meta.graph carries graph semantics: 'directed' (written by every
        // port for an undirected graph) and 'format' (written by the Python
        // MultiGraph, which this port cannot represent).
        var directed = true;
        foreach (var block in doc.Blocks)
        {
            if (block.Kind == "nodes" || block.Kind == "edges") continue;
            if (block.Kind == "meta" && block.Name == "graph")
            {
                foreach (var row in block.Rows)
                {
                    if (row.TryGetValue("format", out var format) && format is string f && f == MultigraphFormat)
                        throw new GraphError(
                            $"This is a {MultigraphFormat} document, which may contain multiple edges " +
                            "per (relType, source, target) triple; this port has no MultiGraph and " +
                            "would silently drop them.");
                    if (row.TryGetValue("directed", out var d) && d is bool b)
                        directed = b;
                }
                continue;
            }
            throw new GraphError(
                $"unknown block kind '{block.Kind}' (expected 'nodes', 'edges' or 'meta')");
        }

        var graph = new ISONGraph(name, directed);

        // Nodes first regardless of block order - the canonical writer sorts
        // blocks by name, which puts 'edges' ahead of 'nodes'.
        foreach (var block in doc.Blocks)
        {
            if (block.Kind != "nodes") continue;
            foreach (var row in block.Rows)
            {
                var id = row.TryGetValue("id", out var rawId) ? IdText(rawId) : null;
                if (id is null)
                    throw new GraphError("FromIson: node row has no id");

                var props = new Dictionary<string, object?>();
                foreach (var kv in row)
                {
                    if (kv.Key == "id") continue;
                    if (kv.Value is not null) props[kv.Key] = kv.Value;
                }
                try
                {
                    graph.AddNode(block.Name, id, props);
                }
                catch (DuplicateNodeError ex)
                {
                    throw new GraphError($"duplicate node row: {ex.Message}");
                }
            }
        }

        foreach (var block in doc.Blocks)
        {
            if (block.Kind != "edges") continue;
            foreach (var row in block.Rows)
            {
                row.TryGetValue("source", out var rawSource);
                row.TryGetValue("target", out var rawTarget);
                if (rawSource is not Reference source || rawTarget is not Reference target)
                    throw new GraphError(
                        "FromIson: Invalid node reference: edge row is missing a source or target");

                var props = new Dictionary<string, object?>();
                foreach (var kv in row)
                {
                    if (kv.Key == "source" || kv.Key == "target") continue;
                    if (kv.Value is not null) props[kv.Key] = kv.Value;
                }
                var sourceRef = new NodeRef(source.Type ?? string.Empty, source.Id);
                var targetRef = new NodeRef(target.Type ?? string.Empty, target.Id);
                foreach (var end in new[] { sourceRef, targetRef })
                {
                    if (!graph.HasNode(end.Type, end.Id))
                        throw new GraphError(
                            $"Invalid node reference: :{end.Type}:{end.Id} has not been defined");
                }
                // An undirected graph serializes both an edge and the mirror it
                // auto-created; re-adding the mirror would collide, so skip what
                // is already reconstructed. A directed graph still fails on a
                // genuine duplicate.
                if (!graph.Directed && graph.HasEdge(block.Name, sourceRef, targetRef))
                    continue;
                try
                {
                    graph.AddEdge(block.Name, sourceRef, targetRef, props);
                }
                catch (DuplicateEdgeError ex)
                {
                    throw new GraphError($"duplicate edge row: {ex.Message}");
                }
            }
        }

        return graph;
    }

    /// <summary>Parse a graph from ISON.</summary>
    /// <remarks>
    /// Parser failures are rewrapped as <see cref="GraphError"/> so the public
    /// contract is unchanged by routing through Ison.Parser.
    /// </remarks>
    public static ISONGraph FromIson(string text, string name = "graph")
        => BuildFromDocument(ParseOrThrow(() => IsonParser.Ison.Loads(text), "FromIson"), name);

    /// <summary>Parse a graph from ISONL.</summary>
    public static ISONGraph FromIsonl(string text, string name = "graph")
        => BuildFromDocument(ParseOrThrow(() => IsonParser.Ison.LoadsIsonl(text), "FromIsonl"), name);

    private static Document ParseOrThrow(Func<Document> parse, string context)
    {
        try
        {
            return parse();
        }
        catch (IsonParser.IsonException ex)
        {
            // "malformed block header" / "malformed line" are the phrases the
            // hand-rolled parser used; keep them so callers matching on the
            // message still work.
            var kind = context == "FromIsonl" ? "malformed line" : "malformed block header";
            throw new GraphError($"{context}: {kind}: {ex.Message}");
        }
    }

    public void Save(string path, string format = "auto")
    {
        var actualFormat = format;
        if (format == "auto")
        {
            actualFormat = path.EndsWith(".isonl", StringComparison.OrdinalIgnoreCase)
                ? "isonl"
                : "ison";
        }
        var content = actualFormat == "isonl" ? ToIsonl() : ToIson();
        File.WriteAllText(path, content, new UTF8Encoding(false));
    }

    /// <summary>Load a graph from a file ('ison', 'isonl', or 'auto' by extension).</summary>
    public static ISONGraph Load(string path, string format = "auto")
    {
        var text = File.ReadAllText(path, Encoding.UTF8);
        var actualFormat = format;
        if (format == "auto")
        {
            actualFormat = path.EndsWith(".isonl", StringComparison.OrdinalIgnoreCase)
                ? "isonl"
                : "ison";
        }
        var name = System.IO.Path.GetFileNameWithoutExtension(path);
        return actualFormat == "isonl" ? FromIsonl(text, name) : FromIson(text, name);
    }

    /// <summary>Alias for <see cref="FromIson"/>.</summary>
    public static ISONGraph Parse(string text, string name = "graph") => FromIson(text, name);
}
