// ISONGraph Schema Validation (Graphantic)
//
// Graph schema validation with:
// - Node type schemas with property validation
// - Edge type schemas with reference integrity
// - Graph-level constraints (cycles, connectivity, cardinality)
// - Fluent API for schema definition
//
// Example:
//     var person = new NodeType("person")
//         .Id(new IntField())
//         .Field("name", new StringField().Required().Max(100))
//         .Field("age", new IntField().Min(0).Max(150));
//
//     var knows = new EdgeType("KNOWS")
//         .FromNode(person).ToNode(person).NoSelfLoop().Unique();
//
//     var schema = new GraphSchema("social")
//         .NodeTypes(person)
//         .EdgeTypes(knows)
//         .NoOrphans();
//
//     var result = schema.Validate(graph);
//
// Author: Mahesh Vaikri

using System.Globalization;
using System.Text.RegularExpressions;

namespace IsonGraph;

// =============================================================================
// Enums
// =============================================================================

/// <summary>Edge cardinality constraints.</summary>
public enum Cardinality
{
    OneToOne,   // 1:1
    OneToMany,  // 1:N
    ManyToOne,  // N:1
    ManyToMany, // N:N
}

/// <summary>Validation error codes.</summary>
public enum ErrorCode
{
    // Field errors
    RequiredField,
    InvalidType,
    MinValue,
    MaxValue,
    MinLength,
    MaxLength,
    PatternMismatch,
    InvalidEmail,
    InvalidEnum,

    // Reference errors
    RefNotFound,
    RefWrongType,

    // Edge errors
    SelfLoop,
    DuplicateEdge,
    CardinalityViolation,
    InvalidSourceType,
    InvalidTargetType,

    // Graph errors
    CycleDetected,
    NotConnected,
    OrphanNode,
    MaxDepthExceeded,
}

// =============================================================================
// Validation Result
// =============================================================================

/// <summary>Represents a single validation error.</summary>
public sealed class ValidationError
{
    public ErrorCode Code { get; }
    public string Message { get; }
    public string Location { get; set; }
    public Dictionary<string, object?> Context { get; }

    public ValidationError(ErrorCode code, string message, string location = "",
                           Dictionary<string, object?>? context = null)
    {
        Code = code;
        Message = message;
        Location = location;
        Context = context ?? new Dictionary<string, object?>();
    }

    public override string ToString()
    {
        var loc = Location.Length > 0 ? $"[{Location}] " : "";
        return $"{loc}{Code}: {Message}";
    }
}

/// <summary>Result of a schema validation.</summary>
public sealed class ValidationResult
{
    public bool Valid { get; private set; } = true;
    public List<ValidationError> Errors { get; } = new();
    public List<ValidationError> Warnings { get; } = new();

    /// <summary>Add a validation error (marks the result invalid).</summary>
    public void AddError(ValidationError error)
    {
        Errors.Add(error);
        Valid = false;
    }

    /// <summary>Add a validation warning.</summary>
    public void AddWarning(ValidationError warning) => Warnings.Add(warning);

    /// <summary>Merge another result into this one.</summary>
    public void Merge(ValidationResult other)
    {
        Errors.AddRange(other.Errors);
        Warnings.AddRange(other.Warnings);
        if (!other.Valid)
            Valid = false;
    }

    public override string ToString() =>
        Valid ? "ValidationResult(VALID)" : $"ValidationResult(INVALID ({Errors.Count} errors))";
}

// =============================================================================
// Field Validators
// =============================================================================

/// <summary>Base class for field type validators.</summary>
public abstract class FieldValidator
{
    private protected bool RequiredFlag;
    private protected string? DefaultString;
    private protected bool HasDefaultFlag;

    internal bool HasDefault => HasDefaultFlag;
    internal string? DefaultValue => DefaultString;

    /// <summary>Validate a value (null means the field is missing).</summary>
    public abstract ValidationResult Validate(string? value, string fieldName);

    /// <summary>
    /// Handle a missing value: returns a result (with a REQUIRED_FIELD error
    /// when required) when the value is null, or null to continue validating.
    /// </summary>
    protected ValidationResult? CheckRequired(string? value, string fieldName)
    {
        if (value is null)
        {
            var result = new ValidationResult();
            if (RequiredFlag)
            {
                result.AddError(new ValidationError(
                    ErrorCode.RequiredField, $"Field '{fieldName}' is required", fieldName));
            }
            return result;
        }
        return null;
    }
}

/// <summary>String field validator.</summary>
public sealed class StringField : FieldValidator
{
    private static readonly Regex EmailPattern = new(
        @"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", RegexOptions.CultureInvariant);

    private int? _minLength;
    private int? _maxLength;
    private Regex? _pattern;
    private string? _patternSource;
    private bool _email;
    private List<string>? _enum;

    public StringField Required() { RequiredFlag = true; return this; }
    public StringField Default(string value) { DefaultString = value; HasDefaultFlag = true; return this; }
    public StringField Min(int length) { _minLength = length; return this; }
    public StringField Max(int length) { _maxLength = length; return this; }

    public StringField Pattern(string regex)
    {
        _pattern = new Regex(regex, RegexOptions.CultureInvariant);
        _patternSource = regex;
        return this;
    }

    public StringField Email() { _email = true; return this; }
    public StringField Enum(params string[] values) { _enum = values.ToList(); return this; }

    public override ValidationResult Validate(string? value, string fieldName)
    {
        var requiredResult = CheckRequired(value, fieldName);
        if (requiredResult is not null)
            return requiredResult;

        var result = new ValidationResult();
        var val = value!;

        if (_minLength is int min && val.Length < min)
        {
            result.AddError(new ValidationError(
                ErrorCode.MinLength,
                $"Field '{fieldName}' must be at least {min} characters",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["min_length"] = min.ToString(CultureInfo.InvariantCulture),
                    ["actual"] = val.Length.ToString(CultureInfo.InvariantCulture),
                }));
        }

        if (_maxLength is int max && val.Length > max)
        {
            result.AddError(new ValidationError(
                ErrorCode.MaxLength,
                $"Field '{fieldName}' must be at most {max} characters",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["max_length"] = max.ToString(CultureInfo.InvariantCulture),
                    ["actual"] = val.Length.ToString(CultureInfo.InvariantCulture),
                }));
        }

        if (_pattern is not null)
        {
            // Python re.match semantics: the match must start at position 0.
            var m = _pattern.Match(val);
            if (!m.Success || m.Index != 0)
            {
                result.AddError(new ValidationError(
                    ErrorCode.PatternMismatch,
                    $"Field '{fieldName}' does not match pattern",
                    fieldName,
                    new Dictionary<string, object?> { ["pattern"] = _patternSource ?? "" }));
            }
        }

        if (_email && !EmailPattern.IsMatch(val))
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidEmail,
                $"Field '{fieldName}' is not a valid email address",
                fieldName));
        }

        if (_enum is not null && !_enum.Contains(val))
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidEnum,
                $"Field '{fieldName}' must be one of: {string.Join(", ", _enum)}",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["allowed"] = string.Join(", ", _enum),
                    ["actual"] = val,
                }));
        }

        return result;
    }
}

/// <summary>Integer field validator.</summary>
public sealed class IntField : FieldValidator
{
    private long? _min;
    private long? _max;

    public IntField Required() { RequiredFlag = true; return this; }

    public IntField Default(long value)
    {
        DefaultString = value.ToString(CultureInfo.InvariantCulture);
        HasDefaultFlag = true;
        return this;
    }

    public IntField Min(long value) { _min = value; return this; }
    public IntField Max(long value) { _max = value; return this; }
    public IntField Range(long minValue, long maxValue) { _min = minValue; _max = maxValue; return this; }

    public override ValidationResult Validate(string? value, string fieldName)
    {
        var requiredResult = CheckRequired(value, fieldName);
        if (requiredResult is not null)
            return requiredResult;

        var result = new ValidationResult();

        if (!long.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed))
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidType,
                $"Field '{fieldName}' must be an integer, got '{value}'",
                fieldName));
            return result;
        }

        if (_min is long min && parsed < min)
        {
            result.AddError(new ValidationError(
                ErrorCode.MinValue,
                $"Field '{fieldName}' must be at least {min}",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["min"] = min.ToString(CultureInfo.InvariantCulture),
                    ["actual"] = parsed.ToString(CultureInfo.InvariantCulture),
                }));
        }

        if (_max is long max && parsed > max)
        {
            result.AddError(new ValidationError(
                ErrorCode.MaxValue,
                $"Field '{fieldName}' must be at most {max}",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["max"] = max.ToString(CultureInfo.InvariantCulture),
                    ["actual"] = parsed.ToString(CultureInfo.InvariantCulture),
                }));
        }

        return result;
    }
}

/// <summary>Float field validator.</summary>
public sealed class FloatField : FieldValidator
{
    private double? _min;
    private double? _max;

    public FloatField Required() { RequiredFlag = true; return this; }

    public FloatField Default(double value)
    {
        DefaultString = value.ToString(CultureInfo.InvariantCulture);
        HasDefaultFlag = true;
        return this;
    }

    public FloatField Min(double value) { _min = value; return this; }
    public FloatField Max(double value) { _max = value; return this; }
    public FloatField Range(double minValue, double maxValue) { _min = minValue; _max = maxValue; return this; }

    public override ValidationResult Validate(string? value, string fieldName)
    {
        var requiredResult = CheckRequired(value, fieldName);
        if (requiredResult is not null)
            return requiredResult;

        var result = new ValidationResult();

        if (!double.TryParse(value, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                             CultureInfo.InvariantCulture, out var parsed))
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidType,
                $"Field '{fieldName}' must be a number, got '{value}'",
                fieldName));
            return result;
        }

        if (_min is double min && parsed < min)
        {
            result.AddError(new ValidationError(
                ErrorCode.MinValue,
                $"Field '{fieldName}' must be at least {min.ToString(CultureInfo.InvariantCulture)}",
                fieldName));
        }

        if (_max is double max && parsed > max)
        {
            result.AddError(new ValidationError(
                ErrorCode.MaxValue,
                $"Field '{fieldName}' must be at most {max.ToString(CultureInfo.InvariantCulture)}",
                fieldName));
        }

        return result;
    }
}

/// <summary>Boolean field validator.</summary>
public sealed class BoolField : FieldValidator
{
    private static readonly HashSet<string> BoolValues = new(StringComparer.OrdinalIgnoreCase)
    {
        "true", "false", "1", "0", "yes", "no",
    };

    public BoolField Required() { RequiredFlag = true; return this; }

    public BoolField Default(bool value)
    {
        DefaultString = value ? "true" : "false";
        HasDefaultFlag = true;
        return this;
    }

    public override ValidationResult Validate(string? value, string fieldName)
    {
        var requiredResult = CheckRequired(value, fieldName);
        if (requiredResult is not null)
            return requiredResult;

        var result = new ValidationResult();

        if (!BoolValues.Contains(value!))
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidType,
                $"Field '{fieldName}' must be a boolean, got '{value}'",
                fieldName));
        }

        return result;
    }
}

/// <summary>Reference field validator (values in ":type:id" format).</summary>
public sealed class RefField : FieldValidator
{
    private string? _nodeType;

    public RefField(string? nodeType = null)
    {
        _nodeType = nodeType;
    }

    public RefField Required() { RequiredFlag = true; return this; }
    public RefField Default(string value) { DefaultString = value; HasDefaultFlag = true; return this; }

    /// <summary>Specify the required target node type.</summary>
    public RefField To(string nodeType) { _nodeType = nodeType; return this; }

    public override ValidationResult Validate(string? value, string fieldName)
    {
        var requiredResult = CheckRequired(value, fieldName);
        if (requiredResult is not null)
            return requiredResult;

        var result = new ValidationResult();
        var val = value!;

        var secondColon = val.Length > 0 && val[0] == ':' ? val.IndexOf(':', 1) : -1;
        if (secondColon < 0)
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidType,
                $"Field '{fieldName}' must be a node reference (format :type:id)",
                fieldName));
            return result;
        }

        var refType = val[1..secondColon];
        if (_nodeType is not null && refType != _nodeType)
        {
            result.AddError(new ValidationError(
                ErrorCode.RefWrongType,
                $"Field '{fieldName}' must reference '{_nodeType}', got '{refType}'",
                fieldName,
                new Dictionary<string, object?>
                {
                    ["expected"] = _nodeType,
                    ["actual"] = refType,
                }));
        }

        return result;
    }
}

// =============================================================================
// Node Type Schema
// =============================================================================

/// <summary>
/// Schema definition for a node type:
///     new NodeType("person")
///         .Id(new IntField())
///         .Field("name", new StringField().Required())
///         .Field("age", new IntField().Min(0))
/// </summary>
public sealed class NodeType
{
    public string Name { get; }

    private FieldValidator? _idType;
    private readonly List<(string Name, FieldValidator Validator)> _fields = new();
    private readonly List<Func<Node, ValidationError?>> _constraints = new();

    public NodeType(string name)
    {
        Name = name;
    }

    /// <summary>Define the ID field validator.</summary>
    public NodeType Id(FieldValidator fieldType)
    {
        _idType = fieldType;
        return this;
    }

    /// <summary>Add a field definition.</summary>
    public NodeType Field(string name, FieldValidator fieldType)
    {
        _fields.Add((name, fieldType));
        return this;
    }

    /// <summary>Add a custom constraint.</summary>
    public NodeType Constraint(Func<Node, ValidationError?> fn)
    {
        _constraints.Add(fn);
        return this;
    }

    /// <summary>
    /// Validate a single node. Declared defaults are applied to missing
    /// fields (written into the node's properties) before validating.
    /// </summary>
    public ValidationResult ValidateNode(Node node)
    {
        var result = new ValidationResult();
        var location = $"nodes.{Name}[{node.Id}]";

        // Validate ID
        if (_idType is not null)
        {
            var idResult = _idType.Validate(node.Id, "id");
            foreach (var error in idResult.Errors)
                error.Location = location;
            result.Merge(idResult);
        }

        // Validate fields
        foreach (var (fieldName, fieldType) in _fields)
        {
            node.Properties.TryGetValue(fieldName, out var value);
            if (value is null && fieldType.HasDefault)
            {
                value = fieldType.DefaultValue;
                node.Properties[fieldName] = value!;
            }
            // Validated against the rendered text so a schema accepts exactly
            // what it did when properties were strings. Type-aware validation
            // is a separate change.
            var fieldResult = fieldType.Validate(value is null ? null : PropertyValue.ValueText(value), fieldName);
            foreach (var error in fieldResult.Errors)
                error.Location = $"{location}.{fieldName}";
            result.Merge(fieldResult);
        }

        // Custom constraints
        foreach (var constraint in _constraints)
        {
            var error = constraint(node);
            if (error is not null)
            {
                error.Location = location;
                result.AddError(error);
            }
        }

        return result;
    }

    public override string ToString() => $"NodeType({Name})";
}

// =============================================================================
// Edge Type Schema
// =============================================================================

/// <summary>
/// Schema definition for an edge/relationship type:
///     new EdgeType("KNOWS")
///         .FromNode(person).ToNode(person)
///         .Field("since", new IntField())
///         .NoSelfLoop().Unique()
/// </summary>
public sealed class EdgeType
{
    public string Name { get; }

    private string? _sourceType;
    private string? _targetType;
    private readonly List<(string Name, FieldValidator Validator)> _fields = new();
    private readonly List<Func<Edge, ValidationError?>> _constraints = new();

    internal bool IsUnique { get; private set; }
    internal bool IsAcyclic { get; private set; }
    internal bool IsBidirectional { get; private set; }
    internal Cardinality? CardinalityConstraint { get; private set; }
    private bool _noSelfLoop;

    public EdgeType(string name)
    {
        Name = name;
    }

    /// <summary>Set the source node type.</summary>
    public EdgeType FromNode(NodeType nodeType) { _sourceType = nodeType.Name; return this; }

    /// <summary>Set the source node type by name.</summary>
    public EdgeType FromNode(string nodeType) { _sourceType = nodeType; return this; }

    /// <summary>Set the target node type.</summary>
    public EdgeType ToNode(NodeType nodeType) { _targetType = nodeType.Name; return this; }

    /// <summary>Set the target node type by name.</summary>
    public EdgeType ToNode(string nodeType) { _targetType = nodeType; return this; }

    /// <summary>Add an edge property field.</summary>
    public EdgeType Field(string name, FieldValidator fieldType)
    {
        _fields.Add((name, fieldType));
        return this;
    }

    /// <summary>Disallow self-referential edges.</summary>
    public EdgeType NoSelfLoop() { _noSelfLoop = true; return this; }

    /// <summary>Require unique source-target pairs.</summary>
    public EdgeType Unique() { IsUnique = true; return this; }

    /// <summary>Enforce a DAG (no cycles via this edge type only).</summary>
    public EdgeType Acyclic() { IsAcyclic = true; return this; }

    /// <summary>Require symmetric edges (if A -&gt; B exists, B -&gt; A must too).</summary>
    public EdgeType Bidirectional() { IsBidirectional = true; return this; }

    /// <summary>Set a cardinality constraint.</summary>
    public EdgeType Cardinality(Cardinality cardinality)
    {
        CardinalityConstraint = cardinality;
        return this;
    }

    /// <summary>Add a custom constraint.</summary>
    public EdgeType Constraint(Func<Edge, ValidationError?> fn)
    {
        _constraints.Add(fn);
        return this;
    }

    /// <summary>Validate a single edge (defaults applied to missing fields).</summary>
    public ValidationResult ValidateEdge(Edge edge, ISONGraph graph)
    {
        var result = new ValidationResult();
        var location = $"edges.{Name}[{edge.Source} -> {edge.Target}]";

        if (_sourceType is not null && edge.Source.Type != _sourceType)
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidSourceType,
                $"Edge source must be '{_sourceType}', got '{edge.Source.Type}'",
                location,
                new Dictionary<string, object?>
                {
                    ["expected"] = _sourceType,
                    ["actual"] = edge.Source.Type,
                }));
        }

        if (_targetType is not null && edge.Target.Type != _targetType)
        {
            result.AddError(new ValidationError(
                ErrorCode.InvalidTargetType,
                $"Edge target must be '{_targetType}', got '{edge.Target.Type}'",
                location,
                new Dictionary<string, object?>
                {
                    ["expected"] = _targetType,
                    ["actual"] = edge.Target.Type,
                }));
        }

        if (!graph.HasNode(edge.Source))
        {
            result.AddError(new ValidationError(
                ErrorCode.RefNotFound,
                $"Source node {edge.Source} does not exist",
                location));
        }

        if (!graph.HasNode(edge.Target))
        {
            result.AddError(new ValidationError(
                ErrorCode.RefNotFound,
                $"Target node {edge.Target} does not exist",
                location));
        }

        if (_noSelfLoop && edge.Source == edge.Target)
        {
            result.AddError(new ValidationError(
                ErrorCode.SelfLoop,
                $"Self-loop not allowed: {edge.Source}",
                location));
        }

        foreach (var (fieldName, fieldType) in _fields)
        {
            edge.Properties.TryGetValue(fieldName, out var value);
            if (value is null && fieldType.HasDefault)
            {
                value = fieldType.DefaultValue;
                edge.Properties[fieldName] = value!;
            }
            // Validated against the rendered text so a schema accepts exactly
            // what it did when properties were strings. Type-aware validation
            // is a separate change.
            var fieldResult = fieldType.Validate(value is null ? null : PropertyValue.ValueText(value), fieldName);
            foreach (var error in fieldResult.Errors)
                error.Location = $"{location}.{fieldName}";
            result.Merge(fieldResult);
        }

        foreach (var constraint in _constraints)
        {
            var error = constraint(edge);
            if (error is not null)
            {
                error.Location = location;
                result.AddError(error);
            }
        }

        return result;
    }

    public override string ToString() => $"EdgeType({Name})";
}

// =============================================================================
// Graph Schema
// =============================================================================

/// <summary>
/// Complete graph schema definition:
///     new GraphSchema("social")
///         .NodeTypes(person, company)
///         .EdgeTypes(knows, worksAt)
///         .Connected()
///         .NoOrphans()
/// </summary>
public sealed class GraphSchema
{
    public string Name { get; }

    private readonly List<NodeType> _nodeTypes = new();
    private readonly Dictionary<string, NodeType> _nodeTypesByName = new();
    private readonly List<EdgeType> _edgeTypes = new();
    private bool _requireConnected;
    private bool _requireNoOrphans;
    private int? _maxDepth;
    private readonly List<Func<ISONGraph, IEnumerable<ValidationError>>> _constraints = new();

    public GraphSchema(string name)
    {
        Name = name;
    }

    /// <summary>Add node type schemas.</summary>
    public GraphSchema NodeTypes(params NodeType[] types)
    {
        foreach (var nodeType in types)
        {
            _nodeTypes.Add(nodeType);
            _nodeTypesByName[nodeType.Name] = nodeType;
        }
        return this;
    }

    /// <summary>Add edge type schemas.</summary>
    public GraphSchema EdgeTypes(params EdgeType[] types)
    {
        _edgeTypes.AddRange(types);
        return this;
    }

    /// <summary>Require the graph to be connected.</summary>
    public GraphSchema Connected() { _requireConnected = true; return this; }

    /// <summary>Require every node to have at least one edge.</summary>
    public GraphSchema NoOrphans() { _requireNoOrphans = true; return this; }

    /// <summary>Set the maximum graph depth.</summary>
    public GraphSchema MaxDepth(int depth) { _maxDepth = depth; return this; }

    /// <summary>The configured maximum graph depth, if any.</summary>
    public int? MaxDepthValue => _maxDepth;

    /// <summary>Add a custom graph-level constraint.</summary>
    public GraphSchema Constraint(Func<ISONGraph, IEnumerable<ValidationError>> fn)
    {
        _constraints.Add(fn);
        return this;
    }

    /// <summary>Validate a graph against this schema.</summary>
    public ValidationResult Validate(ISONGraph graph)
    {
        var result = new ValidationResult();

        // Validate nodes
        foreach (var node in graph.Nodes())
        {
            if (_nodeTypesByName.TryGetValue(node.Type, out var nodeType))
                result.Merge(nodeType.ValidateNode(node));
        }

        // Validate edges
        foreach (var edgeType in _edgeTypes)
        {
            var relType = edgeType.Name;
            var edgesOfType = graph.Edges(relType).ToList();

            // Check uniqueness
            if (edgeType.IsUnique)
            {
                var seen = new HashSet<(NodeRef, NodeRef)>();
                foreach (var edge in edgesOfType)
                {
                    if (!seen.Add((edge.Source, edge.Target)))
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.DuplicateEdge,
                            $"Duplicate edge: {edge.Source} -> {edge.Target}",
                            $"edges.{relType}"));
                    }
                }
            }

            // Check cardinality
            if (edgeType.CardinalityConstraint is Cardinality cardinality)
                CheckCardinality(edgesOfType, cardinality, relType, result);

            // Check acyclic: only edges of THIS relationship type may not form a cycle
            if (edgeType.IsAcyclic && graph.HasCycle(relType))
            {
                result.AddError(new ValidationError(
                    ErrorCode.CycleDetected,
                    $"Cycle detected in '{relType}' edges (must be DAG)",
                    $"edges.{relType}"));
            }

            // Check bidirectional
            if (edgeType.IsBidirectional)
            {
                foreach (var edge in edgesOfType)
                {
                    if (!graph.HasEdge(relType, edge.Target, edge.Source))
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.DuplicateEdge,
                            $"Missing reverse edge for bidirectional: {edge.Target} -> {edge.Source}",
                            $"edges.{relType}"));
                    }
                }
            }

            // Validate individual edges
            foreach (var edge in edgesOfType)
                result.Merge(edgeType.ValidateEdge(edge, graph));
        }

        // Graph-level constraints
        if (_requireConnected && !graph.IsConnected())
        {
            result.AddError(new ValidationError(
                ErrorCode.NotConnected,
                "Graph is not connected (some nodes are unreachable)",
                "graph"));
        }

        if (_requireNoOrphans)
        {
            foreach (var node in graph.Nodes())
            {
                if (graph.Degree(node.Ref) == 0)
                {
                    result.AddError(new ValidationError(
                        ErrorCode.OrphanNode,
                        $"Orphan node (no edges): :{node.Type}:{node.Id}",
                        $"nodes.{node.Type}[{node.Id}]"));
                }
            }
        }

        // Custom constraints
        foreach (var constraint in _constraints)
        {
            foreach (var error in constraint(graph))
                result.AddError(error);
        }

        return result;
    }

    private static void CheckCardinality(List<Edge> edges, Cardinality cardinality,
                                         string relType, ValidationResult result)
    {
        var location = $"edges.{relType}";
        var sourceCounts = new Dictionary<NodeRef, int>();
        var targetCounts = new Dictionary<NodeRef, int>();

        foreach (var edge in edges)
        {
            sourceCounts[edge.Source] = sourceCounts.GetValueOrDefault(edge.Source) + 1;
            targetCounts[edge.Target] = targetCounts.GetValueOrDefault(edge.Target) + 1;
        }

        switch (cardinality)
        {
            case IsonGraph.Cardinality.OneToOne:
                foreach (var (source, count) in sourceCounts)
                {
                    if (count > 1)
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.CardinalityViolation,
                            $"ONE_TO_ONE violation: {source} has {count} outgoing edges",
                            location));
                    }
                }
                foreach (var (target, count) in targetCounts)
                {
                    if (count > 1)
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.CardinalityViolation,
                            $"ONE_TO_ONE violation: {target} has {count} incoming edges",
                            location));
                    }
                }
                break;

            case IsonGraph.Cardinality.OneToMany:
                foreach (var (target, count) in targetCounts)
                {
                    if (count > 1)
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.CardinalityViolation,
                            $"ONE_TO_MANY violation: {target} has {count} incoming edges",
                            location));
                    }
                }
                break;

            case IsonGraph.Cardinality.ManyToOne:
                foreach (var (source, count) in sourceCounts)
                {
                    if (count > 1)
                    {
                        result.AddError(new ValidationError(
                            ErrorCode.CardinalityViolation,
                            $"MANY_TO_ONE violation: {source} has {count} outgoing edges",
                            location));
                    }
                }
                break;

            case IsonGraph.Cardinality.ManyToMany:
                // No restrictions
                break;
        }
    }

    public override string ToString() => $"GraphSchema({Name})";
}
