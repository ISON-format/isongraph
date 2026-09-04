/**
 * ISONQL C++ Tests
 *
 * Comprehensive tests for ISONQL query language.
 */

#include <iostream>
#include <string>
#include <cassert>
#include <cmath>
#include "../include/isonql.hpp"

using namespace isonql;
using namespace ison_graph;

int passed = 0;
int failed = 0;

#define TEST(name) void test_##name()
#define RUN_TEST(name) do { \
    std::cout << "Running " << #name << "... "; \
    try { \
        test_##name(); \
        std::cout << "PASSED" << std::endl; \
        passed++; \
    } catch (const std::exception& e) { \
        std::cout << "FAILED: " << e.what() << std::endl; \
        failed++; \
    } catch (...) { \
        std::cout << "FAILED: Unknown exception" << std::endl; \
        failed++; \
    } \
} while(0)

#define ASSERT_TRUE(cond) do { if (!(cond)) throw std::runtime_error("Assertion failed: " #cond); } while(0)
#define ASSERT_FALSE(cond) ASSERT_TRUE(!(cond))
#define ASSERT_EQ(a, b) do { if ((a) != (b)) throw std::runtime_error("Assertion failed: " #a " == " #b); } while(0)
#define ASSERT_NEAR(a, b, eps) do { if (std::abs((a) - (b)) > (eps)) throw std::runtime_error("Assertion failed: " #a " ~= " #b); } while(0)

// Helper to create test graph
ISONGraph createTestGraph() {
    ISONGraph graph;

    // Add people
    graph.addNode("person", "alice", {{"name", "Alice"}, {"age", "30"}, {"city", "NYC"}});
    graph.addNode("person", "bob", {{"name", "Bob"}, {"age", "25"}, {"city", "LA"}});
    graph.addNode("person", "charlie", {{"name", "Charlie"}, {"age", "35"}, {"city", "NYC"}});
    graph.addNode("person", "diana", {{"name", "Diana"}, {"age", "28"}, {"city", "Chicago"}});

    // Add posts
    graph.addNode("post", "p1", {{"title", "Hello World"}, {"likes", "10"}});
    graph.addNode("post", "p2", {{"title", "Graph Databases"}, {"likes", "25"}});
    graph.addNode("post", "p3", {{"title", "ISONQL Guide"}, {"likes", "15"}});

    // Add KNOWS edges
    graph.addEdge("KNOWS", {"person", "alice"}, {"person", "bob"}, {{"since", "2020"}});
    graph.addEdge("KNOWS", {"person", "alice"}, {"person", "charlie"}, {{"since", "2019"}});
    graph.addEdge("KNOWS", {"person", "bob"}, {"person", "diana"}, {{"since", "2021"}});
    graph.addEdge("KNOWS", {"person", "charlie"}, {"person", "diana"}, {{"since", "2018"}});

    // Add AUTHORED edges
    graph.addEdge("AUTHORED", {"person", "alice"}, {"post", "p1"}, {});
    graph.addEdge("AUTHORED", {"person", "bob"}, {"post", "p2"}, {});
    graph.addEdge("AUTHORED", {"person", "charlie"}, {"post", "p3"}, {});

    // Add LIKES edges
    graph.addEdge("LIKES", {"person", "alice"}, {"post", "p2"}, {});
    graph.addEdge("LIKES", {"person", "bob"}, {"post", "p1"}, {});
    graph.addEdge("LIKES", {"person", "diana"}, {"post", "p3"}, {});

    return graph;
}

// =============================================================================
// NODES Query Tests
// =============================================================================

TEST(nodes_all) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person");
    ASSERT_EQ(result.count, 4);
    ASSERT_EQ(result.totalCount, 4);
}

TEST(nodes_where_eq) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE city = NYC");
    ASSERT_EQ(result.count, 2);  // Alice and Charlie

    auto nodes = result.toNodes();
    for (const auto& node : nodes) {
        ASSERT_EQ(ison_graph::valueToText(node.properties.at("city")), "NYC");
    }
}

TEST(nodes_where_gt) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE age > 28");
    ASSERT_EQ(result.count, 2);  // Alice (30) and Charlie (35)
}

TEST(nodes_where_lt) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE age < 30");
    ASSERT_EQ(result.count, 2);  // Bob (25) and Diana (28)
}

TEST(nodes_where_ne) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE city != NYC");
    ASSERT_EQ(result.count, 2);  // Bob (LA) and Diana (Chicago)
}

TEST(nodes_order_by_asc) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person ORDER BY age ASC");
    auto nodes = result.toNodes();
    ASSERT_EQ(nodes.size(), 4);
    ASSERT_EQ(ison_graph::valueToText(nodes[0].properties.at("name")), "Bob");      // 25
    ASSERT_EQ(ison_graph::valueToText(nodes[1].properties.at("name")), "Diana");    // 28
    ASSERT_EQ(ison_graph::valueToText(nodes[2].properties.at("name")), "Alice");    // 30
    ASSERT_EQ(ison_graph::valueToText(nodes[3].properties.at("name")), "Charlie");  // 35
}

TEST(nodes_order_by_desc) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person ORDER BY age DESC");
    auto nodes = result.toNodes();
    ASSERT_EQ(nodes.size(), 4);
    ASSERT_EQ(ison_graph::valueToText(nodes[0].properties.at("name")), "Charlie");  // 35
    ASSERT_EQ(ison_graph::valueToText(nodes[3].properties.at("name")), "Bob");      // 25
}

TEST(nodes_limit) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person LIMIT 2");
    ASSERT_EQ(result.count, 2);
    ASSERT_EQ(result.totalCount, 4);
}

TEST(nodes_offset) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person ORDER BY name ASC LIMIT 2 OFFSET 1");
    auto nodes = result.toNodes();
    ASSERT_EQ(nodes.size(), 2);
    // Names sorted: Alice, Bob, Charlie, Diana
    // After offset 1: Bob, Charlie
    ASSERT_EQ(ison_graph::valueToText(nodes[0].properties.at("name")), "Bob");
    ASSERT_EQ(ison_graph::valueToText(nodes[1].properties.at("name")), "Charlie");
}

TEST(nodes_multiple_conditions) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE city = NYC AND age > 30");
    ASSERT_EQ(result.count, 1);  // Only Charlie (35, NYC)
}

TEST(nodes_where_or) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // OR must be a real OR, not evaluated as AND
    auto result = engine.execute("NODES person WHERE city = NYC OR city = LA");
    ASSERT_EQ(result.count, 3);  // Alice (NYC), Charlie (NYC), Bob (LA)

    auto result2 = engine.execute("NODES person WHERE city = LA OR city = Chicago");
    ASSERT_EQ(result2.count, 2);  // Bob, Diana
}

TEST(nodes_where_or_and_precedence) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // AND binds tighter than OR: (city = NYC AND age > 30) OR city = LA
    auto result = engine.execute("NODES person WHERE city = NYC AND age > 30 OR city = LA");
    ASSERT_EQ(result.count, 2);  // Charlie (NYC, 35) and Bob (LA)

    // (city = NYC AND age > 100) OR (city = Chicago AND age < 30)
    auto result2 = engine.execute("NODES person WHERE city = NYC AND age > 100 OR city = Chicago AND age < 30");
    ASSERT_EQ(result2.count, 1);  // Diana (Chicago, 28)
}

TEST(count_where_or) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("COUNT person WHERE age < 26 OR age > 34");
    ASSERT_EQ(result.toInt().value(), 2);  // Bob (25) and Charlie (35)
}

// =============================================================================
// EDGES Query Tests
// =============================================================================

TEST(edges_all) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("EDGES");
    // KNOWS: 4, AUTHORED: 3, LIKES: 3 = 10 total
    ASSERT_EQ(result.count, 10);
}

TEST(edges_by_type) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("EDGES KNOWS");
    ASSERT_EQ(result.count, 4);

    auto edges = result.toEdges();
    for (const auto& edge : edges) {
        ASSERT_EQ(edge.relType, "KNOWS");
    }
}

TEST(edges_where) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("EDGES KNOWS WHERE since > 2019");
    ASSERT_EQ(result.count, 2);  // since 2020 and 2021
}

TEST(edges_limit) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("EDGES LIMIT 3");
    ASSERT_EQ(result.count, 3);
}

// =============================================================================
// TRAVERSE Query Tests
// =============================================================================

TEST(traverse_single_hop) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("TRAVERSE person:alice -> KNOWS -> person");
    auto refs = result.toNodeRefs();

    // Alice knows Bob and Charlie
    ASSERT_EQ(refs.size(), 2);
}

TEST(traverse_multi_hop) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // From Alice, through KNOWS, then another KNOWS
    auto result = engine.execute("TRAVERSE person:alice -> KNOWS -> person -> KNOWS -> person");
    auto refs = result.toNodeRefs();

    // Alice -> Bob -> Diana, Alice -> Charlie -> Diana
    // Diana is reachable (deduplicated)
    ASSERT_TRUE(refs.size() >= 1);
}

TEST(traverse_with_limit) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("TRAVERSE person:alice -> KNOWS -> person LIMIT 1");
    ASSERT_EQ(result.count, 1);
}

// =============================================================================
// PATH Query Tests
// =============================================================================

TEST(path_direct) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("PATH person:alice TO person:bob VIA KNOWS");
    ASSERT_EQ(result.count, 1);

    auto paths = std::get<std::vector<PathResult>>(result.data);
    ASSERT_EQ(paths[0].length, 1);  // Direct connection
}

TEST(path_indirect) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("PATH person:alice TO person:diana VIA KNOWS");
    ASSERT_EQ(result.count, 1);

    auto paths = std::get<std::vector<PathResult>>(result.data);
    ASSERT_TRUE(paths[0].length >= 2);  // Alice -> Bob/Charlie -> Diana
}

TEST(path_no_connection) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // Alice and post p2 are connected via LIKES, not KNOWS
    auto result = engine.execute("PATH person:alice TO post:p2 VIA KNOWS");
    ASSERT_EQ(result.count, 0);  // No path via KNOWS
}

// =============================================================================
// COUNT Query Tests
// =============================================================================

TEST(count_all) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("COUNT person");
    ASSERT_TRUE(result.toInt().has_value());
    ASSERT_EQ(result.toInt().value(), 4);
}

TEST(count_where) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("COUNT person WHERE age > 28");
    ASSERT_EQ(result.toInt().value(), 2);  // Alice and Charlie
}

TEST(count_posts) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("COUNT post");
    ASSERT_EQ(result.toInt().value(), 3);
}

// =============================================================================
// Aggregation Query Tests
// =============================================================================

TEST(sum_age) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("SUM person.age");
    // 30 + 25 + 35 + 28 = 118
    ASSERT_NEAR(result.toDouble().value(), 118.0, 0.001);
}

TEST(avg_age) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("AVG person.age");
    // 118 / 4 = 29.5
    ASSERT_NEAR(result.toDouble().value(), 29.5, 0.001);
}

TEST(min_age) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("MIN person.age");
    ASSERT_NEAR(result.toDouble().value(), 25.0, 0.001);  // Bob
}

TEST(max_age) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("MAX person.age");
    ASSERT_NEAR(result.toDouble().value(), 35.0, 0.001);  // Charlie
}

TEST(avg_with_where) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("AVG person.age WHERE city = NYC");
    // Alice (30) and Charlie (35) -> avg = 32.5
    ASSERT_NEAR(result.toDouble().value(), 32.5, 0.001);
}

TEST(sum_likes) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("SUM post.likes");
    // 10 + 25 + 15 = 50
    ASSERT_NEAR(result.toDouble().value(), 50.0, 0.001);
}

// =============================================================================
// Fluent API Tests
// =============================================================================

TEST(fluent_nodes_basic) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.match("person").execute();
    ASSERT_EQ(result.count, 4);
}

TEST(fluent_nodes_where) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.match("person")
        .where("age", ">", static_cast<int64_t>(28))
        .execute();
    ASSERT_EQ(result.count, 2);  // Alice and Charlie
}

TEST(fluent_nodes_order_limit) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.match("person")
        .orderBy("age", "DESC")
        .limit(2)
        .execute();

    auto nodes = result.toNodes();
    ASSERT_EQ(nodes.size(), 2);
    ASSERT_EQ(ison_graph::valueToText(nodes[0].properties.at("name")), "Charlie");  // 35
    ASSERT_EQ(ison_graph::valueToText(nodes[1].properties.at("name")), "Alice");    // 30
}

TEST(fluent_nodes_count) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto count = engine.match("person")
        .where("city", "=", std::string("NYC"))
        .count();
    ASSERT_EQ(count, 2);
}

TEST(fluent_edges_basic) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.matchEdges("KNOWS").execute();
    ASSERT_EQ(result.count, 4);
}

TEST(fluent_edges_where) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.matchEdges("KNOWS")
        .where("since", ">=", std::string("2020"))
        .execute();
    ASSERT_EQ(result.count, 2);  // 2020 and 2021
}

TEST(fluent_offset_and_return) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // offset() and returnFields() must not be silently ignored by the builder
    auto result = engine.match("person")
        .orderBy("name", "ASC")
        .limit(2)
        .offset(1)
        .returnFields({"name"})
        .execute();

    auto nodes = result.toNodes();
    ASSERT_EQ(nodes.size(), 2);
    // Sorted: Alice, Bob, Charlie, Diana; after OFFSET 1: Bob, Charlie
    ASSERT_EQ(ison_graph::valueToText(nodes[0].properties.at("name")), "Bob");
    ASSERT_EQ(ison_graph::valueToText(nodes[1].properties.at("name")), "Charlie");

    // RETURN projection: only the requested field remains
    for (const auto& node : nodes) {
        ASSERT_EQ(node.properties.size(), 1);
        ASSERT_TRUE(node.properties.count("name") == 1);
    }
}

TEST(fluent_where_value_with_spaces) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    // Condition::toString must quote string values so the regenerated
    // query survives values containing spaces
    auto result = engine.match("post")
        .where("title", "=", std::string("Hello World"))
        .execute();
    ASSERT_EQ(result.count, 1);

    auto count = engine.match("post")
        .where("title", "=", std::string("Graph Databases"))
        .count();
    ASSERT_EQ(count, 1);
}

// =============================================================================
// Condition Tests
// =============================================================================

TEST(condition_contains) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES post WHERE title CONTAINS Graph");
    ASSERT_EQ(result.count, 1);  // "Graph Databases"
}

TEST(condition_starts_with) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES post WHERE title STARTS_WITH Hello");
    ASSERT_EQ(result.count, 1);  // "Hello World"
}

TEST(condition_ends_with) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES post WHERE title ENDS_WITH Guide");
    ASSERT_EQ(result.count, 1);  // "ISONQL Guide"
}

TEST(condition_exists) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE EXISTS city");
    ASSERT_EQ(result.count, 4);  // All have city
}

TEST(condition_exists_postfix) {
    auto graph = createTestGraph();
    graph.addNode("person", "eve", {{"name", "Eve"}});  // no city
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE city EXISTS");
    ASSERT_EQ(result.count, 4);

    auto missing = engine.execute("NODES person WHERE city NOT EXISTS");
    ASSERT_EQ(missing.count, 1);
}

TEST(condition_not_in) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    auto result = engine.execute("NODES person WHERE city NOT IN ('NYC')");
    ASSERT_EQ(result.count, 2);  // Bob (LA), Diana (Chicago)
}

// =============================================================================
// Error Handling Tests
// =============================================================================

TEST(error_unknown_operator) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    bool threw = false;
    try {
        engine.execute("NODES person WHERE name LIKE 'A'");
    } catch (const std::runtime_error&) {
        threw = true;
    }
    ASSERT_TRUE(threw);
}

TEST(error_unclosed_list) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    bool threw = false;
    try {
        engine.execute("NODES person WHERE city IN ('NYC', 'LA'");
    } catch (const std::runtime_error&) {
        threw = true;
    }
    ASSERT_TRUE(threw);
}

TEST(error_invalid_query) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    bool threw = false;
    try {
        engine.execute("INVALID_KEYWORD");
    } catch (const std::runtime_error&) {
        threw = true;
    }
    ASSERT_TRUE(threw);
}

TEST(error_missing_to_in_path) {
    auto graph = createTestGraph();
    QueryEngine engine(graph);

    bool threw = false;
    try {
        engine.execute("PATH person:alice person:bob");
    } catch (const std::runtime_error&) {
        threw = true;
    }
    ASSERT_TRUE(threw);
}

// =============================================================================
// Main
// =============================================================================

int main() {
    std::cout << "=== ISONQL C++ Tests ===" << std::endl << std::endl;

    // NODES tests
    RUN_TEST(nodes_all);
    RUN_TEST(nodes_where_eq);
    RUN_TEST(nodes_where_gt);
    RUN_TEST(nodes_where_lt);
    RUN_TEST(nodes_where_ne);
    RUN_TEST(nodes_order_by_asc);
    RUN_TEST(nodes_order_by_desc);
    RUN_TEST(nodes_limit);
    RUN_TEST(nodes_offset);
    RUN_TEST(nodes_multiple_conditions);
    RUN_TEST(nodes_where_or);
    RUN_TEST(nodes_where_or_and_precedence);
    RUN_TEST(count_where_or);

    // EDGES tests
    RUN_TEST(edges_all);
    RUN_TEST(edges_by_type);
    RUN_TEST(edges_where);
    RUN_TEST(edges_limit);

    // TRAVERSE tests
    RUN_TEST(traverse_single_hop);
    RUN_TEST(traverse_multi_hop);
    RUN_TEST(traverse_with_limit);

    // PATH tests
    RUN_TEST(path_direct);
    RUN_TEST(path_indirect);
    RUN_TEST(path_no_connection);

    // COUNT tests
    RUN_TEST(count_all);
    RUN_TEST(count_where);
    RUN_TEST(count_posts);

    // Aggregation tests
    RUN_TEST(sum_age);
    RUN_TEST(avg_age);
    RUN_TEST(min_age);
    RUN_TEST(max_age);
    RUN_TEST(avg_with_where);
    RUN_TEST(sum_likes);

    // Fluent API tests
    RUN_TEST(fluent_nodes_basic);
    RUN_TEST(fluent_nodes_where);
    RUN_TEST(fluent_nodes_order_limit);
    RUN_TEST(fluent_nodes_count);
    RUN_TEST(fluent_edges_basic);
    RUN_TEST(fluent_edges_where);
    RUN_TEST(fluent_offset_and_return);
    RUN_TEST(fluent_where_value_with_spaces);

    // Condition tests
    RUN_TEST(condition_contains);
    RUN_TEST(condition_starts_with);
    RUN_TEST(condition_ends_with);
    RUN_TEST(condition_exists);
    RUN_TEST(condition_exists_postfix);
    RUN_TEST(condition_not_in);

    // Error handling tests
    RUN_TEST(error_invalid_query);
    RUN_TEST(error_missing_to_in_path);
    RUN_TEST(error_unknown_operator);
    RUN_TEST(error_unclosed_list);

    std::cout << std::endl << "=== Results ===" << std::endl;
    std::cout << "Total: " << (passed + failed) << ", Passed: " << passed << ", Failed: " << failed << std::endl;

    return failed > 0 ? 1 : 0;
}
