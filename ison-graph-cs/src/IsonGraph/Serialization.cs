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

    public string ToIson()
    {
        var blocks = new List<string>();

        // Serialize nodes by type (sorted, ordinal).
        var sortedNodeTypes = new List<string>(_nodeTypeOrder);
        sortedNodeTypes.Sort(OrdinalComparer);

        foreach (var nodeType in sortedNodeTypes)
        {
            var typeNodes = SortedNodes(_nodeOrder[nodeType]);
            if (typeNodes.Count == 0)
                continue;

            var propKeys = new SortedSet<string>(OrdinalComparer);
            foreach (var node in typeNodes)
            {
                foreach (var key in node.Properties.Keys)
                    propKeys.Add(key);
            }

            var lines = new List<string> { "nodes." + nodeType };
            var fields = new List<string> { "id" };
            fields.AddRange(propKeys);
            lines.Add(string.Join(" ", fields));

            foreach (var node in typeNodes)
            {
                var values = new List<string> { QuoteValue(node.Id) };
                foreach (var key in propKeys)
                {
                    values.Add(node.Properties.TryGetValue(key, out var v)
                        ? QuoteValue(v)
                        : "null");
                }
                lines.Add(string.Join(" ", values));
            }

            blocks.Add(string.Join("\n", lines));
        }

        // Serialize edges by type (sorted, ordinal).
        var sortedEdgeTypes = new List<string>(_edgeTypeOrder);
        sortedEdgeTypes.Sort(OrdinalComparer);

        foreach (var relType in sortedEdgeTypes)
        {
            var relEdges = SortedEdges(_edgesByType[relType]);
            if (relEdges.Count == 0)
                continue;

            var propKeys = new SortedSet<string>(OrdinalComparer);
            foreach (var edge in relEdges)
            {
                foreach (var key in edge.Properties.Keys)
                    propKeys.Add(key);
            }

            var lines = new List<string> { "edges." + relType };
            var fields = new List<string> { "source", "target" };
            fields.AddRange(propKeys);
            lines.Add(string.Join(" ", fields));

            foreach (var edge in relEdges)
            {
                var values = new List<string> { edge.Source.ToIsonRef(), edge.Target.ToIsonRef() };
                foreach (var key in propKeys)
                {
                    values.Add(edge.Properties.TryGetValue(key, out var v)
                        ? QuoteValue(v)
                        : "null");
                }
                lines.Add(string.Join(" ", values));
            }

            blocks.Add(string.Join("\n", lines));
        }

        return string.Join("\n\n", blocks);
    }

    /// <summary>
    /// Serialize the graph to the ISONL streaming format, one line per row:
    ///     nodes.person|id name age|1 Alice 30
    /// </summary>
    public string ToIsonl()
    {
        var lines = new List<string>();

        // Serialize nodes (type blocks, then rows, both sorted).
        var sortedNodeTypes = new List<string>(_nodeTypeOrder);
        sortedNodeTypes.Sort(OrdinalComparer);

        foreach (var nodeType in sortedNodeTypes)
        {
            foreach (var node in SortedNodes(_nodeOrder[nodeType]))
            {
                var propKeys = new List<string>(node.Properties.Keys);
                propKeys.Sort(OrdinalComparer);

                var fields = new List<string> { "id" };
                fields.AddRange(propKeys);
                var values = new List<string> { QuoteValue(node.Id) };
                foreach (var key in propKeys)
                    values.Add(QuoteValue(node.Properties[key]));

                lines.Add($"nodes.{node.Type}|{string.Join(" ", fields)}|{string.Join(" ", values)}");
            }
        }

        // Serialize edges (type blocks, then rows, both sorted).
        var sortedEdgeTypes = new List<string>(_edgeTypeOrder);
        sortedEdgeTypes.Sort(OrdinalComparer);

        foreach (var relType in sortedEdgeTypes)
        {
            foreach (var edge in SortedEdges(_edgesByType[relType]))
            {
                var propKeys = new List<string>(edge.Properties.Keys);
                propKeys.Sort(OrdinalComparer);

                var fields = new List<string> { "source", "target" };
                fields.AddRange(propKeys);
                var values = new List<string> { edge.Source.ToIsonRef(), edge.Target.ToIsonRef() };
                foreach (var key in propKeys)
                    values.Add(QuoteValue(edge.Properties[key]));

                lines.Add($"edges.{relType}|{string.Join(" ", fields)}|{string.Join(" ", values)}");
            }
        }

        return string.Join("\n", lines);
    }

    // =========================================================================
    // Deserialization
    // =========================================================================

    private static (string Kind, string TypeName) ParseBlockHeader(string header, string context)
    {
        var dotPos = header.IndexOf('.');
        if (dotPos < 0)
        {
            throw new GraphError(
                $"{context}: malformed block header '{header}' " +
                "(expected 'nodes.<type>' or 'edges.<REL>')");
        }
        var kind = header[..dotPos];
        var typeName = header[(dotPos + 1)..];
        if (kind != "nodes" && kind != "edges")
        {
            throw new GraphError(
                $"{context}: unknown block kind '{kind}' in header '{header}' " +
                "(expected 'nodes' or 'edges')");
        }
        return (kind, typeName);
    }

    private void AddRowFromProps(string kind, string typeName,
                                 IReadOnlyList<string> fields, IReadOnlyList<string> values,
                                 string context, string rowDescription)
    {
        var props = new Dictionary<string, string>();
        for (var i = 0; i < fields.Count; i++)
            props[fields[i]] = values[i];

        if (kind == "nodes")
        {
            if (!props.TryGetValue("id", out var nodeId))
            {
                throw new GraphError(
                    $"{context}: 'nodes.{typeName}' is missing the required 'id' field: " +
                    rowDescription);
            }
            props.Remove("id");
            try
            {
                AddNode(typeName, nodeId, props);
            }
            catch (DuplicateNodeError)
            {
                throw new GraphError(
                    $"{context}: duplicate node row ':{typeName}:{nodeId}' in 'nodes.{typeName}'");
            }
        }
        else // edges
        {
            if (!props.TryGetValue("source", out var sourceRef) ||
                !props.TryGetValue("target", out var targetRef))
            {
                throw new GraphError(
                    $"{context}: 'edges.{typeName}' is missing the required 'source' and/or " +
                    $"'target' field: {rowDescription}");
            }
            var source = ParseNodeRefString(sourceRef);
            var target = ParseNodeRefString(targetRef);
            props.Remove("source");
            props.Remove("target");
            try
            {
                AddEdge(typeName, source, target, props);
            }
            catch (NodeNotFoundError e)
            {
                throw new GraphError(
                    $"{context}: edge in 'edges.{typeName}' references a node that has not " +
                    $"been defined ({e.Message}); node rows must appear before the edges " +
                    "that use them");
            }
            catch (DuplicateEdgeError)
            {
                throw new GraphError(
                    $"{context}: duplicate edge row '{sourceRef} -> {targetRef}' " +
                    $"in 'edges.{typeName}'");
            }
        }
    }

    /// <summary>
    /// Parse a graph from ISON format. Malformed input (field/value count
    /// mismatch, missing id/source/target, unknown block kind, duplicates,
    /// undefined edge endpoints) throws a descriptive <see cref="GraphError"/>.
    /// </summary>
    public static ISONGraph FromIson(string text, string name = "graph")
    {
        var graph = new ISONGraph(name);

        // Split into blocks separated by blank lines.
        var blocks = new List<List<string>>();
        var currentBlock = new List<string>();
        foreach (var rawLine in text.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0)
            {
                if (currentBlock.Count > 0)
                {
                    blocks.Add(currentBlock);
                    currentBlock = new List<string>();
                }
            }
            else
            {
                currentBlock.Add(line);
            }
        }
        if (currentBlock.Count > 0)
            blocks.Add(currentBlock);

        foreach (var blockLines in blocks)
        {
            var header = blockLines[0];
            var (kind, typeName) = ParseBlockHeader(header, "FromIson");

            if (blockLines.Count < 2)
            {
                throw new GraphError(
                    $"FromIson: block '{header}' has no field-name line");
            }

            var fields = SplitFields(blockLines[1]);

            for (var r = 2; r < blockLines.Count; r++)
            {
                var dataLine = blockLines[r];
                var values = SplitFields(dataLine);
                if (values.Count != fields.Count)
                {
                    throw new GraphError(
                        $"FromIson: row in block '{header}' has {values.Count} values but " +
                        $"the header declares {fields.Count} fields: {dataLine}");
                }
                graph.AddRowFromProps(kind, typeName, fields, values, "FromIson", dataLine);
            }
        }

        return graph;
    }

    /// <summary>
    /// Parse a graph from the ISONL streaming format (one row per line,
    /// "kind.type|fields|values"). Malformed lines throw <see cref="GraphError"/>.
    /// </summary>
    public static ISONGraph FromIsonl(string text, string name = "graph")
    {
        var graph = new ISONGraph(name);

        foreach (var rawLine in text.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0)
                continue;

            var parts = SplitPipeAware(line);
            if (parts.Count != 3)
            {
                throw new GraphError(
                    $"FromIsonl: malformed line (expected 'kind.type|fields|values'): {line}");
            }

            var (kind, typeName) = ParseBlockHeader(parts[0], "FromIsonl");
            var fields = SplitFields(parts[1]);
            var values = SplitFields(parts[2]);

            if (fields.Count != values.Count)
            {
                throw new GraphError(
                    $"FromIsonl: line for '{parts[0]}' has {values.Count} values but " +
                    $"declares {fields.Count} fields: {line}");
            }

            graph.AddRowFromProps(kind, typeName, fields, values, "FromIsonl", line);
        }

        return graph;
    }

    // =========================================================================
    // File I/O
    // =========================================================================

    /// <summary>Save the graph to a file ('ison', 'isonl', or 'auto' by extension).</summary>
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
