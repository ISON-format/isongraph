// Tests for schema validation (Graphantic): field validators, defaults,
// node/edge type schemas, cardinality, acyclic-per-rel-type, and graph-level
// constraints.

using Xunit;

namespace IsonGraph.Tests;

public class FieldValidatorTests
{
    [Fact]
    public void StringRequired()
    {
        var field = new StringField().Required();
        Assert.False(field.Validate(null, "name").Valid);
        Assert.True(field.Validate("Alice", "name").Valid);
    }

    [Fact]
    public void StringOptionalMissingIsValid()
    {
        Assert.True(new StringField().Validate(null, "name").Valid);
    }

    [Fact]
    public void StringMinMaxLength()
    {
        var field = new StringField().Min(3).Max(5);
        Assert.False(field.Validate("ab", "name").Valid);
        Assert.True(field.Validate("abc", "name").Valid);
        Assert.True(field.Validate("abcde", "name").Valid);
        Assert.False(field.Validate("abcdef", "name").Valid);

        var result = field.Validate("ab", "name");
        Assert.Equal(ErrorCode.MinLength, result.Errors[0].Code);
    }

    [Fact]
    public void StringPattern()
    {
        var field = new StringField().Pattern("^[A-Z][a-z]+$");
        Assert.True(field.Validate("Alice", "name").Valid);
        Assert.False(field.Validate("alice", "name").Valid);
        Assert.Equal(ErrorCode.PatternMismatch, field.Validate("alice", "name").Errors[0].Code);
    }

    [Fact]
    public void StringPatternAnchoredAtStart()
    {
        // Python re.match semantics: matches at the start without ^.
        var field = new StringField().Pattern("[a-z]+");
        Assert.True(field.Validate("abc123", "name").Valid);
        Assert.False(field.Validate("123abc", "name").Valid);
    }

    [Fact]
    public void StringEmail()
    {
        var field = new StringField().Email();
        Assert.True(field.Validate("alice@example.com", "email").Valid);
        Assert.False(field.Validate("not-an-email", "email").Valid);
        Assert.Equal(ErrorCode.InvalidEmail, field.Validate("x", "email").Errors[0].Code);
    }

    [Fact]
    public void StringEnum()
    {
        var field = new StringField().Enum("active", "inactive");
        Assert.True(field.Validate("active", "status").Valid);
        Assert.False(field.Validate("unknown", "status").Valid);
        Assert.Equal(ErrorCode.InvalidEnum, field.Validate("x", "status").Errors[0].Code);
    }

    [Fact]
    public void IntValidation()
    {
        var field = new IntField().Min(0).Max(150);
        Assert.True(field.Validate("30", "age").Valid);
        Assert.False(field.Validate("-1", "age").Valid);
        Assert.False(field.Validate("200", "age").Valid);
        Assert.False(field.Validate("abc", "age").Valid);
        Assert.Equal(ErrorCode.InvalidType, field.Validate("abc", "age").Errors[0].Code);
        Assert.Equal(ErrorCode.MinValue, field.Validate("-1", "age").Errors[0].Code);
        Assert.Equal(ErrorCode.MaxValue, field.Validate("200", "age").Errors[0].Code);
    }

    [Fact]
    public void IntRange()
    {
        var field = new IntField().Range(1, 10);
        Assert.True(field.Validate("5", "n").Valid);
        Assert.False(field.Validate("11", "n").Valid);
    }

    [Fact]
    public void FloatValidation()
    {
        var field = new FloatField().Min(0.0).Max(100.0);
        Assert.True(field.Validate("55.5", "score").Valid);
        Assert.True(field.Validate("100", "score").Valid);
        Assert.False(field.Validate("-0.5", "score").Valid);
        Assert.False(field.Validate("101.5", "score").Valid);
        Assert.False(field.Validate("abc", "score").Valid);
    }

    [Fact]
    public void BoolValidation()
    {
        var field = new BoolField();
        Assert.True(field.Validate("true", "flag").Valid);
        Assert.True(field.Validate("false", "flag").Valid);
        Assert.True(field.Validate("1", "flag").Valid);
        Assert.True(field.Validate("no", "flag").Valid);
        Assert.False(field.Validate("maybe", "flag").Valid);
    }

    [Fact]
    public void RefValidation()
    {
        var field = new RefField().To("company");
        Assert.True(field.Validate(":company:100", "employer").Valid);
        Assert.False(field.Validate(":person:1", "employer").Valid);
        Assert.Equal(ErrorCode.RefWrongType,
                     field.Validate(":person:1", "employer").Errors[0].Code);
        Assert.False(field.Validate("company:100", "employer").Valid);
        Assert.Equal(ErrorCode.InvalidType,
                     field.Validate("junk", "employer").Errors[0].Code);
    }

    [Fact]
    public void RefWithoutTypeAcceptsAnyRef()
    {
        var field = new RefField();
        Assert.True(field.Validate(":anything:1", "link").Valid);
    }
}

public class SchemaDefaultsTests
{
    [Fact]
    public void DefaultAppliedToMissingField()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice")));

        var person = new NodeType("person")
            .Field("name", new StringField().Required())
            .Field("status", new StringField().Default("active"));
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.True(result.Valid);
        Assert.Equal("active", PropertyValue.ValueText(graph.GetNode("person", "1").Properties["status"]));
    }

    [Fact]
    public void DefaultSatisfiesRequired()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");

        var person = new NodeType("person")
            .Field("status", new StringField().Required().Default("active"));
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.True(result.Valid);
        Assert.Equal("active", PropertyValue.ValueText(graph.GetNode("person", "1").Properties["status"]));
    }

    [Fact]
    public void MissingRequiredWithoutDefaultStillErrors()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");

        var person = new NodeType("person").Field("name", new StringField().Required());
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.RequiredField, result.Errors[0].Code);
    }

    [Fact]
    public void PresentValueNotOverwrittenByDefault()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("status", "inactive")));

        var person = new NodeType("person")
            .Field("status", new StringField().Default("active"));
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.True(result.Valid);
        Assert.Equal("inactive", PropertyValue.ValueText(graph.GetNode("person", "1").Properties["status"]));
    }

    [Fact]
    public void EdgeDefaultApplied()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        var person = new NodeType("person");
        var knows = new EdgeType("KNOWS").Field("weight", new IntField().Default(1));
        var result = new GraphSchema("s")
            .NodeTypes(person)
            .EdgeTypes(knows)
            .Validate(graph);

        Assert.True(result.Valid);
        var edge = graph.GetEdge("KNOWS", new("person", "1"), new("person", "2"));
        Assert.Equal("1", PropertyValue.ValueText(edge.Properties["weight"]));
    }

    [Fact]
    public void IntAndBoolDefaults()
    {
        var graph = new ISONGraph();
        graph.AddNode("item", "1");

        var item = new NodeType("item")
            .Field("count", new IntField().Default(42))
            .Field("active", new BoolField().Default(true));
        var result = new GraphSchema("s").NodeTypes(item).Validate(graph);

        Assert.True(result.Valid);
        var props = graph.GetNode("item", "1").Properties;
        Assert.Equal("42", props["count"]);
        Assert.Equal("true", props["active"]);
    }
}

public class NodeTypeSchemaTests
{
    [Fact]
    public void ValidNodePasses()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30")));

        var person = new NodeType("person")
            .Id(new IntField())
            .Field("name", new StringField().Required().Max(100))
            .Field("age", new IntField().Min(0).Max(150));

        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);
        Assert.True(result.Valid);
    }

    [Fact]
    public void IdValidation()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "abc");

        var person = new NodeType("person").Id(new IntField());
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.InvalidType, result.Errors[0].Code);
        Assert.Contains("nodes.person[abc]", result.Errors[0].Location);
    }

    [Fact]
    public void FieldErrorHasLocation()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("age", "999")));

        var person = new NodeType("person").Field("age", new IntField().Max(150));
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal("nodes.person[1].age", result.Errors[0].Location);
    }

    [Fact]
    public void UnregisteredTypesIgnored()
    {
        var graph = new ISONGraph();
        graph.AddNode("mystery", "1", Props.Of(("weird", "value")));

        var person = new NodeType("person").Field("name", new StringField().Required());
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);
        Assert.True(result.Valid);
    }

    [Fact]
    public void CustomNodeConstraint()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1", Props.Of(("name", "Alice")));

        var person = new NodeType("person").Constraint(
            node => node.Properties.ContainsKey("email")
                ? null
                : new ValidationError(ErrorCode.RequiredField, "email is mandatory"));
        var result = new GraphSchema("s").NodeTypes(person).Validate(graph);

        Assert.False(result.Valid);
        Assert.Contains("email is mandatory", result.Errors[0].Message);
    }
}

public class EdgeTypeSchemaTests
{
    private static ISONGraph BaseGraph()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "100");
        return graph;
    }

    [Fact]
    public void SourceAndTargetTypesChecked()
    {
        var graph = BaseGraph();
        graph.AddEdge("WORKS_AT", new("company", "100"), new("person", "1"));

        var worksAt = new EdgeType("WORKS_AT").FromNode("person").ToNode("company");
        var result = new GraphSchema("s").EdgeTypes(worksAt).Validate(graph);

        Assert.False(result.Valid);
        var codes = result.Errors.Select(e => e.Code).ToHashSet();
        Assert.Contains(ErrorCode.InvalidSourceType, codes);
        Assert.Contains(ErrorCode.InvalidTargetType, codes);
    }

    [Fact]
    public void ValidEdgePasses()
    {
        var graph = BaseGraph();
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"),
                      Props.Of(("years", "5")));

        var worksAt = new EdgeType("WORKS_AT")
            .FromNode("person")
            .ToNode("company")
            .Field("years", new IntField().Min(0));
        var result = new GraphSchema("s").EdgeTypes(worksAt).Validate(graph);
        Assert.True(result.Valid);
    }

    [Fact]
    public void NoSelfLoopConstraint()
    {
        var graph = BaseGraph();
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "1"));

        var knows = new EdgeType("KNOWS").NoSelfLoop();
        var result = new GraphSchema("s").EdgeTypes(knows).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.SelfLoop, result.Errors[0].Code);
    }

    [Fact]
    public void EdgeFieldValidation()
    {
        var graph = BaseGraph();
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
                      Props.Of(("since", "not-a-year")));

        var knows = new EdgeType("KNOWS").Field("since", new IntField());
        var result = new GraphSchema("s").EdgeTypes(knows).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.InvalidType, result.Errors[0].Code);
    }

    [Fact]
    public void CustomEdgeConstraint()
    {
        var graph = BaseGraph();
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        var knows = new EdgeType("KNOWS").Constraint(
            _ => new ValidationError(ErrorCode.InvalidType, "always fails"));
        var result = new GraphSchema("s").EdgeTypes(knows).Validate(graph);

        Assert.False(result.Valid);
        Assert.Contains("always fails", result.Errors[0].Message);
    }

    [Fact]
    public void BidirectionalRequiresReverse()
    {
        var graph = BaseGraph();
        graph.AddEdge("FRIENDS", new("person", "1"), new("person", "2"));

        var friends = new EdgeType("FRIENDS").Bidirectional();
        var result = new GraphSchema("s").EdgeTypes(friends).Validate(graph);
        Assert.False(result.Valid);
        Assert.Contains("Missing reverse edge", result.Errors[0].Message);

        graph.AddEdge("FRIENDS", new("person", "2"), new("person", "1"));
        Assert.True(new GraphSchema("s").EdgeTypes(friends).Validate(graph).Valid);
    }
}

public class CardinalityTests
{
    private static ISONGraph PeopleAndCompanies()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddNode("company", "100");
        graph.AddNode("company", "101");
        return graph;
    }

    [Fact]
    public void ManyToOneViolatedByTwoOutgoing()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"));
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "101"));

        var worksAt = new EdgeType("WORKS_AT").Cardinality(Cardinality.ManyToOne);
        var result = new GraphSchema("s").EdgeTypes(worksAt).Validate(graph);

        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.CardinalityViolation, result.Errors[0].Code);
        Assert.Contains("MANY_TO_ONE", result.Errors[0].Message);
    }

    [Fact]
    public void ManyToOneAllowsSharedTarget()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"));
        graph.AddEdge("WORKS_AT", new("person", "2"), new("company", "100"));

        var worksAt = new EdgeType("WORKS_AT").Cardinality(Cardinality.ManyToOne);
        Assert.True(new GraphSchema("s").EdgeTypes(worksAt).Validate(graph).Valid);
    }

    [Fact]
    public void OneToManyViolatedByTwoIncoming()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("MANAGES", new("person", "1"), new("company", "100"));
        graph.AddEdge("MANAGES", new("person", "2"), new("company", "100"));

        var manages = new EdgeType("MANAGES").Cardinality(Cardinality.OneToMany);
        var result = new GraphSchema("s").EdgeTypes(manages).Validate(graph);

        Assert.False(result.Valid);
        Assert.Contains("ONE_TO_MANY", result.Errors[0].Message);
    }

    [Fact]
    public void OneToOneViolatedEitherWay()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("OWNS", new("person", "1"), new("company", "100"));
        graph.AddEdge("OWNS", new("person", "1"), new("company", "101"));

        var owns = new EdgeType("OWNS").Cardinality(Cardinality.OneToOne);
        var result = new GraphSchema("s").EdgeTypes(owns).Validate(graph);
        Assert.False(result.Valid);
        Assert.Contains("ONE_TO_ONE", result.Errors[0].Message);
    }

    [Fact]
    public void OneToOneSatisfied()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("OWNS", new("person", "1"), new("company", "100"));
        graph.AddEdge("OWNS", new("person", "2"), new("company", "101"));

        var owns = new EdgeType("OWNS").Cardinality(Cardinality.OneToOne);
        Assert.True(new GraphSchema("s").EdgeTypes(owns).Validate(graph).Valid);
    }

    [Fact]
    public void ManyToManyUnrestricted()
    {
        var graph = PeopleAndCompanies();
        graph.AddEdge("LIKES", new("person", "1"), new("company", "100"));
        graph.AddEdge("LIKES", new("person", "1"), new("company", "101"));
        graph.AddEdge("LIKES", new("person", "2"), new("company", "100"));

        var likes = new EdgeType("LIKES").Cardinality(Cardinality.ManyToMany);
        Assert.True(new GraphSchema("s").EdgeTypes(likes).Validate(graph).Valid);
    }
}

public class AcyclicSchemaTests
{
    [Fact]
    public void AcyclicViolatedByCycle()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("REPORTS_TO", new("person", "1"), new("person", "2"));
        graph.AddEdge("REPORTS_TO", new("person", "2"), new("person", "1"));

        var reportsTo = new EdgeType("REPORTS_TO").Acyclic();
        var result = new GraphSchema("s").EdgeTypes(reportsTo).Validate(graph);

        Assert.False(result.Valid);
        Assert.Contains(ErrorCode.CycleDetected, result.Errors.Select(e => e.Code));
    }

    [Fact]
    public void AcyclicIsPerRelType()
    {
        // A cycle via OTHER edges must not fail an acyclic REPORTS_TO.
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("REPORTS_TO", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "1")); // KNOWS cycle

        var reportsTo = new EdgeType("REPORTS_TO").Acyclic();
        var result = new GraphSchema("s").EdgeTypes(reportsTo).Validate(graph);
        Assert.True(result.Valid);

        var knows = new EdgeType("KNOWS").Acyclic();
        Assert.False(new GraphSchema("s").EdgeTypes(knows).Validate(graph).Valid);
    }

    [Fact]
    public void AcyclicDagPasses()
    {
        var graph = new ISONGraph();
        graph.AddNode("t", "1");
        graph.AddNode("t", "2");
        graph.AddNode("t", "3");
        graph.AddEdge("DEP", new("t", "1"), new("t", "2"));
        graph.AddEdge("DEP", new("t", "1"), new("t", "3"));
        graph.AddEdge("DEP", new("t", "2"), new("t", "3"));

        var dep = new EdgeType("DEP").Acyclic();
        Assert.True(new GraphSchema("s").EdgeTypes(dep).Validate(graph).Valid);
    }
}

public class GraphSchemaTests
{
    [Fact]
    public void ConnectedConstraint()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        var schema = new GraphSchema("s").Connected();
        Assert.True(schema.Validate(graph).Valid);

        graph.AddNode("person", "99");
        var result = schema.Validate(graph);
        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.NotConnected, result.Errors[0].Code);
    }

    [Fact]
    public void NoOrphansConstraint()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddNode("person", "3"); // orphan

        var result = new GraphSchema("s").NoOrphans().Validate(graph);
        Assert.False(result.Valid);
        Assert.Equal(ErrorCode.OrphanNode, result.Errors[0].Code);
        Assert.Contains(":person:3", result.Errors[0].Message);
    }

    [Fact]
    public void UniqueEdgeConstraintNoDuplicates()
    {
        // The core graph already prevents duplicates, so unique passes.
        var graph = new ISONGraph();
        graph.AddNode("person", "1");
        graph.AddNode("person", "2");
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));

        var knows = new EdgeType("KNOWS").Unique();
        Assert.True(new GraphSchema("s").EdgeTypes(knows).Validate(graph).Valid);
    }

    [Fact]
    public void CustomGraphConstraint()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "1");

        var schema = new GraphSchema("s").Constraint(g =>
            g.NodeCount() < 2
                ? new[] { new ValidationError(ErrorCode.NotConnected, "too small", "graph") }
                : Array.Empty<ValidationError>());

        var result = schema.Validate(graph);
        Assert.False(result.Valid);
        Assert.Contains("too small", result.Errors[0].Message);

        graph.AddNode("person", "2");
        Assert.True(schema.Validate(graph).Valid);
    }

    [Fact]
    public void MaxDepthStored()
    {
        var schema = new GraphSchema("s").MaxDepth(10);
        Assert.Equal(10, schema.MaxDepthValue);
    }

    [Fact]
    public void FullSchemaScenario()
    {
        var person = new NodeType("person")
            .Id(new IntField())
            .Field("name", new StringField().Required().Max(100))
            .Field("age", new IntField().Min(0).Max(150))
            .Field("email", new StringField().Email());

        var company = new NodeType("company")
            .Id(new IntField())
            .Field("name", new StringField().Required());

        var knows = new EdgeType("KNOWS")
            .FromNode(person).ToNode(person).NoSelfLoop().Unique();

        var worksAt = new EdgeType("WORKS_AT")
            .FromNode(person).ToNode(company)
            .Cardinality(Cardinality.ManyToOne);

        var schema = new GraphSchema("social")
            .NodeTypes(person, company)
            .EdgeTypes(knows, worksAt)
            .NoOrphans();

        var graph = new ISONGraph("social");
        graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("age", "30"),
                                              ("email", "alice@example.com")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob"), ("age", "25"),
                                              ("email", "bob@example.com")));
        graph.AddNode("company", "100", Props.Of(("name", "Acme")));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"));
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"));
        graph.AddEdge("WORKS_AT", new("person", "2"), new("company", "100"));

        Assert.True(schema.Validate(graph).Valid);

        // Break it: bad email + orphan.
        graph.AddNode("person", "3", Props.Of(("name", "Carol"), ("email", "nope")));
        var result = schema.Validate(graph);
        Assert.False(result.Valid);
        var codes = result.Errors.Select(e => e.Code).ToHashSet();
        Assert.Contains(ErrorCode.InvalidEmail, codes);
        Assert.Contains(ErrorCode.OrphanNode, codes);
    }

    [Fact]
    public void ValidationResultMergeAndToString()
    {
        var a = new ValidationResult();
        var b = new ValidationResult();
        b.AddError(new ValidationError(ErrorCode.InvalidType, "boom", "loc"));
        b.AddWarning(new ValidationError(ErrorCode.MaxDepthExceeded, "deep"));

        a.Merge(b);
        Assert.False(a.Valid);
        Assert.Single(a.Errors);
        Assert.Single(a.Warnings);
        Assert.Contains("INVALID", a.ToString());
        Assert.Contains("[loc]", a.Errors[0].ToString());
    }
}
