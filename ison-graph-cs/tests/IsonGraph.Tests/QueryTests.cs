// Comprehensive tests for ISONQL: tokenizer, parser, condition evaluation,
// every query type, fluent builders, and error handling. Mirrors the Python
// test suite (tests/test_isonql.py).

using Xunit;

namespace IsonGraph.Tests;

public static class QueryFixtures
{
    public static ISONGraph SimpleGraph()
    {
        var graph = new ISONGraph();
        graph.AddNode("person", "alice",
            Props.Of(("name", "Alice"), ("age", "30"), ("status", "active")));
        graph.AddNode("person", "bob",
            Props.Of(("name", "Bob"), ("age", "25"), ("status", "active")));
        graph.AddNode("person", "charlie",
            Props.Of(("name", "Charlie"), ("age", "35"), ("status", "inactive")));
        graph.AddEdge("KNOWS", new("person", "alice"), new("person", "bob"),
            Props.Of(("since", "2020"), ("strength", "0.8")));
        graph.AddEdge("KNOWS", new("person", "bob"), new("person", "charlie"),
            Props.Of(("since", "2021"), ("strength", "0.5")));
        return graph;
    }

    public static ISONGraph SocialGraph()
    {
        var graph = new ISONGraph();

        // People (ages 30, 25, 35, 28, 32, 40 - the fluent regression fixture)
        graph.AddNode("person", "1",
            Props.Of(("name", "Alice"), ("age", "30"), ("city", "NYC"), ("salary", "80000")));
        graph.AddNode("person", "2",
            Props.Of(("name", "Bob"), ("age", "25"), ("city", "LA"), ("salary", "60000")));
        graph.AddNode("person", "3",
            Props.Of(("name", "Charlie"), ("age", "35"), ("city", "NYC"), ("salary", "90000")));
        graph.AddNode("person", "4",
            Props.Of(("name", "Diana"), ("age", "28"), ("city", "Chicago"), ("salary", "75000")));
        graph.AddNode("person", "5",
            Props.Of(("name", "Eve"), ("age", "32"), ("city", "NYC"), ("salary", "85000")));
        graph.AddNode("person", "6",
            Props.Of(("name", "Frank"), ("age", "40"), ("city", "LA"), ("salary", "100000")));

        // Companies
        graph.AddNode("company", "100",
            Props.Of(("name", "TechCorp"), ("employees", "500"), ("industry", "tech")));
        graph.AddNode("company", "101",
            Props.Of(("name", "FinanceInc"), ("employees", "200"), ("industry", "finance")));
        graph.AddNode("company", "102",
            Props.Of(("name", "StartupXYZ"), ("employees", "50"), ("industry", "tech")));

        // Projects
        graph.AddNode("project", "p1",
            Props.Of(("name", "Project Alpha"), ("budget", "100000")));
        graph.AddNode("project", "p2",
            Props.Of(("name", "Project Beta"), ("budget", "50000")));

        // KNOWS
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "2"),
            Props.Of(("since", "2018"), ("close", "true")));
        graph.AddEdge("KNOWS", new("person", "1"), new("person", "3"),
            Props.Of(("since", "2019"), ("close", "false")));
        graph.AddEdge("KNOWS", new("person", "2"), new("person", "4"),
            Props.Of(("since", "2020"), ("close", "true")));
        graph.AddEdge("KNOWS", new("person", "3"), new("person", "5"),
            Props.Of(("since", "2017"), ("close", "true")));
        graph.AddEdge("KNOWS", new("person", "4"), new("person", "5"),
            Props.Of(("since", "2021"), ("close", "false")));
        graph.AddEdge("KNOWS", new("person", "5"), new("person", "6"),
            Props.Of(("since", "2016"), ("close", "true")));

        // WORKS_AT
        graph.AddEdge("WORKS_AT", new("person", "1"), new("company", "100"),
            Props.Of(("role", "Engineer"), ("years", "5")));
        graph.AddEdge("WORKS_AT", new("person", "2"), new("company", "100"),
            Props.Of(("role", "Designer"), ("years", "2")));
        graph.AddEdge("WORKS_AT", new("person", "3"), new("company", "101"),
            Props.Of(("role", "Manager"), ("years", "8")));
        graph.AddEdge("WORKS_AT", new("person", "4"), new("company", "102"),
            Props.Of(("role", "Developer"), ("years", "3")));
        graph.AddEdge("WORKS_AT", new("person", "5"), new("company", "100"),
            Props.Of(("role", "Lead"), ("years", "6")));
        graph.AddEdge("WORKS_AT", new("person", "6"), new("company", "101"),
            Props.Of(("role", "Director"), ("years", "10")));

        // WORKS_ON
        graph.AddEdge("WORKS_ON", new("person", "1"), new("project", "p1"),
            Props.Of(("hours", "20")));
        graph.AddEdge("WORKS_ON", new("person", "2"), new("project", "p1"),
            Props.Of(("hours", "15")));
        graph.AddEdge("WORKS_ON", new("person", "3"), new("project", "p2"),
            Props.Of(("hours", "10")));

        return graph;
    }

    public static QueryEngine Engine() => new(SocialGraph());
    public static QueryEngine SimpleEngine() => new(SimpleGraph());
}

public class TokenizerTests
{
    [Fact]
    public void TokenizeSimple()
    {
        Assert.Equal(new List<string> { "NODES", "person" },
                     ISONQLParser.Tokenize("NODES person"));
    }

    [Fact]
    public void TokenizeWithOperators()
    {
        Assert.Equal(new List<string> { "NODES", "person", "WHERE", "age", ">", "25" },
                     ISONQLParser.Tokenize("NODES person WHERE age > 25"));
    }

    [Fact]
    public void TokenizeMultiCharOperators()
    {
        var tokens = ISONQLParser.Tokenize("age >= 25 AND age <= 50");
        Assert.Contains(">=", tokens);
        Assert.Contains("<=", tokens);
    }

    [Fact]
    public void TokenizeStringLiterals()
    {
        Assert.Contains("Alice Smith", ISONQLParser.Tokenize("name = \"Alice Smith\""));
    }

    [Fact]
    public void TokenizeSingleQuotedStrings()
    {
        Assert.Contains("Bob", ISONQLParser.Tokenize("name = 'Bob'"));
    }

    [Fact]
    public void TokenizeNodeReference()
    {
        Assert.Contains(":person:alice", ISONQLParser.Tokenize("TRAVERSE :person:alice -> KNOWS"));
    }

    [Fact]
    public void TokenizeArrows()
    {
        var tokens = ISONQLParser.Tokenize("-> KNOWS -> <- FOLLOWS <-");
        Assert.Contains("->", tokens);
        Assert.Contains("<-", tokens);
    }

    [Fact]
    public void TokenizeTypeIdNodeRef()
    {
        Assert.Contains("person:1", ISONQLParser.Tokenize("TRAVERSE person:1 -> KNOWS -> person"));
        var tokens = ISONQLParser.Tokenize("PATH person:alice TO person:bob");
        Assert.Contains("person:alice", tokens);
        Assert.Contains("person:bob", tokens);
    }

    [Fact]
    public void TokenizeBareColon()
    {
        Assert.Equal(new List<string> { "person", ":" }, ISONQLParser.Tokenize("person :"));
    }

    [Fact]
    public void TokenizeNegativeNumbers()
    {
        Assert.Contains("-5", ISONQLParser.Tokenize("NODES person WHERE score > -5"));
        Assert.Contains("-3.5", ISONQLParser.Tokenize("NODES person WHERE score > -3.5"));
    }

    [Fact]
    public void UnknownCharacterRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => ISONQLParser.Tokenize("NODES person WHERE age > 25 ;"));
        Assert.Contains("Unexpected character", ex.Message);
    }
}

public class ParserTests
{
    private readonly ISONQLParser _parser = new();

    [Fact]
    public void ParseNodesBasic()
    {
        var result = _parser.Parse("NODES person");
        Assert.Equal(QueryType.Nodes, result.Type);
        Assert.Equal("person", result.NodeType);
        Assert.Empty(result.ConditionGroups);
    }

    [Fact]
    public void ParseNodesWithWhere()
    {
        var result = _parser.Parse("NODES person WHERE age > 25");
        Assert.Equal("person", result.NodeType);
        Assert.Single(result.ConditionGroups);
        var cond = result.ConditionGroups[0][0];
        Assert.Equal("age", cond.Field);
        Assert.Equal(Operator.Gt, cond.Operator);
        Assert.Equal(25L, cond.Value);
    }

    [Fact]
    public void ParseNodesWithOrderBy()
    {
        var result = _parser.Parse("NODES person ORDER BY name DESC");
        Assert.Equal("name", result.OrderBy);
        Assert.Equal(SortOrder.Desc, result.OrderDir);
    }

    [Fact]
    public void ParseNodesWithLimitOffset()
    {
        var result = _parser.Parse("NODES person LIMIT 10 OFFSET 5");
        Assert.Equal(10, result.Limit);
        Assert.Equal(5, result.Offset);
    }

    [Fact]
    public void ParseNodesShorthand()
    {
        var result = _parser.Parse("NODES person(name=\"Alice\", age=30)");
        Assert.Equal("person", result.NodeType);
        Assert.Equal(2, result.Conditions.Count);
    }

    [Fact]
    public void ParseEdgesBasic()
    {
        var result = _parser.Parse("EDGES KNOWS");
        Assert.Equal(QueryType.Edges, result.Type);
        Assert.Equal("KNOWS", result.RelType);
    }

    [Fact]
    public void ParseEdgesWithWhere()
    {
        var result = _parser.Parse("EDGES KNOWS WHERE since > 2020");
        var cond = result.ConditionGroups[0][0];
        Assert.Equal("since", cond.Field);
        Assert.Equal(2020L, cond.Value);
    }

    [Fact]
    public void ParseTraverse()
    {
        var result = _parser.Parse("TRAVERSE person:alice -> KNOWS -> person");
        Assert.Equal(QueryType.Traverse, result.Type);
        Assert.Equal(new NodeRef("person", "alice"), result.Start);
        Assert.Single(result.Pattern);
        Assert.Equal("KNOWS", result.Pattern[0].RelType);
        Assert.Equal("person", result.Pattern[0].TargetType);
        Assert.Equal(Direction.Out, result.Pattern[0].Direction);
    }

    [Fact]
    public void ParseTraverseWithMax()
    {
        var result = _parser.Parse("TRAVERSE person:1 -> KNOWS -> person MAX 3");
        Assert.Equal(3, result.MaxDepth);
    }

    [Fact]
    public void ParseTraverseIncoming()
    {
        var result = _parser.Parse("TRAVERSE person:2 <- KNOWS <- person");
        Assert.Equal(Direction.In, result.Pattern[0].Direction);
    }

    [Fact]
    public void ParsePath()
    {
        var result = _parser.Parse("PATH person:alice TO person:bob");
        Assert.Equal(QueryType.Path, result.Type);
        Assert.Equal(new NodeRef("person", "alice"), result.Source);
        Assert.Equal(new NodeRef("person", "bob"), result.Target);
    }

    [Fact]
    public void ParsePathWithVia()
    {
        var result = _parser.Parse("PATH person:1 TO person:5 VIA KNOWS MAX 5");
        Assert.Equal("KNOWS", result.Via);
        Assert.Equal(5, result.MaxHops);
    }

    [Fact]
    public void ParseCount()
    {
        var result = _parser.Parse("COUNT person WHERE age > 25");
        Assert.Equal(QueryType.Count, result.Type);
        Assert.Equal("person", result.NodeType);
        Assert.Single(result.Conditions);
    }

    [Fact]
    public void ParseAggregationSum()
    {
        var result = _parser.Parse("SUM person.salary WHERE city = NYC");
        Assert.Equal(QueryType.Sum, result.Type);
        Assert.Equal("person", result.NodeType);
        Assert.Equal("salary", result.Property);
    }

    [Fact]
    public void ParseAggregationAvg()
    {
        var result = _parser.Parse("AVG person.age");
        Assert.Equal(QueryType.Avg, result.Type);
        Assert.Equal("age", result.Property);
    }

    [Fact]
    public void ParseMultipleConditions()
    {
        var result = _parser.Parse(
            "NODES person WHERE age > 25 AND city = NYC AND status = active");
        Assert.Equal(3, result.Conditions.Count);
        Assert.Single(result.ConditionGroups);
    }

    [Fact]
    public void ParseInOperator()
    {
        var result = _parser.Parse("NODES person WHERE city IN (NYC, LA, Chicago)");
        var cond = result.ConditionGroups[0][0];
        Assert.Equal(Operator.In, cond.Operator);
        Assert.Equal(new List<string> { "NYC", "LA", "Chicago" }, cond.Value);
    }

    [Fact]
    public void ParseContainsOperator()
    {
        var result = _parser.Parse("NODES person WHERE name CONTAINS Ali");
        Assert.Equal(Operator.Contains, result.ConditionGroups[0][0].Operator);
    }

    [Fact]
    public void ParseExistsOperator()
    {
        var result = _parser.Parse("NODES person WHERE EXISTS email");
        Assert.Equal(Operator.Exists, result.ConditionGroups[0][0].Operator);
        Assert.Equal("email", result.ConditionGroups[0][0].Field);
    }

    [Fact]
    public void ParseBooleanValues()
    {
        var result = _parser.Parse("NODES person WHERE active = TRUE");
        Assert.True(result.ConditionGroups[0][0].Value is true);
    }

    [Fact]
    public void ParseNullValues()
    {
        var result = _parser.Parse("NODES person WHERE email = NULL");
        Assert.Null(result.ConditionGroups[0][0].Value);
    }

    [Fact]
    public void ParseFloatValues()
    {
        var result = _parser.Parse("NODES person WHERE score > 3.5");
        Assert.Equal(3.5, result.ConditionGroups[0][0].Value);
    }

    [Fact]
    public void ParseNegativeValues()
    {
        var result = _parser.Parse("NODES person WHERE score > -5");
        Assert.Equal(-5L, result.ConditionGroups[0][0].Value);

        result = _parser.Parse("NODES person WHERE score > -3.5");
        Assert.Equal(-3.5, result.ConditionGroups[0][0].Value);
    }

    [Fact]
    public void ParseInvalidQueryType()
    {
        var ex = Assert.Throws<ArgumentException>(() => _parser.Parse("INVALID person"));
        Assert.Contains("Unknown query type", ex.Message);
    }

    [Fact]
    public void ParseEmptyQuery()
    {
        Assert.Throws<ArgumentException>(() => _parser.Parse(""));
    }

    [Fact]
    public void ParseInvalidNodeRef()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => _parser.Parse("TRAVERSE invalid_ref -> KNOWS"));
        Assert.Contains("Invalid node reference", ex.Message);
    }

    [Fact]
    public void ParseOrConditions()
    {
        var result = _parser.Parse("NODES person WHERE city = LA OR city = Chicago");
        Assert.Equal(2, result.ConditionGroups.Count);
        Assert.Equal("LA", result.ConditionGroups[0][0].Value);
        Assert.Equal("Chicago", result.ConditionGroups[1][0].Value);
    }

    [Fact]
    public void ParseAndOrPrecedence()
    {
        // AND binds tighter than OR: a AND b OR c == (a AND b) OR c
        var result = _parser.Parse(
            "NODES person WHERE age > 30 AND city = NYC OR city = Chicago");
        Assert.Equal(2, result.ConditionGroups.Count);
        Assert.Equal(2, result.ConditionGroups[0].Count);
        Assert.Single(result.ConditionGroups[1]);
    }

    [Fact]
    public void ParseUnknownOperatorRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => _parser.Parse("NODES person WHERE age INVALID 25"));
        Assert.Contains("unknown operator", ex.Message);
    }

    [Fact]
    public void ParseUnclosedListRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => _parser.Parse("NODES person WHERE city IN ('NYC', 'LA'"));
        Assert.Contains("unclosed list", ex.Message);
    }

    [Fact]
    public void ParseNotWithoutExistsOrInRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => _parser.Parse("NODES person WHERE city NOT LIKE x"));
        Assert.Contains("expected EXISTS or IN after NOT", ex.Message);
    }

    [Fact]
    public void CaseInsensitiveKeywords()
    {
        Assert.Equal(QueryType.Nodes, _parser.Parse("NODES person").Type);
        Assert.Equal(QueryType.Nodes, _parser.Parse("nodes person").Type);
        Assert.Equal(QueryType.Nodes, _parser.Parse("Nodes Person").Type);
    }

    [Fact]
    public void WhitespaceHandling()
    {
        var result = _parser.Parse("  NODES   person   WHERE   age  >  25  ");
        Assert.Equal(QueryType.Nodes, result.Type);
        Assert.Equal("person", result.NodeType);
    }
}

public class ConditionTests
{
    private static Dictionary<string, object?> P(params (string K, object? V)[] pairs) =>
        pairs.ToDictionary(p => p.K, p => p.V);

    [Fact]
    public void EqOperator()
    {
        var cond = new Condition("name", Operator.Eq, "Alice");
        Assert.True(cond.Evaluate(P(("name", "Alice"))));
        Assert.False(cond.Evaluate(P(("name", "Bob"))));
    }

    [Fact]
    public void NeOperator()
    {
        var cond = new Condition("name", Operator.Ne, "Alice");
        Assert.True(cond.Evaluate(P(("name", "Bob"))));
        Assert.False(cond.Evaluate(P(("name", "Alice"))));
    }

    [Fact]
    public void GtOperator()
    {
        var cond = new Condition("age", Operator.Gt, 25L);
        Assert.True(cond.Evaluate(P(("age", "30"))));
        Assert.False(cond.Evaluate(P(("age", "25"))));
        Assert.False(cond.Evaluate(P(("age", "20"))));
    }

    [Fact]
    public void GeOperator()
    {
        var cond = new Condition("age", Operator.Ge, 25L);
        Assert.True(cond.Evaluate(P(("age", "30"))));
        Assert.True(cond.Evaluate(P(("age", "25"))));
        Assert.False(cond.Evaluate(P(("age", "20"))));
    }

    [Fact]
    public void LtOperator()
    {
        var cond = new Condition("age", Operator.Lt, 25L);
        Assert.True(cond.Evaluate(P(("age", "20"))));
        Assert.False(cond.Evaluate(P(("age", "25"))));
        Assert.False(cond.Evaluate(P(("age", "30"))));
    }

    [Fact]
    public void LeOperator()
    {
        var cond = new Condition("age", Operator.Le, 25L);
        Assert.True(cond.Evaluate(P(("age", "20"))));
        Assert.True(cond.Evaluate(P(("age", "25"))));
        Assert.False(cond.Evaluate(P(("age", "30"))));
    }

    [Fact]
    public void NumericComparisonAgainstNonNumericPropIsFalse()
    {
        var cond = new Condition("age", Operator.Gt, 25L);
        Assert.False(cond.Evaluate(P(("age", "abc"))));
    }

    [Fact]
    public void FloatComparison()
    {
        var cond = new Condition("strength", Operator.Gt, 0.6);
        Assert.True(cond.Evaluate(P(("strength", "0.8"))));
        Assert.False(cond.Evaluate(P(("strength", "0.5"))));
    }

    [Fact]
    public void InOperator()
    {
        var cond = new Condition("city", Operator.In, new List<string> { "NYC", "LA" });
        Assert.True(cond.Evaluate(P(("city", "NYC"))));
        Assert.True(cond.Evaluate(P(("city", "LA"))));
        Assert.False(cond.Evaluate(P(("city", "Chicago"))));
    }

    [Fact]
    public void NotInOperator()
    {
        var cond = new Condition("city", Operator.NotIn, new List<string> { "NYC", "LA" });
        Assert.True(cond.Evaluate(P(("city", "Chicago"))));
        Assert.False(cond.Evaluate(P(("city", "NYC"))));
    }

    [Fact]
    public void ContainsOperator()
    {
        var cond = new Condition("name", Operator.Contains, "lic");
        Assert.True(cond.Evaluate(P(("name", "Alice"))));
        Assert.False(cond.Evaluate(P(("name", "Bob"))));
    }

    [Fact]
    public void StartsWithOperator()
    {
        var cond = new Condition("name", Operator.StartsWith, "Al");
        Assert.True(cond.Evaluate(P(("name", "Alice"))));
        Assert.False(cond.Evaluate(P(("name", "Bob"))));
    }

    [Fact]
    public void EndsWithOperator()
    {
        var cond = new Condition("email", Operator.EndsWith, ".com");
        Assert.True(cond.Evaluate(P(("email", "alice@example.com"))));
        Assert.False(cond.Evaluate(P(("email", "alice@example.org"))));
    }

    [Fact]
    public void MatchesOperator()
    {
        // Python re.match semantics: anchored at the start of the value.
        var cond = new Condition("email", Operator.Matches, "^[a-z]+@");
        Assert.True(cond.Evaluate(P(("email", "alice@example.com"))));
        Assert.False(cond.Evaluate(P(("email", "123@example.com"))));

        var unanchored = new Condition("email", Operator.Matches, "[a-z]+@");
        Assert.False(unanchored.Evaluate(P(("email", "123abc@example.com"))));
    }

    [Fact]
    public void MatchesInvalidRegexIsFalse()
    {
        var cond = new Condition("email", Operator.Matches, "([");
        Assert.False(cond.Evaluate(P(("email", "alice@example.com"))));
    }

    [Fact]
    public void ExistsOperator()
    {
        var cond = new Condition("email", Operator.Exists);
        Assert.True(cond.Evaluate(P(("email", "alice@example.com"))));
        Assert.False(cond.Evaluate(P(("name", "Alice"))));
    }

    [Fact]
    public void NotExistsOperator()
    {
        var cond = new Condition("email", Operator.NotExists);
        Assert.True(cond.Evaluate(P(("name", "Alice"))));
        Assert.False(cond.Evaluate(P(("email", "alice@example.com"))));
    }

    [Fact]
    public void MissingFieldIsFalse()
    {
        var cond = new Condition("missing", Operator.Eq, "value");
        Assert.False(cond.Evaluate(P(("other", "value"))));
    }
}

public class NodesQueryTests
{
    [Fact]
    public void NodesAll()
    {
        var result = QueryFixtures.Engine().Execute("NODES");
        Assert.True(result.Count > 0);
        Assert.Equal(result.Count, result.TotalCount);
    }

    [Fact]
    public void NodesByType()
    {
        var result = QueryFixtures.Engine().Execute("NODES person");
        Assert.Equal(6, result.Count);
        Assert.All(result.Nodes, n => Assert.Equal("person", n.Type));
    }

    [Fact]
    public void NodesWhereGt()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE age > 30");
        Assert.Equal(3, result.Count); // Charlie (35), Eve (32), Frank (40)
        Assert.All(result.Nodes, n => Assert.True(int.Parse(PropertyValue.ValueText(n.Properties["age"])) > 30));
    }

    [Fact]
    public void NodesWhereEqString()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE city = NYC");
        Assert.Equal(3, result.Count); // Alice, Charlie, Eve
        Assert.All(result.Nodes, n => Assert.Equal("NYC", PropertyValue.ValueText(n.Properties["city"])));
    }

    [Fact]
    public void NodesWhereMultipleConditions()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE age > 25 AND city = NYC");
        Assert.Equal(3, result.Count); // Alice (30), Charlie (35), Eve (32)
    }

    [Fact]
    public void NodesOrderByAsc()
    {
        var result = QueryFixtures.Engine().Execute("NODES person ORDER BY age ASC");
        var ages = result.Nodes.Select(n => int.Parse(PropertyValue.ValueText(n.Properties["age"]))).ToList();
        Assert.Equal(ages.OrderBy(a => a).ToList(), ages);
    }

    [Fact]
    public void NodesOrderByDesc()
    {
        var result = QueryFixtures.Engine().Execute("NODES person ORDER BY age DESC");
        var ages = result.Nodes.Select(n => int.Parse(PropertyValue.ValueText(n.Properties["age"]))).ToList();
        Assert.Equal(ages.OrderByDescending(a => a).ToList(), ages);
    }

    [Fact]
    public void NodesOrderByStringField()
    {
        var result = QueryFixtures.Engine().Execute("NODES person ORDER BY name ASC");
        var names = result.Nodes.Select(n => PropertyValue.ValueText(n.Properties["name"])).ToList();
        Assert.Equal(new List<string> { "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank" },
                     names);
    }

    [Fact]
    public void NodesLimit()
    {
        var result = QueryFixtures.Engine().Execute("NODES person LIMIT 3");
        Assert.Equal(3, result.Count);
        Assert.Equal(6, result.TotalCount);
    }

    [Fact]
    public void NodesOffset()
    {
        var result = QueryFixtures.Engine()
            .Execute("NODES person ORDER BY age ASC LIMIT 2 OFFSET 2");
        Assert.Equal(2, result.Count);
        var ages = result.Nodes.Select(n => int.Parse(PropertyValue.ValueText(n.Properties["age"]))).ToList();
        Assert.True(ages[0] >= 28); // skipped 25, 28
    }

    [Fact]
    public void NodesReturnFields()
    {
        var result = QueryFixtures.Engine().Execute("NODES person RETURN name, age");
        Assert.Equal(6, result.Count);
        foreach (var node in result.Nodes)
        {
            Assert.True(node.Properties.ContainsKey("name"));
            Assert.True(node.Properties.ContainsKey("age"));
            Assert.False(node.Properties.ContainsKey("city"));
        }
    }

    [Fact]
    public void NodesShorthandSyntax()
    {
        var result = QueryFixtures.Engine().Execute("NODES person(city=\"NYC\")");
        Assert.Equal(3, result.Count);
    }

    [Fact]
    public void NodesShorthandCombinedWithWhere()
    {
        var result = QueryFixtures.Engine()
            .Execute("NODES person(city=\"NYC\") WHERE age > 30");
        Assert.Equal(2, result.Count); // Charlie (35), Eve (32)
    }

    [Fact]
    public void NodesInOperator()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE city IN (NYC, LA)");
        Assert.Equal(5, result.Count);
    }

    [Fact]
    public void NodesContainsOperator()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE name CONTAINS a");
        Assert.All(result.Nodes, n => Assert.Contains("a", PropertyValue.ValueText(n.Properties["name"])));
    }

    [Fact]
    public void NodesStartsWith()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE name STARTS_WITH A");
        Assert.Equal(1, result.Count); // Alice
    }

    [Fact]
    public void NodesEmptyResult()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE age > 100");
        Assert.Equal(0, result.Count);
        Assert.Empty(result.Nodes);
    }

    [Fact]
    public void NodesWhereOr()
    {
        var result = QueryFixtures.Engine()
            .Execute("NODES person WHERE city = LA OR city = Chicago");
        Assert.Equal(3, result.Count); // Bob (LA), Frank (LA), Diana (Chicago)
        Assert.All(result.Nodes,
                   n => Assert.Contains(PropertyValue.ValueText(n.Properties["city"]), new[] { "LA", "Chicago" }));
    }

    [Fact]
    public void NodesWhereAndOrPrecedence()
    {
        var result = QueryFixtures.Engine()
            .Execute("NODES person WHERE age > 30 AND city = NYC OR city = Chicago");
        // (age > 30 AND NYC) -> Charlie, Eve; OR Chicago -> Diana
        Assert.Equal(3, result.Count);
        var names = result.Nodes.Select(n => PropertyValue.ValueText(n.Properties["name"])).ToHashSet();
        Assert.Equal(new HashSet<string> { "Charlie", "Eve", "Diana" }, names);
    }

    [Fact]
    public void NodesLimitZero()
    {
        var result = QueryFixtures.Engine().Execute("NODES person LIMIT 0");
        Assert.Equal(0, result.Count);
        Assert.Equal(6, result.TotalCount);
    }

    [Fact]
    public void NodesWhereNegativeNumber()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE age > -5");
        Assert.Equal(6, result.Count);
    }

    [Fact]
    public void NodesOrderByMissingFieldSortsLast()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("person", "999", Props.Of(("name", "NoAge"), ("city", "NYC")));

        var result = engine.Execute("NODES person ORDER BY age ASC");
        Assert.Equal(7, result.Count);
        Assert.Equal("999", result.Nodes[^1].Id);
        var ages = result.Nodes.Take(6).Select(n => int.Parse(PropertyValue.ValueText(n.Properties["age"]))).ToList();
        Assert.Equal(ages.OrderBy(a => a).ToList(), ages);

        result = engine.Execute("NODES person ORDER BY age DESC");
        Assert.Equal("999", result.Nodes[^1].Id); // missing still last on DESC
    }

    [Fact]
    public void NodesPostfixExists()
    {
        var graph = new ISONGraph("robust");
        graph.AddNode("person", "1",
            Props.Of(("name", "Alice"), ("email", "a@x.com"), ("city", "NYC")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob"), ("city", "LA")));
        var engine = new QueryEngine(graph);

        var result = engine.Execute("NODES person WHERE email EXISTS");
        Assert.Equal(1, result.Count);
        Assert.Equal("Alice", PropertyValue.ValueText(result.Nodes[0].Properties["name"]));
    }

    [Fact]
    public void NodesPostfixNotExists()
    {
        var graph = new ISONGraph("robust");
        graph.AddNode("person", "1",
            Props.Of(("name", "Alice"), ("email", "a@x.com"), ("city", "NYC")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob"), ("city", "LA")));
        var engine = new QueryEngine(graph);

        var result = engine.Execute("NODES person WHERE email NOT EXISTS");
        Assert.Equal(1, result.Count);
        Assert.Equal("Bob", PropertyValue.ValueText(result.Nodes[0].Properties["name"]));
    }

    [Fact]
    public void NodesNotInList()
    {
        var graph = new ISONGraph("robust");
        graph.AddNode("person", "1", Props.Of(("name", "Alice"), ("city", "NYC")));
        graph.AddNode("person", "2", Props.Of(("name", "Bob"), ("city", "LA")));
        var engine = new QueryEngine(graph);

        var result = engine.Execute("NODES person WHERE city NOT IN ('NYC')");
        Assert.Equal(1, result.Count);
        Assert.Equal("Bob", PropertyValue.ValueText(result.Nodes[0].Properties["name"]));
    }
}

public class EdgesQueryTests
{
    [Fact]
    public void EdgesAll()
    {
        var result = QueryFixtures.Engine().Execute("EDGES");
        Assert.Equal(15, result.Count); // 6 KNOWS + 6 WORKS_AT + 3 WORKS_ON
    }

    [Fact]
    public void EdgesByType()
    {
        var result = QueryFixtures.Engine().Execute("EDGES KNOWS");
        Assert.Equal(6, result.Count);
        Assert.All(result.Edges, e => Assert.Equal("KNOWS", e.RelType));
    }

    [Fact]
    public void EdgesWhereCondition()
    {
        var result = QueryFixtures.Engine().Execute("EDGES KNOWS WHERE since > 2019");
        Assert.Equal(2, result.Count); // 2020, 2021
        Assert.All(result.Edges, e => Assert.True(int.Parse(PropertyValue.ValueText(e.Properties["since"])) > 2019));
    }

    [Fact]
    public void EdgesWhereBoolean()
    {
        var result = QueryFixtures.Engine().Execute("EDGES KNOWS WHERE close = TRUE");
        Assert.Equal(4, result.Count);
        Assert.All(result.Edges, e => Assert.Equal("true", PropertyValue.ValueText(e.Properties["close"])));
    }

    [Fact]
    public void EdgesLimit()
    {
        var result = QueryFixtures.Engine().Execute("EDGES KNOWS LIMIT 3");
        Assert.Equal(3, result.Count);
        Assert.Equal(6, result.TotalCount);
    }

    [Fact]
    public void EdgesWorksAt()
    {
        var result = QueryFixtures.Engine().Execute("EDGES WORKS_AT");
        Assert.Equal(6, result.Count);
        Assert.All(result.Edges, e => Assert.Equal("WORKS_AT", e.RelType));
    }

    [Fact]
    public void EdgesWithPropertyFilter()
    {
        var result = QueryFixtures.Engine().Execute("EDGES WORKS_AT WHERE years > 5");
        Assert.Equal(3, result.Count); // 8, 6, 10
        Assert.All(result.Edges, e => Assert.True(int.Parse(PropertyValue.ValueText(e.Properties["years"])) > 5));
    }
}

public class TraverseQueryTests
{
    [Fact]
    public void TraverseSingleHop()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:1 -> KNOWS -> person");
        Assert.Equal(2, result.Count); // Alice knows Bob and Charlie
    }

    [Fact]
    public void TraverseWithColonPrefix()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE :person:1 -> KNOWS -> person");
        Assert.Equal(2, result.Count);
    }

    [Fact]
    public void TraverseMaxDepth()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:1 -> KNOWS -> person MAX 2");
        Assert.True(result.Count >= 2);
    }

    [Fact]
    public void TraverseIncoming()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:2 <- KNOWS <- person");
        Assert.True(result.Count >= 1); // Alice knows Bob
        Assert.Contains(new NodeRef("person", "1"), result.Refs);
    }

    [Fact]
    public void TraverseLimit()
    {
        var result = QueryFixtures.Engine()
            .Execute("TRAVERSE person:1 -> KNOWS -> person MAX 3 LIMIT 2");
        Assert.True(result.Count <= 2);
    }

    [Fact]
    public void TraverseWildcardTarget()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:1 -> WORKS_AT -> *");
        Assert.Equal(1, result.Count);
        Assert.Equal(new NodeRef("company", "100"), result.Refs[0]);
    }

    [Fact]
    public void TraverseFromStringId()
    {
        var result = QueryFixtures.SimpleEngine()
            .Execute("TRAVERSE person:alice -> KNOWS -> person");
        Assert.Equal(1, result.Count);
        Assert.Equal(new NodeRef("person", "bob"), result.Refs[0]);
    }

    [Fact]
    public void TraverseNonExistentNode()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:99999 -> KNOWS -> person");
        Assert.Equal(0, result.Count);
    }

    [Fact]
    public void TraverseVeryDeep()
    {
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:1 -> KNOWS -> person MAX 10");
        Assert.True(result.Count >= 0);
    }

    [Fact]
    public void TraverseTargetTypeFilters()
    {
        // WORKS_AT reaches only companies; restricting to person yields nothing.
        var result = QueryFixtures.Engine().Execute("TRAVERSE person:1 -> WORKS_AT -> person");
        Assert.Equal(0, result.Count);
    }
}

public class PathQueryTests
{
    [Fact]
    public void PathDirect()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:1 TO person:2");
        Assert.Equal(1, result.Count);
        Assert.Equal(1, result.Paths[0].Length);
    }

    [Fact]
    public void PathMultiHop()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:1 TO person:5 VIA KNOWS");
        Assert.Equal(1, result.Count);
        Assert.True(result.Paths[0].Length >= 1);
    }

    [Fact]
    public void PathViaRelationship()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:1 TO person:4 VIA KNOWS MAX 5");
        Assert.Equal(1, result.Count);
        Assert.All(result.Paths[0].Edges, e => Assert.Equal("KNOWS", e.RelType));
    }

    [Fact]
    public void PathMaxHops()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:1 TO person:6 MAX 3");
        Assert.True(result.Count <= 1);
    }

    [Fact]
    public void PathNotFound()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("person", "999", Props.Of(("name", "Isolated")));
        var result = engine.Execute("PATH person:1 TO person:999 MAX 5");
        Assert.Equal(0, result.Count);
    }

    [Fact]
    public void PathSameNode()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:1 TO person:1");
        Assert.Equal(1, result.Count);
        Assert.Equal(0, result.Paths[0].Length);
    }

    [Fact]
    public void PathWithStringIds()
    {
        var result = QueryFixtures.SimpleEngine()
            .Execute("PATH person:alice TO person:charlie VIA KNOWS");
        Assert.Equal(1, result.Count);
        Assert.Equal(2, result.Paths[0].Length);
    }

    [Fact]
    public void PathNonExistentNodes()
    {
        var result = QueryFixtures.Engine().Execute("PATH person:99998 TO person:99999");
        Assert.Equal(0, result.Count);
    }

    [Fact]
    public void PathMissingSourceThrows()
    {
        Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Execute("PATH TO person:bob"));
    }
}

public class CountQueryTests
{
    [Fact]
    public void CountAllOfType()
    {
        var result = QueryFixtures.Engine().Execute("COUNT person");
        Assert.Equal(6L, result.CountValue);
    }

    [Fact]
    public void CountWithCondition()
    {
        var result = QueryFixtures.Engine().Execute("COUNT person WHERE age > 30");
        Assert.Equal(3L, result.CountValue);
    }

    [Fact]
    public void CountWithMultipleConditions()
    {
        var result = QueryFixtures.Engine().Execute("COUNT person WHERE age > 25 AND city = NYC");
        Assert.Equal(3L, result.CountValue);
    }

    [Fact]
    public void CountCompanies()
    {
        var result = QueryFixtures.Engine().Execute("COUNT company");
        Assert.Equal(3L, result.CountValue);
    }

    [Fact]
    public void CountZero()
    {
        var result = QueryFixtures.Engine().Execute("COUNT person WHERE age > 100");
        Assert.Equal(0L, result.CountValue);
    }

    [Fact]
    public void CountWithOr()
    {
        var result = QueryFixtures.Engine()
            .Execute("COUNT person WHERE city = LA OR city = Chicago");
        Assert.Equal(3L, result.CountValue);
    }
}

public class AggregationQueryTests
{
    [Fact]
    public void SumBasic()
    {
        var result = QueryFixtures.Engine().Execute("SUM person.salary");
        Assert.Equal(80000.0 + 60000 + 90000 + 75000 + 85000 + 100000, result.Value);
    }

    [Fact]
    public void SumWithCondition()
    {
        var result = QueryFixtures.Engine().Execute("SUM person.salary WHERE city = NYC");
        Assert.Equal(80000.0 + 90000 + 85000, result.Value);
    }

    [Fact]
    public void AvgBasic()
    {
        var result = QueryFixtures.Engine().Execute("AVG person.age");
        var expected = (30.0 + 25 + 35 + 28 + 32 + 40) / 6;
        Assert.NotNull(result.Value);
        Assert.True(Math.Abs(result.Value.Value - expected) < 0.01);
    }

    [Fact]
    public void AvgWithCondition()
    {
        var result = QueryFixtures.Engine().Execute("AVG person.salary WHERE city = NYC");
        var expected = (80000.0 + 90000 + 85000) / 3;
        Assert.NotNull(result.Value);
        Assert.True(Math.Abs(result.Value.Value - expected) < 0.01);
    }

    [Fact]
    public void MinBasic()
    {
        var result = QueryFixtures.Engine().Execute("MIN person.age");
        Assert.Equal(25.0, result.Value);
    }

    [Fact]
    public void MinWithCondition()
    {
        var result = QueryFixtures.Engine().Execute("MIN person.salary WHERE city = NYC");
        Assert.Equal(80000.0, result.Value);
    }

    [Fact]
    public void MaxBasic()
    {
        var result = QueryFixtures.Engine().Execute("MAX person.age");
        Assert.Equal(40.0, result.Value);
    }

    [Fact]
    public void MaxWithCondition()
    {
        var result = QueryFixtures.Engine().Execute("MAX person.salary WHERE city = LA");
        Assert.Equal(100000.0, result.Value);
    }

    [Fact]
    public void AggregationNoMatches()
    {
        var result = QueryFixtures.Engine().Execute("SUM person.salary WHERE age > 100");
        Assert.Null(result.Value);
        Assert.Equal(0, result.TotalCount);
    }

    [Fact]
    public void AggregationMissingProperty()
    {
        var result = QueryFixtures.Engine().Execute("SUM person.nonexistent");
        Assert.Null(result.Value);
    }
}

public class FluentApiTests
{
    [Fact]
    public void BasicMatch()
    {
        var result = QueryFixtures.Engine().Match("person").Execute();
        Assert.Equal(6, result.Count);
    }

    [Fact]
    public void MatchWithWhereRegressionCount()
    {
        // Regression: ages 30, 25, 35, 28, 32, 40 - "age > 30" matches exactly 3.
        var result = QueryFixtures.Engine().Match("person").Where("age", ">", 30).Execute();
        Assert.Equal(3, result.Count);
        var names = result.Nodes.Select(n => PropertyValue.ValueText(n.Properties["name"])).ToHashSet();
        Assert.Equal(new HashSet<string> { "Charlie", "Eve", "Frank" }, names);
    }

    [Fact]
    public void MatchMultipleWhere()
    {
        var result = QueryFixtures.Engine().Match("person")
            .Where("age", ">", 25)
            .Where("city", "=", "NYC")
            .Execute();
        Assert.Equal(3, result.Count);
    }

    [Fact]
    public void MatchOrderBy()
    {
        var result = QueryFixtures.Engine().Match("person").OrderBy("age", "ASC").Execute();
        var ages = result.Nodes.Select(n => int.Parse(PropertyValue.ValueText(n.Properties["age"]))).ToList();
        Assert.Equal(ages.OrderBy(a => a).ToList(), ages);
    }

    [Fact]
    public void MatchOrderByDesc()
    {
        var result = QueryFixtures.Engine().Match("person").OrderBy("age", "DESC").Execute();
        Assert.Equal("40", PropertyValue.ValueText(result.Nodes[0].Properties["age"]));
    }

    [Fact]
    public void MatchLimit()
    {
        var result = QueryFixtures.Engine().Match("person").Limit(3).Execute();
        Assert.Equal(3, result.Count);
    }

    [Fact]
    public void MatchOffset()
    {
        var result = QueryFixtures.Engine().Match("person")
            .OrderBy("age", "ASC").Offset(2).Limit(2).Execute();
        Assert.Equal(2, result.Count);
        Assert.Equal("30", PropertyValue.ValueText(result.Nodes[0].Properties["age"]));
    }

    [Fact]
    public void MatchReturnFields()
    {
        var result = QueryFixtures.Engine().Match("person")
            .ReturnFields("name", "age").Execute();
        foreach (var node in result.Nodes)
        {
            Assert.True(node.Properties.ContainsKey("name"));
            Assert.True(node.Properties.ContainsKey("age"));
            Assert.False(node.Properties.ContainsKey("city"));
        }
    }

    [Fact]
    public void MatchWhereExists()
    {
        var result = QueryFixtures.Engine().Match("person").WhereExists("salary").Execute();
        Assert.Equal(6, result.Count);
    }

    [Fact]
    public void MatchWhereNotExists()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("person", "999", Props.Of(("name", "NoEmail"), ("age", "50")));
        var result = engine.Match("person").WhereNotExists("email").Execute();
        Assert.Equal(7, result.Count); // nobody has an email
    }

    [Fact]
    public void MatchCount()
    {
        var count = QueryFixtures.Engine().Match("person").Where("age", ">", 30).Count();
        Assert.Equal(3L, count);
    }

    [Fact]
    public void MatchLimitZero()
    {
        var result = QueryFixtures.Engine().Match("person").Limit(0).Execute();
        Assert.Equal(0, result.Count);
        Assert.Equal(6, result.TotalCount);
    }

    [Fact]
    public void WhereInvalidOperatorRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Match("person").Where("age", "LIKE", "3%"));
        Assert.Contains("Unknown operator", ex.Message);
    }

    [Fact]
    public void MatchWhereIn()
    {
        var result = QueryFixtures.Engine().Match("person")
            .Where("city", "IN", new List<string> { "NYC", "LA" })
            .Execute();
        Assert.Equal(5, result.Count);
    }

    [Fact]
    public void MatchChaining()
    {
        var result = QueryFixtures.Engine().Match("person")
            .Where("age", ">=", 25)
            .Where("city", "IN", new List<string> { "NYC", "LA" })
            .OrderBy("salary", "DESC")
            .Limit(5)
            .ReturnFields("name", "salary")
            .Execute();
        Assert.True(result.Count <= 5);
        Assert.Equal("Frank", PropertyValue.ValueText(result.Nodes[0].Properties["name"])); // highest salary
    }

    [Fact]
    public void FluentAndStringEquivalence()
    {
        var engine = QueryFixtures.Engine();
        var stringResult = engine.Execute("NODES person WHERE age > 30 ORDER BY age ASC LIMIT 2");
        var fluentResult = engine.Match("person")
            .Where("age", ">", 30).OrderBy("age", "ASC").Limit(2).Execute();

        Assert.Equal(stringResult.Count, fluentResult.Count);
        Assert.Equal(stringResult.Nodes.Select(n => n.Id), fluentResult.Nodes.Select(n => n.Id));
    }
}

public class EdgeQueryBuilderTests
{
    [Fact]
    public void MatchEdgesBasic()
    {
        var result = QueryFixtures.Engine().MatchEdges("KNOWS").Execute();
        Assert.Equal(6, result.Count);
    }

    [Fact]
    public void MatchEdgesWithWhere()
    {
        var result = QueryFixtures.Engine().MatchEdges("KNOWS")
            .Where("since", ">", 2019).Execute();
        Assert.Equal(2, result.Count);
        Assert.All(result.Edges, e => Assert.True(int.Parse(PropertyValue.ValueText(e.Properties["since"])) > 2019));
    }

    [Fact]
    public void MatchEdgesLimit()
    {
        var result = QueryFixtures.Engine().MatchEdges("KNOWS").Limit(3).Execute();
        Assert.Equal(3, result.Count);
    }

    [Fact]
    public void MatchEdgesAllTypes()
    {
        var result = QueryFixtures.Engine().MatchEdges().Execute();
        Assert.Equal(15, result.Count);
    }

    [Fact]
    public void MatchEdgesInvalidOperatorRaises()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().MatchEdges("KNOWS").Where("since", "LIKE", 2020));
        Assert.Contains("Unknown operator", ex.Message);
    }
}

public class QueryResultTests
{
    [Fact]
    public void ResultCounts()
    {
        var result = QueryFixtures.Engine().Execute("NODES person LIMIT 3");
        Assert.Equal(3, result.Count);
        Assert.Equal(3, result.Nodes.Count);
    }

    [Fact]
    public void ResultFirstNode()
    {
        var result = QueryFixtures.Engine().Execute("NODES person ORDER BY age ASC");
        var first = result.FirstNode();
        Assert.NotNull(first);
        Assert.Equal("25", PropertyValue.ValueText(first.Properties["age"])); // Bob is youngest
    }

    [Fact]
    public void ResultFirstNodeEmpty()
    {
        var result = QueryFixtures.Engine().Execute("NODES person WHERE age > 100");
        Assert.Null(result.FirstNode());
    }

    [Fact]
    public void ResultToStringIncludesCounts()
    {
        var result = QueryFixtures.Engine().Execute("NODES person");
        Assert.Contains("count=6", result.ToString());
        Assert.Contains("time=", result.ToString());
    }

    [Fact]
    public void ResultExecutionTime()
    {
        var result = QueryFixtures.Engine().Execute("NODES person");
        Assert.True(result.ExecutionTimeMs >= 0);
    }

    [Fact]
    public void ResultQueryStringPreserved()
    {
        const string query = "NODES person WHERE age > 25";
        var result = QueryFixtures.Engine().Execute(query);
        Assert.Equal(query, result.Query);
    }

    [Fact]
    public void ResultQueryType()
    {
        Assert.Equal("COUNT", QueryFixtures.Engine().Execute("COUNT person").QueryType);
        Assert.Equal("NODES", QueryFixtures.Engine().Execute("NODES person").QueryType);
        Assert.Equal("AVG", QueryFixtures.Engine().Execute("AVG person.age").QueryType);
    }
}

public class QueryErrorHandlingTests
{
    [Fact]
    public void InvalidQuerySyntax()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Execute("INVALID QUERY"));
        Assert.Contains("Unknown query type", ex.Message);
    }

    [Fact]
    public void ExecuteWrapsParseErrors()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Execute("NODES person WHERE name LIKE 'A%'"));
        Assert.Contains("Parse error", ex.Message);
    }

    [Fact]
    public void UnknownOperatorViaEngine()
    {
        Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Execute("NODES person WHERE age INVALID 25"));
    }

    [Fact]
    public void UnclosedListViaEngine()
    {
        Assert.Throws<ArgumentException>(
            () => QueryFixtures.Engine().Execute("NODES person WHERE city IN ('NYC', 'LA'"));
    }
}

public class QueryEdgeCaseTests
{
    [Fact]
    public void EmptyGraphNodes()
    {
        var engine = new QueryEngine(new ISONGraph());
        Assert.Equal(0, engine.Execute("NODES person").Count);
    }

    [Fact]
    public void EmptyGraphEdges()
    {
        var engine = new QueryEngine(new ISONGraph());
        Assert.Equal(0, engine.Execute("EDGES KNOWS").Count);
    }

    [Fact]
    public void EmptyGraphCount()
    {
        var engine = new QueryEngine(new ISONGraph());
        Assert.Equal(0L, engine.Execute("COUNT person").CountValue);
    }

    [Fact]
    public void SpecialCharactersInString()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("person", "special", Props.Of(("name", "O'Brien"), ("age", "45")));
        var result = engine.Execute("NODES person WHERE name CONTAINS Brien");
        Assert.Equal(1, result.Count);
    }

    [Fact]
    public void NumericStringId()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("item", "123", Props.Of(("name", "Item 123")));
        Assert.Equal(1, engine.Execute("NODES item").Count);
    }

    [Fact]
    public void UnicodeInProperties()
    {
        var engine = QueryFixtures.Engine();
        engine.Graph.AddNode("person", "unicode", Props.Of(("name", "日本語"), ("city", "東京")));
        var result = engine.Execute("NODES person WHERE name = 日本語");
        Assert.Equal(1, result.Count);
    }

    [Fact]
    public void QueryWithoutReturnKeepsAllProperties()
    {
        var result = QueryFixtures.Engine().Execute("NODES person LIMIT 1");
        var node = result.Nodes[0];
        Assert.True(node.Properties.ContainsKey("name"));
        Assert.True(node.Properties.ContainsKey("city"));
        Assert.True(node.Properties.ContainsKey("salary"));
    }

    [Fact]
    public void ComplexMultiConditionQuery()
    {
        var result = QueryFixtures.Engine().Execute(
            "NODES person WHERE age >= 25 AND age <= 35 AND city = NYC ORDER BY age DESC LIMIT 2");
        Assert.True(result.Count <= 2);
        foreach (var node in result.Nodes)
        {
            var age = int.Parse(PropertyValue.ValueText(node.Properties["age"]));
            Assert.InRange(age, 25, 35);
        }
    }
}

public class QueryIntegrationTests
{
    [Fact]
    public void FullWorkflow()
    {
        var graph = new ISONGraph();
        graph.AddNode("user", "1", Props.Of(("name", "Alice"), ("score", "100")));
        graph.AddNode("user", "2", Props.Of(("name", "Bob"), ("score", "85")));
        graph.AddNode("user", "3", Props.Of(("name", "Charlie"), ("score", "92")));
        graph.AddEdge("FOLLOWS", new("user", "1"), new("user", "2"));
        graph.AddEdge("FOLLOWS", new("user", "2"), new("user", "3"));

        var engine = new QueryEngine(graph);

        Assert.Equal(2, engine.Execute("NODES user WHERE score > 90").Count);
        Assert.Equal(3L, engine.Execute("COUNT user").CountValue);

        var avg = engine.Execute("AVG user.score");
        Assert.NotNull(avg.Value);
        Assert.True(Math.Abs(avg.Value.Value - 92.33) < 1);

        Assert.True(engine.Execute("TRAVERSE user:1 -> FOLLOWS -> user MAX 2").Count >= 1);

        var path = engine.Execute("PATH user:1 TO user:3 VIA FOLLOWS");
        Assert.Equal(1, path.Count);
    }

    [Fact]
    public void QueryAfterGraphModification()
    {
        var engine = QueryFixtures.Engine();
        var initial = engine.Execute("COUNT person").CountValue;

        engine.Graph.AddNode("person", "100",
            Props.Of(("name", "NewPerson"), ("age", "50"), ("city", "Boston"), ("salary", "70000")));

        Assert.Equal(initial + 1, engine.Execute("COUNT person").CountValue);
        Assert.Equal(1, engine.Execute("NODES person WHERE city = Boston").Count);
    }

    [Fact]
    public void MultipleEnginesSameGraph()
    {
        var graph = QueryFixtures.SocialGraph();
        var engine1 = new QueryEngine(graph);
        var engine2 = new QueryEngine(graph);
        Assert.Equal(engine1.Execute("COUNT person").CountValue,
                     engine2.Execute("COUNT person").CountValue);
    }

    [Fact]
    public void LargeResultSet()
    {
        var graph = new ISONGraph();
        for (var i = 0; i < 100; i++)
        {
            graph.AddNode("item", i.ToString(),
                Props.Of(("value", i.ToString()), ("category", (i % 10).ToString())));
        }
        var engine = new QueryEngine(graph);
        Assert.Equal(100, engine.Execute("NODES item").Count);
        Assert.Equal(10, engine.Execute("NODES item WHERE category = 3").Count);
    }

    [Fact]
    public void ManyConditions()
    {
        var graph = new ISONGraph();
        graph.AddNode("data", "1",
            Props.Of(("a", "1"), ("b", "2"), ("c", "3"), ("d", "4"), ("e", "5")));
        var engine = new QueryEngine(graph);
        var result = engine.Execute(
            "NODES data WHERE a = 1 AND b = 2 AND c = 3 AND d = 4 AND e = 5");
        Assert.Equal(1, result.Count);
    }

    [Fact]
    public void DeepTraversalPath()
    {
        var graph = new ISONGraph();
        for (var i = 1; i <= 20; i++)
            graph.AddNode("node", i.ToString());
        for (var i = 1; i < 20; i++)
            graph.AddEdge("NEXT", new("node", i.ToString()), new("node", (i + 1).ToString()));

        var engine = new QueryEngine(graph);
        var result = engine.Execute("PATH node:1 TO node:20 VIA NEXT MAX 25");
        Assert.Equal(1, result.Count);
        Assert.Equal(19, result.Paths[0].Length);
    }
}
