// ISONQL - Pure Property Graph Query Language for ISONGraph
//
// A declarative query language for property graph operations.
//
// Supported query types:
// - NODES: Select and filter nodes
// - EDGES: Select and filter edges
// - TRAVERSE: Graph traversal with patterns
// - PATH: Shortest path finding
// - COUNT: Count nodes matching criteria
// - SUM/AVG/MIN/MAX: Numeric aggregations
//
// Example:
//     var engine = new QueryEngine(graph);
//     var result = engine.Execute("NODES person WHERE age > 25");
//     var result2 = engine.Execute("TRAVERSE person:alice -> KNOWS -> person");
//     var result3 = engine.Match("person").Where("age", ">", 25)
//                         .OrderBy("age", "DESC").Limit(10).Execute();
//
// Author: Mahesh Vaikri
// Version: 1.0.0

using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace IsonGraph;

// =============================================================================
// Enums
// =============================================================================

/// <summary>Query operators for conditions.</summary>
public enum Operator
{
    Eq,
    Ne,
    Gt,
    Ge,
    Lt,
    Le,
    In,
    NotIn,
    Contains,
    StartsWith,
    EndsWith,
    Matches,
    Exists,
    NotExists,
}

/// <summary>Sort order for results.</summary>
public enum SortOrder
{
    Asc,
    Desc,
}

/// <summary>Supported query types.</summary>
public enum QueryType
{
    Nodes,
    Edges,
    Traverse,
    Path,
    Count,
    Sum,
    Avg,
    Min,
    Max,
}

// =============================================================================
// Condition
// =============================================================================

/// <summary>
/// A query condition for filtering. <see cref="Value"/> holds null, bool,
/// long, double, string, or List&lt;string&gt; (for IN / NOT IN lists).
/// </summary>
public sealed class Condition
{
    public string Field { get; }
    public Operator Operator { get; }
    public object? Value { get; }

    public Condition(string field, Operator op, object? value = null)
    {
        Field = field;
        Operator = op;
        Value = value;
    }

    internal static string ValueToString(object? value) => value switch
    {
        null => "null",
        bool b => b ? "true" : "false",
        long l => l.ToString(CultureInfo.InvariantCulture),
        double d => d.ToString(CultureInfo.InvariantCulture),
        string s => s,
        _ => value.ToString() ?? "",
    };

    /// <summary>Evaluate the condition against a property dictionary.</summary>
    public bool Evaluate(IReadOnlyDictionary<string, object?> properties)
    {
        // EXISTS / NOT EXISTS checks
        if (Operator == Operator.Exists)
            return properties.ContainsKey(Field);
        if (Operator == Operator.NotExists)
            return !properties.ContainsKey(Field);

        // Field must exist for other comparisons
        if (!properties.TryGetValue(Field, out var propValue))
            return false;

        // Numeric comparison first when the condition value is numeric. A
        // property that is genuinely a number compares exactly; one stored as
        // a string still parses, so queries written before properties were
        // typed keep working.
        if (Value is long or double &&
            Operator is Operator.Eq or Operator.Ne or Operator.Gt
                        or Operator.Ge or Operator.Lt or Operator.Le)
        {
            if (PropertyValue.AsDouble(propValue) is not double propNum)
            {
                return false;
            }
            var valNum = Value is long l ? l : (double)Value;
            return Operator switch
            {
                Operator.Eq => propNum == valNum,
                Operator.Ne => propNum != valNum,
                Operator.Gt => propNum > valNum,
                Operator.Ge => propNum >= valNum,
                Operator.Lt => propNum < valNum,
                Operator.Le => propNum <= valNum,
                _ => false,
            };
        }

        // String comparison, against the value's text form - which is what
        // every property was before they carried types.
        var valStr = ValueToString(Value);
        var propText = PropertyValue.ValueText(propValue);

        switch (Operator)
        {
            case Operator.Eq: return propText == valStr;
            case Operator.Ne: return propText != valStr;
            case Operator.Gt: return string.CompareOrdinal(propText, valStr) > 0;
            case Operator.Ge: return string.CompareOrdinal(propText, valStr) >= 0;
            case Operator.Lt: return string.CompareOrdinal(propText, valStr) < 0;
            case Operator.Le: return string.CompareOrdinal(propText, valStr) <= 0;
            case Operator.Contains:
                return propText.Contains(valStr, StringComparison.Ordinal);
            case Operator.StartsWith:
                return propText.StartsWith(valStr, StringComparison.Ordinal);
            case Operator.EndsWith:
                return propText.EndsWith(valStr, StringComparison.Ordinal);
            case Operator.Matches:
                try
                {
                    // Python re.match semantics: the match must start at position 0.
                    var m = Regex.Match(propText, valStr);
                    return m.Success && m.Index == 0;
                }
                catch (ArgumentException)
                {
                    return false;
                }
            case Operator.In:
                return Value is List<string> inList && inList.Contains(propValue);
            case Operator.NotIn:
                return Value is not List<string> notInList || !notInList.Contains(propValue);
            default:
                return false;
        }
    }

    public override string ToString()
    {
        var opStr = Operator switch
        {
            Operator.Eq => "=",
            Operator.Ne => "!=",
            Operator.Gt => ">",
            Operator.Ge => ">=",
            Operator.Lt => "<",
            Operator.Le => "<=",
            Operator.In => "IN",
            Operator.NotIn => "NOT IN",
            Operator.Contains => "CONTAINS",
            Operator.StartsWith => "STARTS_WITH",
            Operator.EndsWith => "ENDS_WITH",
            Operator.Matches => "MATCHES",
            Operator.Exists => "EXISTS",
            Operator.NotExists => "NOT EXISTS",
            _ => "?",
        };

        if (Operator is Operator.Exists or Operator.NotExists)
            return opStr + " " + Field;

        static string QuoteString(string s)
        {
            var sb = new StringBuilder("\"");
            foreach (var c in s)
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

        string valStr;
        if (Value is string s)
        {
            valStr = QuoteString(s);
        }
        else if (Value is List<string> list)
        {
            valStr = "(" + string.Join(", ", list.Select(QuoteString)) + ")";
        }
        else
        {
            valStr = ValueToString(Value);
        }

        return $"{Field} {opStr} {valStr}";
    }
}

// =============================================================================
// Result Types
// =============================================================================

/// <summary>A node row in a query result.</summary>
public sealed class NodeResult
{
    public string Type { get; }
    public string Id { get; }
    public Dictionary<string, object?> Properties { get; }

    public NodeResult(string type, string id, Dictionary<string, object?> properties)
    {
        Type = type;
        Id = id;
        Properties = properties;
    }
}

/// <summary>An edge row in a query result.</summary>
public sealed class EdgeResult
{
    public string RelType { get; }
    public NodeRef Source { get; }
    public NodeRef Target { get; }
    public Dictionary<string, object?> Properties { get; }

    public EdgeResult(string relType, NodeRef source, NodeRef target,
                      Dictionary<string, object?> properties)
    {
        RelType = relType;
        Source = source;
        Target = target;
        Properties = properties;
    }
}

/// <summary>A path row in a query result.</summary>
public sealed class PathResult
{
    public List<NodeRef> Nodes { get; }
    public List<EdgeResult> Edges { get; }
    public int Length { get; }

    public PathResult(List<NodeRef> nodes, List<EdgeResult> edges, int length)
    {
        Nodes = nodes;
        Edges = edges;
        Length = length;
    }
}

/// <summary>Result of a query execution.</summary>
public sealed class QueryResult
{
    /// <summary>Node rows (NODES queries).</summary>
    public IReadOnlyList<NodeResult> Nodes { get; internal set; } = Array.Empty<NodeResult>();

    /// <summary>Edge rows (EDGES queries).</summary>
    public IReadOnlyList<EdgeResult> Edges { get; internal set; } = Array.Empty<EdgeResult>();

    /// <summary>Node references (TRAVERSE queries).</summary>
    public IReadOnlyList<NodeRef> Refs { get; internal set; } = Array.Empty<NodeRef>();

    /// <summary>Path rows (PATH queries).</summary>
    public IReadOnlyList<PathResult> Paths { get; internal set; } = Array.Empty<PathResult>();

    /// <summary>COUNT result.</summary>
    public long? CountValue { get; internal set; }

    /// <summary>Aggregation result (SUM/AVG/MIN/MAX); null when no values matched.</summary>
    public double? Value { get; internal set; }

    public int Count { get; internal set; }
    public int TotalCount { get; internal set; }
    public double ExecutionTimeMs { get; internal set; }
    public string Query { get; internal set; } = "";
    public string QueryType { get; internal set; } = "";

    /// <summary>First node row, or null.</summary>
    public NodeResult? FirstNode() => Nodes.Count > 0 ? Nodes[0] : null;

    public override string ToString() =>
        $"QueryResult(count={Count}, total={TotalCount}, " +
        $"time={ExecutionTimeMs.ToString("F2", CultureInfo.InvariantCulture)}ms)";
}

// =============================================================================
// Parsed Query Structure
// =============================================================================

/// <summary>One step of a TRAVERSE pattern.</summary>
public sealed class TraverseStep
{
    public Direction Direction { get; set; }
    public string RelType { get; set; } = "";
    public string TargetType { get; set; } = "*";
}

/// <summary>Structured representation of a parsed ISONQL query.</summary>
public sealed class ParsedQuery
{
    public QueryType Type { get; set; }
    public string? NodeType { get; set; }
    public string? RelType { get; set; }

    /// <summary>
    /// WHERE clause with AND-precedence: outer list = OR-groups, inner list =
    /// AND-ed conditions. Empty means "match everything".
    /// </summary>
    public List<List<Condition>> ConditionGroups { get; set; } = new();

    public string? OrderBy { get; set; }
    public SortOrder OrderDir { get; set; } = SortOrder.Asc;
    public int? Limit { get; set; }
    public int Offset { get; set; }
    public List<string>? ReturnFields { get; set; }

    // TRAVERSE
    public NodeRef? Start { get; set; }
    public List<TraverseStep> Pattern { get; set; } = new();
    public int? MaxDepth { get; set; }

    // PATH
    public NodeRef? Source { get; set; }
    public NodeRef? Target { get; set; }
    public string? Via { get; set; }
    public int MaxHops { get; set; } = 10;

    // Aggregations
    public string? Property { get; set; }

    /// <summary>Flattened conditions (all groups concatenated); handy for tests.</summary>
    public List<Condition> Conditions => ConditionGroups.SelectMany(g => g).ToList();
}

// =============================================================================
// ISONQL Parser
// =============================================================================

/// <summary>
/// Parser for ISONQL (ISON Query Language).
///
/// Supported syntax:
/// - NODES [type] [WHERE conditions] [ORDER BY field [ASC|DESC]] [LIMIT n] [OFFSET n] [RETURN fields]
/// - EDGES [type] [WHERE conditions] [LIMIT n]
/// - TRAVERSE type:id -> REL -> target [MAX depth] [LIMIT n]
/// - PATH source TO target [VIA rel] [MAX hops]
/// - COUNT [type] [WHERE conditions]
/// - SUM/AVG/MIN/MAX type.property [WHERE conditions]
/// </summary>
public sealed class ISONQLParser
{
    private static readonly HashSet<string> Keywords = new(StringComparer.Ordinal)
    {
        "NODES", "EDGES", "TRAVERSE", "PATH", "COUNT", "SUM", "AVG", "MIN", "MAX",
        "WHERE", "AND", "OR", "NOT", "ORDER", "BY", "ASC", "DESC", "LIMIT", "OFFSET",
        "TO", "VIA", "RETURN", "AS", "IN", "CONTAINS", "STARTS_WITH",
        "ENDS_WITH", "MATCHES", "EXISTS", "TRUE", "FALSE", "NULL", "NONE", "NIL",
    };

    private static readonly Dictionary<string, Operator> SymbolOperators = new(StringComparer.Ordinal)
    {
        ["="] = Operator.Eq,
        ["=="] = Operator.Eq,
        ["!="] = Operator.Ne,
        ["<>"] = Operator.Ne,
        [">"] = Operator.Gt,
        [">="] = Operator.Ge,
        ["<"] = Operator.Lt,
        ["<="] = Operator.Le,
    };

    private List<string> _tokens = new();
    private int _pos;

    /// <summary>Parse an ISONQL query string into a <see cref="ParsedQuery"/>.</summary>
    public ParsedQuery Parse(string query)
    {
        _tokens = Tokenize(query);
        _pos = 0;

        if (_tokens.Count == 0)
            throw new ArgumentException("Empty query");

        var keyword = _tokens[0].ToUpperInvariant();
        return keyword switch
        {
            "NODES" => ParseNodesQuery(),
            "EDGES" => ParseEdgesQuery(),
            "TRAVERSE" => ParseTraverseQuery(),
            "PATH" => ParsePathQuery(),
            "COUNT" => ParseCountQuery(),
            "SUM" or "AVG" or "MIN" or "MAX" => ParseAggregationQuery(keyword),
            _ => throw new ArgumentException(
                $"Unknown query type: {keyword}. " +
                "Supported: NODES, EDGES, TRAVERSE, PATH, COUNT, SUM, AVG, MIN, MAX"),
        };
    }

    /// <summary>
    /// Tokenize a query string. A ':' joins into a word token when immediately
    /// followed by an alphanumeric or underscore (so "person:1" is one token);
    /// unknown characters raise a parse error; negative number literals are
    /// single tokens.
    /// </summary>
    public static List<string> Tokenize(string query)
    {
        var tokens = new List<string>();
        var i = 0;
        query = query.Trim();

        while (i < query.Length)
        {
            var c = query[i];

            // Skip whitespace
            if (char.IsWhiteSpace(c))
            {
                i++;
                continue;
            }

            // String literals (single or double quoted); unescape \n and \<char>
            if (c is '"' or '\'')
            {
                var quote = c;
                i++;
                var literal = new StringBuilder();
                while (i < query.Length && query[i] != quote)
                {
                    if (query[i] == '\\' && i + 1 < query.Length)
                    {
                        var next = query[i + 1];
                        literal.Append(next == 'n' ? '\n' : next);
                        i += 2;
                    }
                    else
                    {
                        literal.Append(query[i]);
                        i++;
                    }
                }
                tokens.Add(literal.ToString());
                i++; // skip closing quote
                continue;
            }

            // Multi-character operators
            if (i + 1 < query.Length)
            {
                var two = query.Substring(i, 2);
                if (two is "==" or "!=" or ">=" or "<=" or "<>" or "->" or "<-" or "--")
                {
                    tokens.Add(two);
                    i += 2;
                    continue;
                }
            }

            // Negative number literals (e.g. -5, -3.14)
            if (c == '-' && i + 1 < query.Length && char.IsDigit(query[i + 1]))
            {
                var start = i;
                i++;
                while (i < query.Length && (char.IsDigit(query[i]) || query[i] == '.'))
                    i++;
                tokens.Add(query[start..i]);
                continue;
            }

            // Single-character operators and punctuation
            if (c is '=' or '<' or '>' or '!' or '(' or ')' or ',' or '.' or '*')
            {
                tokens.Add(c.ToString());
                i++;
                continue;
            }

            // Node reference :type:id
            if (c == ':')
            {
                var start = i;
                i++;
                while (i < query.Length &&
                       (char.IsLetterOrDigit(query[i]) || query[i] is ':' or '_' or '-'))
                {
                    i++;
                }
                tokens.Add(query[start..i]);
                continue;
            }

            // Words (identifiers, keywords, numbers, type:id node refs)
            if (char.IsLetterOrDigit(c) || c == '_')
            {
                var start = i;
                while (i < query.Length)
                {
                    var ch = query[i];
                    if (char.IsLetterOrDigit(ch) || ch is '_' or '.' or '-')
                    {
                        i++;
                    }
                    else if (ch == ':' && i + 1 < query.Length &&
                             (char.IsLetterOrDigit(query[i + 1]) || query[i + 1] == '_'))
                    {
                        // Keep type:id references as a single token
                        i++;
                    }
                    else
                    {
                        break;
                    }
                }
                tokens.Add(query[start..i]);
                continue;
            }

            throw new ArgumentException(
                $"Unexpected character '{c}' in query at position {i}");
        }

        return tokens;
    }

    private string? Current() => _pos < _tokens.Count ? _tokens[_pos] : null;

    private string? Peek(int offset)
    {
        var pos = _pos + offset;
        return pos < _tokens.Count ? _tokens[pos] : null;
    }

    private string? Advance()
    {
        var token = Current();
        _pos++;
        return token;
    }

    private string Expect(string expected)
    {
        var token = Advance();
        if (token is null ||
            !string.Equals(token, expected, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"Expected '{expected}', got '{token}'");
        }
        return token;
    }

    private bool Match(params string[] expected)
    {
        var current = Current();
        if (current is null)
            return false;
        foreach (var e in expected)
        {
            if (string.Equals(current, e, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    private int ExpectInt(string clause)
    {
        var token = Advance();
        if (token is null ||
            !int.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n))
        {
            throw new ArgumentException($"Expected integer after {clause}, got '{token}'");
        }
        return n;
    }

    // -------------------------------------------------------------------------
    // Query Parsers
    // -------------------------------------------------------------------------

    private ParsedQuery ParseNodesQuery()
    {
        Advance(); // Skip 'NODES'
        var result = new ParsedQuery { Type = QueryType.Nodes };

        var shorthand = new List<Condition>();

        // Node type (optional)
        if (Current() is not null && !Match("WHERE", "ORDER", "LIMIT", "RETURN"))
        {
            var nodeType = Advance();
            result.NodeType = nodeType;
            // Handle shorthand: person(name="Alice")
            if (Match("("))
            {
                Advance(); // Skip '('
                shorthand = ParseShorthandConditions();
            }
        }

        // WHERE clause
        if (Match("WHERE"))
        {
            Advance();
            result.ConditionGroups = MergeConditionSets(shorthand, ParseConditions());
        }
        else if (shorthand.Count > 0)
        {
            result.ConditionGroups = new List<List<Condition>> { shorthand };
        }

        // ORDER BY clause
        if (Match("ORDER"))
        {
            Advance();
            Expect("BY");
            result.OrderBy = Advance();
            if (Match("ASC", "DESC"))
            {
                result.OrderDir = string.Equals(Advance(), "DESC", StringComparison.OrdinalIgnoreCase)
                    ? SortOrder.Desc
                    : SortOrder.Asc;
            }
        }

        // LIMIT clause
        if (Match("LIMIT"))
        {
            Advance();
            result.Limit = ExpectInt("LIMIT");
        }

        // OFFSET clause
        if (Match("OFFSET"))
        {
            Advance();
            result.Offset = ExpectInt("OFFSET");
        }

        // RETURN clause
        if (Match("RETURN"))
        {
            Advance();
            result.ReturnFields = ParseFieldList();
        }

        return result;
    }

    private ParsedQuery ParseEdgesQuery()
    {
        Advance(); // Skip 'EDGES'
        var result = new ParsedQuery { Type = QueryType.Edges };

        // Edge type (optional)
        if (Current() is not null && !Match("WHERE", "LIMIT"))
            result.RelType = Advance();

        if (Match("WHERE"))
        {
            Advance();
            result.ConditionGroups = ParseConditions();
        }

        if (Match("LIMIT"))
        {
            Advance();
            result.Limit = ExpectInt("LIMIT");
        }

        return result;
    }

    private ParsedQuery ParseTraverseQuery()
    {
        Advance(); // Skip 'TRAVERSE'
        var result = new ParsedQuery { Type = QueryType.Traverse };

        // Start node: type:id or :type:id
        result.Start = ParseNodeRefToken(Advance());

        // Parse traversal pattern: -> REL -> target
        while (Match("->", "<-", "--"))
        {
            var dir1 = Advance()!;
            var relType = Advance() ?? "";

            var step = new TraverseStep { RelType = relType };
            if (Match("->", "<-", "--"))
            {
                var dir2 = Advance()!;
                step.Direction = DirectionFromArrows(dir1, dir2);
                step.TargetType = Current() is not null && !Match("MAX", "LIMIT")
                    ? Advance()!
                    : "*";
            }
            else
            {
                step.Direction = DirectionFromArrows(dir1, dir1);
                step.TargetType = "*";
            }

            result.Pattern.Add(step);
        }

        if (Match("MAX"))
        {
            Advance();
            result.MaxDepth = ExpectInt("MAX");
        }

        if (Match("LIMIT"))
        {
            Advance();
            result.Limit = ExpectInt("LIMIT");
        }

        return result;
    }

    private ParsedQuery ParsePathQuery()
    {
        Advance(); // Skip 'PATH'
        var result = new ParsedQuery { Type = QueryType.Path };

        result.Source = ParseNodeRefToken(Advance());
        Expect("TO");
        result.Target = ParseNodeRefToken(Advance());

        if (Match("VIA"))
        {
            Advance();
            result.Via = Advance();
        }

        if (Match("MAX"))
        {
            Advance();
            result.MaxHops = ExpectInt("MAX");
        }

        return result;
    }

    private ParsedQuery ParseCountQuery()
    {
        Advance(); // Skip 'COUNT'
        var result = new ParsedQuery { Type = QueryType.Count };

        if (Current() is not null && !Match("WHERE"))
            result.NodeType = Advance();

        if (Match("WHERE"))
        {
            Advance();
            result.ConditionGroups = ParseConditions();
        }

        return result;
    }

    private ParsedQuery ParseAggregationQuery(string aggType)
    {
        var result = new ParsedQuery
        {
            Type = aggType switch
            {
                "SUM" => QueryType.Sum,
                "AVG" => QueryType.Avg,
                "MIN" => QueryType.Min,
                _ => QueryType.Max,
            },
        };

        Advance(); // Skip aggregation keyword

        // type.property
        var typeProp = Advance() ?? "";
        var dotPos = typeProp.IndexOf('.');
        if (dotPos >= 0)
        {
            result.NodeType = typeProp[..dotPos];
            result.Property = typeProp[(dotPos + 1)..];
        }
        else
        {
            result.Property = typeProp;
        }

        if (Match("WHERE"))
        {
            Advance();
            result.ConditionGroups = ParseConditions();
        }

        return result;
    }

    // -------------------------------------------------------------------------
    // Condition Parsing
    // -------------------------------------------------------------------------

    /// <summary>
    /// Parse WHERE conditions with standard precedence (AND binds tighter than
    /// OR): the sequence is split into OR-groups of AND-ed conditions, so
    /// "a AND b OR c" parses as "(a AND b) OR c".
    /// </summary>
    private List<List<Condition>> ParseConditions()
    {
        var groups = new List<List<Condition>> { new() };

        while (true)
        {
            var condition = ParseSingleCondition();
            if (condition is not null)
                groups[^1].Add(condition);

            if (Match("AND"))
            {
                Advance();
                continue;
            }
            if (Match("OR"))
            {
                Advance();
                groups.Add(new List<Condition>());
                continue;
            }
            break;
        }

        groups.RemoveAll(g => g.Count == 0);
        return groups;
    }

    private static List<List<Condition>> MergeConditionSets(
        List<Condition> baseConditions, List<List<Condition>> parsed)
    {
        if (baseConditions.Count == 0)
            return parsed;
        if (parsed.Count == 0)
            return new List<List<Condition>> { baseConditions };
        return parsed
            .Select(group => baseConditions.Concat(group).ToList())
            .ToList();
    }

    private Condition? ParseSingleCondition()
    {
        if (Current() is null)
            return null;

        // Prefix EXISTS / NOT EXISTS
        if (Match("EXISTS"))
        {
            Advance();
            var f = Advance() ?? "";
            return new Condition(f, Operator.Exists);
        }

        if (Match("NOT"))
        {
            Advance();
            if (Match("EXISTS"))
            {
                Advance();
                var f = Advance() ?? "";
                return new Condition(f, Operator.NotExists);
            }
        }

        var field = Advance();
        if (field is null || Keywords.Contains(field.ToUpperInvariant()))
        {
            _pos--;
            return null;
        }

        var opToken = Current();
        if (opToken is null)
            return null;

        var opUpper = opToken.ToUpperInvariant();
        Operator op;

        if (SymbolOperators.TryGetValue(opToken, out var symbolOp))
        {
            Advance();
            op = symbolOp;
        }
        else if (opUpper == "IN")
        {
            Advance();
            op = Operator.In;
        }
        else if (opUpper == "CONTAINS")
        {
            Advance();
            op = Operator.Contains;
        }
        else if (opUpper == "STARTS_WITH")
        {
            Advance();
            op = Operator.StartsWith;
        }
        else if (opUpper == "ENDS_WITH")
        {
            Advance();
            op = Operator.EndsWith;
        }
        else if (opUpper == "MATCHES")
        {
            Advance();
            op = Operator.Matches;
        }
        else if (opUpper == "EXISTS")
        {
            // Postfix EXISTS: "field EXISTS"
            Advance();
            return new Condition(field, Operator.Exists);
        }
        else if (opUpper == "NOT")
        {
            var nxt = Peek(1);
            var nxtUpper = nxt?.ToUpperInvariant() ?? "";
            if (nxtUpper == "EXISTS")
            {
                // Postfix NOT EXISTS: "field NOT EXISTS"
                Advance();
                Advance();
                return new Condition(field, Operator.NotExists);
            }
            if (nxtUpper == "IN")
            {
                Advance();
                Advance();
                op = Operator.NotIn;
            }
            else
            {
                throw new ArgumentException(
                    $"Parse error: expected EXISTS or IN after NOT, got '{nxt}'");
            }
        }
        else
        {
            throw new ArgumentException(
                $"Parse error: unknown operator '{opToken}' in condition");
        }

        var value = ParseValue();
        return new Condition(field, op, value);
    }

    private object? ParseValue()
    {
        var token = Current();
        if (token is null)
            return null;

        // List: (val1, val2, ...)
        if (token == "(")
        {
            Advance();
            var values = new List<string>();
            while (!Match(")"))
            {
                if (Current() is null)
                    throw new ArgumentException("Parse error: unclosed list, expected ')'");
                var val = ParseSingleValue();
                if (val is not null)
                    values.Add(Condition.ValueToString(val));
                if (Match(","))
                    Advance();
            }
            Advance(); // Skip ')'
            return values;
        }

        return ParseSingleValue();
    }

    private object? ParseSingleValue()
    {
        var token = Advance();
        if (token is null)
            return null;

        var upper = token.ToUpperInvariant();

        // Booleans
        if (upper == "TRUE")
            return true;
        if (upper == "FALSE")
            return false;

        // Null
        if (upper is "NULL" or "NONE" or "NIL")
            return null;

        // Numbers
        if (token.Contains('.'))
        {
            if (double.TryParse(token, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                                CultureInfo.InvariantCulture, out var d))
            {
                return d;
            }
        }
        else if (long.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture,
                               out var l))
        {
            return l;
        }

        // String (already unquoted by the tokenizer)
        return token;
    }

    private List<Condition> ParseShorthandConditions()
    {
        var conditions = new List<Condition>();

        while (!Match(")"))
        {
            if (Current() is null)
                throw new ArgumentException("Parse error: unclosed shorthand, expected ')'");
            var field = Advance()!;
            if (Match("="))
            {
                Advance();
                var value = ParseSingleValue();
                conditions.Add(new Condition(field, Operator.Eq, value));
            }
            if (Match(","))
                Advance();
        }

        Advance(); // Skip ')'
        return conditions;
    }

    private List<string> ParseFieldList()
    {
        var fields = new List<string>();
        while (Current() is not null && !Match("LIMIT", "OFFSET", "ORDER"))
        {
            fields.Add(Advance()!);
            if (Match(","))
                Advance();
            else
                break;
        }
        return fields;
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private static NodeRef ParseNodeRefToken(string? token)
    {
        var t = token ?? "";
        if (t.StartsWith(':'))
            t = t[1..];

        var parts = t.Split(':');
        if (parts.Length >= 2)
            return new NodeRef(parts[0], parts[1]);

        throw new ArgumentException(
            $"Invalid node reference: {token}. Expected format: type:id");
    }

    private static Direction DirectionFromArrows(string arrow1, string arrow2)
    {
        if (arrow1 == "->" || arrow2 == "->")
            return Direction.Out;
        if (arrow1 == "<-" || arrow2 == "<-")
            return Direction.In;
        return Direction.Both;
    }
}

// =============================================================================
// Query Engine
// =============================================================================

/// <summary>
/// ISONQL query engine: executes parsed ISONQL queries against an
/// <see cref="ISONGraph"/> instance.
/// </summary>
public sealed class QueryEngine
{
    private readonly ISONQLParser _parser = new();

    public ISONGraph Graph { get; }

    public QueryEngine(ISONGraph graph)
    {
        Graph = graph;
    }

    /// <summary>
    /// Execute an ISONQL query string. Throws <see cref="ArgumentException"/>
    /// on invalid syntax.
    /// </summary>
    public QueryResult Execute(string query)
    {
        var stopwatch = Stopwatch.StartNew();

        ParsedQuery parsed;
        try
        {
            parsed = _parser.Parse(query);
        }
        catch (ArgumentException e)
        {
            throw new ArgumentException($"Parse error: {e.Message}", e);
        }

        var result = ExecuteParsed(parsed);
        stopwatch.Stop();
        result.ExecutionTimeMs = stopwatch.Elapsed.TotalMilliseconds;
        result.Query = query;
        return result;
    }

    private QueryResult ExecuteParsed(ParsedQuery parsed) => parsed.Type switch
    {
        QueryType.Nodes => ExecuteNodes(parsed),
        QueryType.Edges => ExecuteEdges(parsed),
        QueryType.Traverse => ExecuteTraverse(parsed),
        QueryType.Path => ExecutePath(parsed),
        QueryType.Count => ExecuteCount(parsed),
        _ => ExecuteAggregation(parsed),
    };

    // -------------------------------------------------------------------------
    // Condition matching: OR across groups, AND within a group.
    // -------------------------------------------------------------------------

    internal static bool MatchesConditions(IReadOnlyDictionary<string, object?> properties,
                                           List<List<Condition>> conditionGroups)
    {
        if (conditionGroups.Count == 0)
            return true;
        foreach (var group in conditionGroups)
        {
            var allMatch = true;
            foreach (var condition in group)
            {
                if (!condition.Evaluate(properties))
                {
                    allMatch = false;
                    break;
                }
            }
            if (allMatch)
                return true;
        }
        return false;
    }

    // -------------------------------------------------------------------------
    // Query Executors
    // -------------------------------------------------------------------------

    internal QueryResult ExecuteNodes(ParsedQuery parsed)
    {
        var nodes = Graph.Nodes(parsed.NodeType).ToList();

        if (parsed.ConditionGroups.Count > 0)
            nodes = nodes.Where(n => MatchesConditions(n.Properties, parsed.ConditionGroups)).ToList();

        var total = nodes.Count;

        // Sort: nodes missing the field always sort last (in both directions);
        // numeric values sort numerically and before strings, so mixed-type
        // properties never crash the comparison.
        if (parsed.OrderBy is not null)
        {
            var orderBy = parsed.OrderBy;
            var present = nodes.Where(n => n.Properties.ContainsKey(orderBy)).ToList();
            var missing = nodes.Where(n => !n.Properties.ContainsKey(orderBy)).ToList();

            // Sort on the rendered value; PropertyValueComparer already puts
            // numbers before text, and rendering keeps that behaviour now that
            // a property may not be a string.
            var comparer = new PropertyValueComparer();
            present = parsed.OrderDir == SortOrder.Desc
                ? present.OrderByDescending(n => PropertyValue.ValueText(n.Properties[orderBy]), comparer).ToList()
                : present.OrderBy(n => PropertyValue.ValueText(n.Properties[orderBy]), comparer).ToList();

            nodes = present.Concat(missing).ToList();
        }

        // Pagination (LIMIT 0 is honored).
        if (parsed.Offset > 0)
            nodes = nodes.Skip(parsed.Offset).ToList();
        if (parsed.Limit.HasValue)
            nodes = nodes.Take(parsed.Limit.Value).ToList();

        // Format output (RETURN projection keeps only requested fields).
        List<NodeResult> data;
        if (parsed.ReturnFields is { Count: > 0 } fields)
        {
            data = nodes.Select(n =>
            {
                var projected = new Dictionary<string, object?>();
                foreach (var f in fields)
                {
                    if (n.Properties.TryGetValue(f, out var v))
                        projected[f] = v;
                }
                return new NodeResult(n.Type, n.Id, projected);
            }).ToList();
        }
        else
        {
            data = nodes
                .Select(n => new NodeResult(n.Type, n.Id, new Dictionary<string, object?>(n.Properties)))
                .ToList();
        }

        return new QueryResult
        {
            Nodes = data,
            Count = data.Count,
            TotalCount = total,
            QueryType = "NODES",
        };
    }

    private sealed class PropertyValueComparer : IComparer<string>
    {
        public int Compare(string? x, string? y)
        {
            var a = x ?? "";
            var b = y ?? "";
            var aNum = double.TryParse(a, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                                       CultureInfo.InvariantCulture, out var da);
            var bNum = double.TryParse(b, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                                       CultureInfo.InvariantCulture, out var db);
            if (aNum && bNum)
                return da.CompareTo(db);
            if (aNum != bNum)
                return aNum ? -1 : 1; // numbers group before strings
            return string.CompareOrdinal(a, b);
        }
    }

    internal QueryResult ExecuteEdges(ParsedQuery parsed)
    {
        var edges = Graph.Edges(parsed.RelType).ToList();

        if (parsed.ConditionGroups.Count > 0)
            edges = edges.Where(e => MatchesConditions(e.Properties, parsed.ConditionGroups)).ToList();

        var total = edges.Count;

        if (parsed.Limit.HasValue)
            edges = edges.Take(parsed.Limit.Value).ToList();

        var data = edges
            .Select(e => new EdgeResult(e.RelType, e.Source, e.Target,
                                        new Dictionary<string, object?>(e.Properties)))
            .ToList();

        return new QueryResult
        {
            Edges = data,
            Count = data.Count,
            TotalCount = total,
            QueryType = "EDGES",
        };
    }

    private QueryResult ExecuteTraverse(ParsedQuery parsed)
    {
        if (parsed.Start is null)
            throw new ArgumentException("TRAVERSE requires a start node");

        var current = new HashSet<NodeRef> { parsed.Start.Value };
        var visited = new HashSet<NodeRef> { parsed.Start.Value };

        foreach (var step in parsed.Pattern)
        {
            var nextLevel = new HashSet<NodeRef>();
            foreach (var nodeRef in current)
            {
                foreach (var neighbor in Graph.Neighbors(nodeRef, step.RelType, step.Direction))
                {
                    if (!visited.Contains(neighbor) &&
                        (step.TargetType == "*" || neighbor.Type == step.TargetType))
                    {
                        nextLevel.Add(neighbor);
                    }
                }
            }
            visited.UnionWith(nextLevel);
            current = nextLevel;
            if (current.Count == 0)
                break;
        }

        // Apply MAX depth by doing additional hops with the last step's rel/direction.
        if (parsed.MaxDepth is int maxDepth && maxDepth > parsed.Pattern.Count)
        {
            var remainingHops = maxDepth - parsed.Pattern.Count;
            var lastRel = parsed.Pattern.Count > 0 ? parsed.Pattern[^1].RelType : null;
            var lastDir = parsed.Pattern.Count > 0 ? parsed.Pattern[^1].Direction : Direction.Out;

            for (var i = 0; i < remainingHops; i++)
            {
                var nextLevel = new HashSet<NodeRef>();
                foreach (var nodeRef in current.ToList())
                {
                    foreach (var neighbor in Graph.Neighbors(nodeRef, lastRel, lastDir))
                    {
                        if (!visited.Contains(neighbor))
                            nextLevel.Add(neighbor);
                    }
                }
                visited.UnionWith(nextLevel);
                current.UnionWith(nextLevel);
                if (nextLevel.Count == 0)
                    break;
            }
        }

        var refs = current.ToList();
        var total = refs.Count;

        if (parsed.Limit.HasValue)
            refs = refs.Take(parsed.Limit.Value).ToList();

        return new QueryResult
        {
            Refs = refs,
            Count = refs.Count,
            TotalCount = total,
            QueryType = "TRAVERSE",
        };
    }

    private QueryResult ExecutePath(ParsedQuery parsed)
    {
        if (parsed.Source is null || parsed.Target is null)
            throw new ArgumentException("PATH requires source and target nodes");

        var path = Graph.ShortestPath(parsed.Source.Value, parsed.Target.Value,
                                      parsed.Via, parsed.MaxHops);

        var paths = new List<PathResult>();
        if (path is not null)
        {
            var edges = path.Edges
                .Select(e => new EdgeResult(e.RelType, e.Source, e.Target,
                                            new Dictionary<string, object?>(e.Properties)))
                .ToList();
            paths.Add(new PathResult(new List<NodeRef>(path.Nodes), edges, path.Length));
        }

        return new QueryResult
        {
            Paths = paths,
            Count = paths.Count,
            TotalCount = paths.Count,
            QueryType = "PATH",
        };
    }

    internal QueryResult ExecuteCount(ParsedQuery parsed)
    {
        long count = 0;
        foreach (var node in Graph.Nodes(parsed.NodeType))
        {
            if (MatchesConditions(node.Properties, parsed.ConditionGroups))
                count++;
        }

        return new QueryResult
        {
            CountValue = count,
            Count = 1,
            TotalCount = (int)count,
            QueryType = "COUNT",
        };
    }

    private QueryResult ExecuteAggregation(ParsedQuery parsed)
    {
        if (parsed.Property is null)
            throw new ArgumentException("Aggregation requires a property name");

        var values = new List<double>();
        foreach (var node in Graph.Nodes(parsed.NodeType))
        {
            if (!MatchesConditions(node.Properties, parsed.ConditionGroups))
                continue;
            if (node.Properties.TryGetValue(parsed.Property, out var raw) &&
                PropertyValue.AsDouble(raw) is double v)
            {
                values.Add(v);
            }
        }

        var queryType = parsed.Type switch
        {
            QueryType.Sum => "SUM",
            QueryType.Avg => "AVG",
            QueryType.Min => "MIN",
            _ => "MAX",
        };

        if (values.Count == 0)
        {
            return new QueryResult
            {
                Value = null,
                Count = 0,
                TotalCount = 0,
                QueryType = queryType,
            };
        }

        double result = parsed.Type switch
        {
            QueryType.Sum => values.Sum(),
            QueryType.Avg => values.Sum() / values.Count,
            QueryType.Min => values.Min(),
            _ => values.Max(),
        };

        return new QueryResult
        {
            Value = result,
            Count = 1,
            TotalCount = values.Count,
            QueryType = queryType,
        };
    }

    // -------------------------------------------------------------------------
    // Fluent API
    // -------------------------------------------------------------------------

    /// <summary>Start a fluent query for nodes of the given type.</summary>
    public QueryBuilder Match(string nodeType) => new(this, nodeType);

    /// <summary>Start a fluent query for edges.</summary>
    public EdgeQueryBuilder MatchEdges(string? relType = null) => new(this, relType);
}

// =============================================================================
// Fluent Query Builders
// =============================================================================

/// <summary>
/// Fluent API for building node queries programmatically:
///     engine.Match("person").Where("age", ">", 25)
///           .OrderBy("age", "DESC").Limit(10).Execute()
/// </summary>
public sealed class QueryBuilder
{
    private static readonly Dictionary<string, Operator> OpMap = new(StringComparer.Ordinal)
    {
        ["="] = Operator.Eq,
        ["=="] = Operator.Eq,
        ["!="] = Operator.Ne,
        ["<>"] = Operator.Ne,
        [">"] = Operator.Gt,
        [">="] = Operator.Ge,
        ["<"] = Operator.Lt,
        ["<="] = Operator.Le,
        ["IN"] = Operator.In,
        ["NOT IN"] = Operator.NotIn,
        ["CONTAINS"] = Operator.Contains,
        ["STARTS_WITH"] = Operator.StartsWith,
        ["ENDS_WITH"] = Operator.EndsWith,
        ["MATCHES"] = Operator.Matches,
    };

    private readonly QueryEngine _engine;
    private readonly string _nodeType;
    private readonly List<Condition> _conditions = new();
    private string? _orderBy;
    private SortOrder _orderDir = SortOrder.Asc;
    private int? _limit;
    private int _offset;
    private List<string>? _fields;

    internal QueryBuilder(QueryEngine engine, string nodeType)
    {
        _engine = engine;
        _nodeType = nodeType;
    }

    internal static object? NormalizeValue(object? value) => value switch
    {
        null => null,
        bool b => b,
        sbyte or byte or short or ushort or int or uint or long =>
            Convert.ToInt64(value, CultureInfo.InvariantCulture),
        float or double or decimal =>
            Convert.ToDouble(value, CultureInfo.InvariantCulture),
        string s => s,
        List<string> list => list,
        IEnumerable<string> seq => seq.ToList(),
        System.Collections.IEnumerable seq => seq.Cast<object?>()
            .Select(Condition.ValueToString).ToList(),
        _ => value.ToString(),
    };

    /// <summary>
    /// Add a WHERE condition. Unknown operator strings throw
    /// <see cref="ArgumentException"/> instead of silently becoming '='.
    /// </summary>
    public QueryBuilder Where(string field, string op, object? value)
    {
        if (!OpMap.TryGetValue(op.ToUpperInvariant(), out var opEnum) &&
            !OpMap.TryGetValue(op, out opEnum))
        {
            throw new ArgumentException(
                $"Unknown operator: '{op}'. Supported: {string.Join(", ", OpMap.Keys.OrderBy(k => k, StringComparer.Ordinal))}");
        }
        _conditions.Add(new Condition(field, opEnum, NormalizeValue(value)));
        return this;
    }

    /// <summary>Add an EXISTS condition.</summary>
    public QueryBuilder WhereExists(string field)
    {
        _conditions.Add(new Condition(field, Operator.Exists));
        return this;
    }

    /// <summary>Add a NOT EXISTS condition.</summary>
    public QueryBuilder WhereNotExists(string field)
    {
        _conditions.Add(new Condition(field, Operator.NotExists));
        return this;
    }

    /// <summary>Set the ORDER BY clause.</summary>
    public QueryBuilder OrderBy(string field, string direction = "ASC")
    {
        _orderBy = field;
        _orderDir = string.Equals(direction, "DESC", StringComparison.OrdinalIgnoreCase)
            ? SortOrder.Desc
            : SortOrder.Asc;
        return this;
    }

    /// <summary>Set the LIMIT (0 is honored and returns no rows).</summary>
    public QueryBuilder Limit(int n)
    {
        _limit = n;
        return this;
    }

    /// <summary>Set the OFFSET for pagination.</summary>
    public QueryBuilder Offset(int n)
    {
        _offset = n;
        return this;
    }

    /// <summary>Set the fields to return (projection).</summary>
    public QueryBuilder ReturnFields(params string[] fields)
    {
        _fields = fields.ToList();
        return this;
    }

    private ParsedQuery BuildParsed() => new()
    {
        Type = QueryType.Nodes,
        NodeType = _nodeType,
        ConditionGroups = _conditions.Count > 0
            ? new List<List<Condition>> { new(_conditions) }
            : new List<List<Condition>>(),
        OrderBy = _orderBy,
        OrderDir = _orderDir,
        Limit = _limit,
        Offset = _offset,
        ReturnFields = _fields,
    };

    /// <summary>Execute the built query.</summary>
    public QueryResult Execute()
    {
        var stopwatch = Stopwatch.StartNew();
        var result = _engine.ExecuteNodes(BuildParsed());
        stopwatch.Stop();
        result.ExecutionTimeMs = stopwatch.Elapsed.TotalMilliseconds;

        var queryStr = new StringBuilder("NODES " + _nodeType);
        if (_conditions.Count > 0)
            queryStr.Append(" WHERE ").Append(string.Join(" AND ", _conditions));
        if (_orderBy is not null)
            queryStr.Append($" ORDER BY {_orderBy} {(_orderDir == SortOrder.Desc ? "DESC" : "ASC")}");
        if (_limit.HasValue)
            queryStr.Append($" LIMIT {_limit.Value}");
        if (_offset > 0)
            queryStr.Append($" OFFSET {_offset}");

        result.Query = queryStr.ToString();
        return result;
    }

    /// <summary>Execute a count query and return the count.</summary>
    public long Count()
    {
        var parsed = new ParsedQuery
        {
            Type = QueryType.Count,
            NodeType = _nodeType,
            ConditionGroups = _conditions.Count > 0
                ? new List<List<Condition>> { new(_conditions) }
                : new List<List<Condition>>(),
        };
        return _engine.ExecuteCount(parsed).CountValue ?? 0;
    }
}

/// <summary>
/// Fluent API for building edge queries:
///     engine.MatchEdges("KNOWS").Where("since", ">", 2020).Limit(10).Execute()
/// </summary>
public sealed class EdgeQueryBuilder
{
    private static readonly Dictionary<string, Operator> OpMap = new(StringComparer.Ordinal)
    {
        ["="] = Operator.Eq,
        ["=="] = Operator.Eq,
        ["!="] = Operator.Ne,
        ["<>"] = Operator.Ne,
        [">"] = Operator.Gt,
        [">="] = Operator.Ge,
        ["<"] = Operator.Lt,
        ["<="] = Operator.Le,
    };

    private readonly QueryEngine _engine;
    private readonly string? _relType;
    private readonly List<Condition> _conditions = new();
    private int? _limit;

    internal EdgeQueryBuilder(QueryEngine engine, string? relType)
    {
        _engine = engine;
        _relType = relType;
    }

    /// <summary>
    /// Add a WHERE condition. Unknown operator strings throw
    /// <see cref="ArgumentException"/>.
    /// </summary>
    public EdgeQueryBuilder Where(string field, string op, object? value)
    {
        if (!OpMap.TryGetValue(op, out var opEnum))
        {
            throw new ArgumentException(
                $"Unknown operator: '{op}'. Supported: {string.Join(", ", OpMap.Keys.OrderBy(k => k, StringComparer.Ordinal))}");
        }
        _conditions.Add(new Condition(field, opEnum, QueryBuilder.NormalizeValue(value)));
        return this;
    }

    /// <summary>Set the LIMIT.</summary>
    public EdgeQueryBuilder Limit(int n)
    {
        _limit = n;
        return this;
    }

    /// <summary>Execute the built query.</summary>
    public QueryResult Execute()
    {
        var parsed = new ParsedQuery
        {
            Type = QueryType.Edges,
            RelType = _relType,
            ConditionGroups = _conditions.Count > 0
                ? new List<List<Condition>> { new(_conditions) }
                : new List<List<Condition>>(),
            Limit = _limit,
        };

        var stopwatch = Stopwatch.StartNew();
        var result = _engine.ExecuteEdges(parsed);
        stopwatch.Stop();
        result.ExecutionTimeMs = stopwatch.Elapsed.TotalMilliseconds;

        var queryStr = "EDGES" + (_relType is null ? "" : " " + _relType);
        if (_conditions.Count > 0)
            queryStr += " WHERE " + string.Join(" AND ", _conditions);
        result.Query = queryStr;
        return result;
    }
}
