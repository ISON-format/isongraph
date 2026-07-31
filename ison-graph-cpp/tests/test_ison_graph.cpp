/**
 * Tests for ison-graph-cpp
 */

#include "../include/ison_graph.hpp"
#include <iostream>
#include <cassert>
#include <stdexcept>

using namespace ison_graph;

// Test helpers
#define TEST(name) void test_##name()
#define RUN_TEST(name) do { \
    std::cout << "Running " #name "... "; \
    try { \
        test_##name(); \
        std::cout << "PASSED" << std::endl; \
    } catch (const std::exception& e) { \
        std::cout << "FAILED: " << e.what() << std::endl; \
        failed++; \
    } \
    total++; \
} while(0)

// =============================================================================
// Node Tests
// =============================================================================

TEST(add_and_get_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}, {"age", "30"}});

    const Node& node = graph.getNode("person", "1");
    assert(node.type == "person");
    assert(node.id == "1");
    assert(node.properties.at("name") == "Alice");
    assert(node.properties.at("age") == "30");
}

TEST(duplicate_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1");

    bool threw = false;
    try {
        graph.addNode("person", "1");
    } catch (const DuplicateNodeError&) {
        threw = true;
    }
    assert(threw);
}

TEST(node_not_found) {
    ISONGraph graph("test");

    bool threw = false;
    try {
        graph.getNode("person", "999");
    } catch (const NodeNotFoundError&) {
        threw = true;
    }
    assert(threw);
}

TEST(has_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1");

    assert(graph.hasNode("person", "1"));
    assert(!graph.hasNode("person", "999"));
}

TEST(remove_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    graph.removeNode("person", "1");
    assert(!graph.hasNode("person", "1"));
    assert(graph.edgeCount() == 0);
}

TEST(update_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.updateNode("person", "1", {{"age", "31"}});

    const Node& node = graph.getNode("person", "1");
    assert(node.properties.at("name") == "Alice");
    assert(node.properties.at("age") == "31");
}

TEST(node_count) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("company", "100");

    assert(graph.nodeCount() == 3);
    assert(graph.nodeCount("person") == 2);
    assert(graph.nodeCount("company") == 1);
}

TEST(node_types) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("company", "100");

    auto types = graph.nodeTypes();
    assert(types.size() == 2);
}

// =============================================================================
// Edge Tests
// =============================================================================

TEST(add_and_has_edge) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"since", "2020"}});

    assert(graph.hasEdge("KNOWS", {"person", "1"}, {"person", "2"}));
    assert(!graph.hasEdge("KNOWS", {"person", "2"}, {"person", "1"}));
}

TEST(edge_to_nonexistent_node) {
    ISONGraph graph("test");
    graph.addNode("person", "1");

    bool threw = false;
    try {
        graph.addEdge("KNOWS", {"person", "1"}, {"person", "999"});
    } catch (const NodeNotFoundError&) {
        threw = true;
    }
    assert(threw);
}

TEST(duplicate_edge) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    bool threw = false;
    try {
        graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    } catch (const DuplicateEdgeError&) {
        threw = true;
    }
    assert(threw);
}

TEST(remove_edge) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    graph.removeEdge("KNOWS", {"person", "1"}, {"person", "2"});
    assert(!graph.hasEdge("KNOWS", {"person", "1"}, {"person", "2"}));
}

TEST(edge_count) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addNode("company", "100");

    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});
    graph.addEdge("WORKS_AT", {"person", "1"}, {"company", "100"});

    assert(graph.edgeCount() == 3);
    assert(graph.edgeCount("KNOWS") == 2);
}

TEST(undirected_add_edge_returns_forward_edge) {
    ISONGraph graph("test", false);  // undirected
    graph.addNode("person", "1");
    graph.addNode("person", "2");

    // addEdge returns the FORWARD edge by value (not a dangling reference to
    // the reverse edge that undirected graphs also store)
    Edge edge = graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"since", "2020"}});
    assert(edge.source.id == "1");
    assert(edge.target.id == "2");
    assert(edge.relType == "KNOWS");
    assert(edge.properties.at("since") == "2020");

    // Both directions stored
    assert(graph.hasEdge("KNOWS", {"person", "1"}, {"person", "2"}));
    assert(graph.hasEdge("KNOWS", {"person", "2"}, {"person", "1"}));
}

TEST(undirected_remove_edge_removes_both_directions) {
    ISONGraph graph("test", false);  // undirected
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    graph.removeEdge("KNOWS", {"person", "1"}, {"person", "2"});
    assert(!graph.hasEdge("KNOWS", {"person", "1"}, {"person", "2"}));
    assert(!graph.hasEdge("KNOWS", {"person", "2"}, {"person", "1"}));
    assert(graph.edgeCount() == 0);

    // Removing by the reverse direction also removes both
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.removeEdge("KNOWS", {"person", "2"}, {"person", "1"});
    assert(!graph.hasEdge("KNOWS", {"person", "1"}, {"person", "2"}));
    assert(!graph.hasEdge("KNOWS", {"person", "2"}, {"person", "1"}));
    assert(graph.edgeCount() == 0);
}

TEST(node_type_id_with_colon_rejected) {
    ISONGraph graph("test");

    bool threw = false;
    try {
        graph.addNode("per:son", "1");
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    assert(threw);

    threw = false;
    try {
        graph.addNode("person", "1:2");
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    assert(threw);

    assert(graph.nodeCount() == 0);
}

// =============================================================================
// Traversal Tests
// =============================================================================

TEST(neighbors) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "3"});

    auto friends = graph.neighbors({"person", "1"}, "KNOWS");
    assert(friends.size() == 2);
}

TEST(neighbors_both_directions) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "2"});

    auto connections = graph.neighbors({"person", "2"}, "KNOWS", Direction::Both);
    assert(connections.size() == 2);
}

TEST(multi_hop) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});

    auto twoHops = graph.multiHop({"person", "1"}, "KNOWS", 2);
    assert(twoHops.size() == 1);
    assert(twoHops[0].id == "3");
}

TEST(multi_hop_range) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addNode("person", "4");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "4"});

    auto inRange = graph.multiHopRange({"person", "1"}, "KNOWS", 1, 3);
    assert(inRange.size() == 3);
}

// =============================================================================
// Path Finding Tests
// =============================================================================

TEST(shortest_path) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});

    auto path = graph.shortestPath({"person", "1"}, {"person", "3"}, "KNOWS");
    assert(path.has_value());
    assert(path->length() == 2);
    assert(path->nodes.size() == 3);
}

TEST(no_path) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");

    auto path = graph.shortestPath({"person", "1"}, {"person", "2"});
    assert(!path.has_value());
}

TEST(path_exists) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    assert(graph.pathExists({"person", "1"}, {"person", "2"}));
    assert(!graph.pathExists({"person", "1"}, {"person", "3"}));
}

// =============================================================================
// Graph Analysis Tests
// =============================================================================

TEST(degree) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "2"});

    assert(graph.outDegree({"person", "1"}) == 1);
    assert(graph.inDegree({"person", "2"}) == 2);
}

TEST(is_connected) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    assert(graph.isConnected());

    graph.addNode("person", "3");
    assert(!graph.isConnected());
}

// =============================================================================
// Serialization Tests
// =============================================================================

TEST(to_ison) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    std::string ison = graph.toIson();
    assert(ison.find("nodes.person") != std::string::npos);
    assert(ison.find("edges.KNOWS") != std::string::npos);
    assert(ison.find("Alice") != std::string::npos);
}

TEST(to_isonl) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "1"});  // self-loop for simplicity

    std::string isonl = graph.toIsonl();
    assert(isonl.find("nodes.person|") != std::string::npos);
    assert(isonl.find("edges.KNOWS|") != std::string::npos);
}

// =============================================================================
// Fluent API Tests
// =============================================================================

TEST(fluent_traversal) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("company", "100");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("WORKS_AT", {"person", "2"}, {"company", "100"});

    auto result = GraphTraversal(graph, {"person", "1"})
        .hop("KNOWS")
        .hop("WORKS_AT")
        .collect();

    assert(result.size() == 1);
    assert(result[0].type == "company");
    assert(result[0].id == "100");
}

TEST(fluent_count) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});

    size_t count = GraphTraversal(graph, {"person", "1"})
        .hops(2, "KNOWS")
        .count();

    assert(count == 1);
}

TEST(fluent_filter) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addNode("person", "3", {{"name", "Charlie"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "3"});

    auto result = GraphTraversal(graph, {"person", "1"})
        .hop("KNOWS")
        .filter([](const Node& n) { return n.properties.at("name") == "Bob"; })
        .collect();

    assert(result.size() == 1);
    assert(result[0].id == "2");
}

// =============================================================================
// Deserialization Tests
// =============================================================================

TEST(from_ison) {
    std::string isonText = R"(
nodes.person
id name age
alice Alice 30
bob Bob 25

edges.KNOWS
source target since
:person:alice :person:bob 2020
)";

    auto graph = ISONGraph::fromIson(isonText, "test");
    assert(graph.nodeCount() == 2);
    assert(graph.edgeCount() == 1);
    assert(graph.hasNode("person", "alice"));
    assert(graph.hasNode("person", "bob"));
    assert(graph.hasEdge("KNOWS", {"person", "alice"}, {"person", "bob"}));
}

TEST(from_isonl) {
    std::string isonlText =
        "nodes.person|id name age|alice Alice 30\n"
        "nodes.person|id name age|bob Bob 25\n"
        "edges.KNOWS|source target since|:person:alice :person:bob 2020\n";

    auto graph = ISONGraph::fromIsonl(isonlText, "test");
    assert(graph.nodeCount() == 2);
    assert(graph.edgeCount() == 1);
    assert(graph.hasNode("person", "alice"));
    assert(graph.hasEdge("KNOWS", {"person", "alice"}, {"person", "bob"}));
}

TEST(ison_roundtrip_special_values) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {
        {"name", "Alice Smith"},          // space
        {"bio", "likes|pipes"},           // pipe
        {"note", "line1\nline2"},         // newline
        {"nick", ""},                     // empty
        {"quote", "she said \"hi\""}      // embedded quotes
    });
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"how", "at a party"}});

    auto restored = ISONGraph::fromIson(graph.toIson(), "test");
    assert(restored.nodeCount() == 2);
    assert(restored.edgeCount() == 1);
    const Node& node = restored.getNode("person", "1");
    assert(node.properties.at("name") == "Alice Smith");
    assert(node.properties.at("bio") == "likes|pipes");
    assert(node.properties.at("note") == "line1\nline2");
    assert(node.properties.at("nick") == "");
    assert(node.properties.at("quote") == "she said \"hi\"");
    auto edge = restored.getEdge("KNOWS", {"person", "1"}, {"person", "2"});
    assert(edge.properties.at("how") == "at a party");
}

TEST(isonl_roundtrip_special_values) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {
        {"name", "Alice Smith"},
        {"bio", "likes|pipes"},
        {"note", "line1\nline2"},
        {"nick", ""}
    });
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"how", "at a party"}, {"tag", "a|b"}});

    auto restored = ISONGraph::fromIsonl(graph.toIsonl(), "test");
    assert(restored.nodeCount() == 2);
    assert(restored.edgeCount() == 1);
    const Node& node = restored.getNode("person", "1");
    assert(node.properties.at("name") == "Alice Smith");
    assert(node.properties.at("bio") == "likes|pipes");
    assert(node.properties.at("note") == "line1\nline2");
    assert(node.properties.at("nick") == "");
    auto edge = restored.getEdge("KNOWS", {"person", "1"}, {"person", "2"});
    assert(edge.properties.at("how") == "at a party");
    assert(edge.properties.at("tag") == "a|b");
}

TEST(from_ison_missing_id_column_throws) {
    std::string isonText =
        "nodes.person\n"
        "name age\n"
        "Alice 30\n";

    bool threw = false;
    try {
        ISONGraph::fromIson(isonText, "test");
    } catch (const GraphError&) {
        threw = true;
    }
    assert(threw);
}

TEST(from_isonl_missing_id_column_throws) {
    std::string isonlText = "nodes.person|name age|Alice 30\n";

    bool threw = false;
    try {
        ISONGraph::fromIsonl(isonlText, "test");
    } catch (const GraphError&) {
        threw = true;
    }
    assert(threw);
}

TEST(from_ison_edge_before_node_throws) {
    std::string isonText =
        "edges.KNOWS\n"
        "source target\n"
        ":person:alice :person:bob\n";

    bool threw = false;
    try {
        ISONGraph::fromIson(isonText, "test");
    } catch (const GraphError&) {
        threw = true;
    }
    assert(threw);
}

// =============================================================================
// Additional Analysis Tests
// =============================================================================

TEST(has_cycle) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});

    assert(!graph.hasCycle());

    // Create a cycle
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "1"});
    assert(graph.hasCycle());
}

TEST(has_cycle_undirected_single_edge_no_false_positive) {
    ISONGraph graph("test", false);  // undirected
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    // A single undirected edge (stored as two directed edges) is NOT a cycle
    assert(!graph.hasCycle());

    // A chain is not a cycle either
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});
    assert(!graph.hasCycle());

    // Closing the triangle IS a cycle
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "1"});
    assert(graph.hasCycle());
}

TEST(has_cycle_per_rel_type) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "1"});  // cycle in KNOWS
    graph.addEdge("LIKES", {"person", "1"}, {"person", "2"});  // no cycle in LIKES

    assert(graph.hasCycle());
    assert(graph.hasCycle("KNOWS"));
    assert(!graph.hasCycle("LIKES"));
}

TEST(has_cycle_deep_chain_iterative) {
    // Deep chain: recursive DFS would overflow the stack; iterative must not
    ISONGraph graph("test");
    const int N = 30000;
    for (int i = 0; i < N; ++i) {
        graph.addNode("n", std::to_string(i));
    }
    for (int i = 0; i + 1 < N; ++i) {
        graph.addEdge("NEXT", {"n", std::to_string(i)}, {"n", std::to_string(i + 1)});
    }
    assert(!graph.hasCycle());

    graph.addEdge("NEXT", {"n", std::to_string(N - 1)}, {"n", "0"});
    assert(graph.hasCycle());
}

TEST(all_paths_deep_chain_iterative) {
    // Deep single path: recursive DFS would overflow the stack; iterative must not
    ISONGraph graph("test");
    const int N = 30000;
    for (int i = 0; i < N; ++i) {
        graph.addNode("n", std::to_string(i));
    }
    for (int i = 0; i + 1 < N; ++i) {
        graph.addEdge("NEXT", {"n", std::to_string(i)}, {"n", std::to_string(i + 1)});
    }

    auto paths = graph.allPaths({"n", "0"}, {"n", std::to_string(N - 1)}, "NEXT", N);
    assert(paths.size() == 1);
    assert(paths[0].length() == static_cast<size_t>(N - 1));
}

TEST(connected_components) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addNode("person", "4");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "3"}, {"person", "4"});

    auto components = graph.connectedComponents();
    assert(components.size() == 2);
}

TEST(all_paths) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "3"});

    auto paths = graph.allPaths({"person", "1"}, {"person", "3"});
    assert(paths.size() == 2);  // Direct path and via person 2
}

TEST(get_edge) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"since", "2020"}});

    auto edge = graph.getEdge("KNOWS", {"person", "1"}, {"person", "2"});
    assert(edge.relType == "KNOWS");
    assert(edge.properties.at("since") == "2020");
}

// =============================================================================
// Pattern Query Tests
// =============================================================================

TEST(query_pattern) {
    ISONGraph graph("test");
    graph.addNode("person", "1");
    graph.addNode("person", "2");
    graph.addNode("person", "3");
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});
    graph.addEdge("KNOWS", {"person", "2"}, {"person", "3"});

    auto result = graph.query(":person:1 -[:KNOWS]-> *");
    assert(result.size() == 1);
    assert(result[0].id == "2");

    auto result2 = graph.query(":person:1 -[:KNOWS*2]-> *");
    assert(result2.size() == 1);
    assert(result2[0].id == "3");
}

// =============================================================================
// Fluent API Start Test
// =============================================================================

TEST(start_method) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    auto result = graph.start({"person", "1"})
        .hop("KNOWS")
        .collect();

    assert(result.size() == 1);
    assert(result[0].id == "2");
}

TEST(collect_nodes) {
    ISONGraph graph("test");
    graph.addNode("person", "1", {{"name", "Alice"}});
    graph.addNode("person", "2", {{"name", "Bob"}});
    graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"});

    auto nodes = graph.start({"person", "1"})
        .hop("KNOWS")
        .collectNodes();

    assert(nodes.size() == 1);
    assert(nodes[0].properties.at("name") == "Bob");
}

// =============================================================================
// Canonical Serialization
//
// toIson()/toIsonl() must be byte-identical for the same logical graph
// regardless of insertion order (node type blocks, node rows, edge type
// blocks, and edge rows are all sorted, ordinal string comparison). The
// golden fixture below is shared verbatim across every ISONGraph language
// port's test suite (Python, JS, TS, Rust, C++, C#) as the cross-language
// byte-identity contract - if it changes here, it must change everywhere.
// =============================================================================

static const std::string CANONICAL_GOLDEN_ISON =
    "nodes.company\n"
    "id name\n"
    "acme \"Acme Corp\"\n"
    "\n"
    "nodes.person\n"
    "id age name\n"
    "1 30 Alice\n"
    "10 22 Jax\n"
    "2 25 Bob\n"
    "\n"
    "nodes.project\n"
    "id name tag\n"
    "p1 Alpha \"a|b\"\n"
    "\n"
    "edges.KNOWS\n"
    "source target since\n"
    ":person:1 :person:2 2020\n"
    ":person:10 :person:1 2021\n"
    "\n"
    "edges.WORKS_AT\n"
    "source target role\n"
    ":person:1 :company:acme \"Lead Engineer\"\n"
    "\n"
    "edges.WORKS_ON\n"
    "source target hours\n"
    ":person:10 :project:p1 3\n"
    ":person:2 :project:p1 5";

static const std::string CANONICAL_GOLDEN_ISONL =
    "nodes.company|id name|acme \"Acme Corp\"\n"
    "nodes.person|id age name|1 30 Alice\n"
    "nodes.person|id age name|10 22 Jax\n"
    "nodes.person|id age name|2 25 Bob\n"
    "nodes.project|id name tag|p1 Alpha \"a|b\"\n"
    "edges.KNOWS|source target since|:person:1 :person:2 2020\n"
    "edges.KNOWS|source target since|:person:10 :person:1 2021\n"
    "edges.WORKS_AT|source target role|:person:1 :company:acme \"Lead Engineer\"\n"
    "edges.WORKS_ON|source target hours|:person:10 :project:p1 3\n"
    "edges.WORKS_ON|source target hours|:person:2 :project:p1 5";

static ISONGraph buildCanonicalFixture(int order) {
    ISONGraph g("fixture");
    std::vector<std::tuple<std::string, std::string, Properties>> nodes = {
        {"company", "acme", {{"name", "Acme Corp"}}},
        {"person", "1", {{"name", "Alice"}, {"age", "30"}}},
        {"person", "10", {{"name", "Jax"}, {"age", "22"}}},
        {"person", "2", {{"name", "Bob"}, {"age", "25"}}},
        {"project", "p1", {{"name", "Alpha"}, {"tag", "a|b"}}},
    };
    std::vector<std::tuple<std::string, NodeRef, NodeRef, Properties>> edges = {
        {"KNOWS", {"person", "10"}, {"person", "1"}, {{"since", "2021"}}},
        {"KNOWS", {"person", "1"}, {"person", "2"}, {{"since", "2020"}}},
        {"WORKS_AT", {"person", "1"}, {"company", "acme"}, {{"role", "Lead Engineer"}}},
        {"WORKS_ON", {"person", "2"}, {"project", "p1"}, {{"hours", "5"}}},
        {"WORKS_ON", {"person", "10"}, {"project", "p1"}, {{"hours", "3"}}},
    };
    if (order != 0) {
        std::reverse(nodes.begin(), nodes.end());
        std::reverse(edges.begin(), edges.end());
    }
    for (const auto& [t, i, props] : nodes) g.addNode(t, i, props);
    for (const auto& [rel, s, t, props] : edges) g.addEdge(rel, s, t, props);
    return g;
}

TEST(to_ison_independent_of_insertion_order) {
    assert(buildCanonicalFixture(0).toIson() == buildCanonicalFixture(1).toIson());
}

TEST(to_isonl_independent_of_insertion_order) {
    assert(buildCanonicalFixture(0).toIsonl() == buildCanonicalFixture(1).toIsonl());
}

TEST(to_ison_matches_golden_fixture) {
    assert(buildCanonicalFixture(0).toIson() == CANONICAL_GOLDEN_ISON);
    assert(buildCanonicalFixture(1).toIson() == CANONICAL_GOLDEN_ISON);
}

TEST(to_isonl_matches_golden_fixture) {
    assert(buildCanonicalFixture(0).toIsonl() == CANONICAL_GOLDEN_ISONL);
    assert(buildCanonicalFixture(1).toIsonl() == CANONICAL_GOLDEN_ISONL);
}

TEST(ordinal_not_numeric_sort) {
    // "1" < "10" < "2" ordinally.
    std::string ison = buildCanonicalFixture(0).toIson();
    size_t start = ison.find("nodes.person\n") + std::string("nodes.person\n").size();
    size_t end = ison.find("\n\n", start);
    std::string personBlock = ison.substr(start, end - start);
    std::istringstream iss(personBlock);
    std::string line;
    std::vector<std::string> ids;
    std::getline(iss, line); // skip "id age name" header
    while (std::getline(iss, line)) {
        ids.push_back(line.substr(0, line.find(' ')));
    }
    assert(ids.size() == 3);
    assert(ids[0] == "1");
    assert(ids[1] == "10");
    assert(ids[2] == "2");
}

TEST(roundtrip_preserves_canonical_form) {
    ISONGraph g = buildCanonicalFixture(0);
    ISONGraph reloaded = ISONGraph::fromIson(g.toIson());
    assert(reloaded.toIson() == g.toIson());
}

// =============================================================================
// Main
// =============================================================================

int main() {
    int total = 0;
    int failed = 0;

    std::cout << "\n=== ISONGraph C++ Tests ===\n\n";

    // Node tests
    RUN_TEST(add_and_get_node);
    RUN_TEST(duplicate_node);
    RUN_TEST(node_not_found);
    RUN_TEST(has_node);
    RUN_TEST(remove_node);
    RUN_TEST(update_node);
    RUN_TEST(node_count);
    RUN_TEST(node_types);

    // Edge tests
    RUN_TEST(add_and_has_edge);
    RUN_TEST(edge_to_nonexistent_node);
    RUN_TEST(duplicate_edge);
    RUN_TEST(remove_edge);
    RUN_TEST(edge_count);
    RUN_TEST(undirected_add_edge_returns_forward_edge);
    RUN_TEST(undirected_remove_edge_removes_both_directions);
    RUN_TEST(node_type_id_with_colon_rejected);

    // Traversal tests
    RUN_TEST(neighbors);
    RUN_TEST(neighbors_both_directions);
    RUN_TEST(multi_hop);
    RUN_TEST(multi_hop_range);

    // Path finding tests
    RUN_TEST(shortest_path);
    RUN_TEST(no_path);
    RUN_TEST(path_exists);

    // Graph analysis tests
    RUN_TEST(degree);
    RUN_TEST(is_connected);

    // Serialization tests
    RUN_TEST(to_ison);
    RUN_TEST(to_isonl);

    // Deserialization tests
    RUN_TEST(from_ison);
    RUN_TEST(from_isonl);
    RUN_TEST(ison_roundtrip_special_values);
    RUN_TEST(isonl_roundtrip_special_values);
    RUN_TEST(from_ison_missing_id_column_throws);
    RUN_TEST(from_isonl_missing_id_column_throws);
    RUN_TEST(from_ison_edge_before_node_throws);

    // Additional analysis tests
    RUN_TEST(has_cycle);
    RUN_TEST(has_cycle_undirected_single_edge_no_false_positive);
    RUN_TEST(has_cycle_per_rel_type);
    RUN_TEST(has_cycle_deep_chain_iterative);
    RUN_TEST(all_paths_deep_chain_iterative);
    RUN_TEST(connected_components);
    RUN_TEST(all_paths);
    RUN_TEST(get_edge);

    // Pattern query tests
    RUN_TEST(query_pattern);

    // Fluent API tests
    RUN_TEST(fluent_traversal);
    RUN_TEST(fluent_count);
    RUN_TEST(fluent_filter);
    RUN_TEST(start_method);
    RUN_TEST(collect_nodes);

    // Canonical serialization tests
    RUN_TEST(to_ison_independent_of_insertion_order);
    RUN_TEST(to_isonl_independent_of_insertion_order);
    RUN_TEST(to_ison_matches_golden_fixture);
    RUN_TEST(to_isonl_matches_golden_fixture);
    RUN_TEST(ordinal_not_numeric_sort);
    RUN_TEST(roundtrip_preserves_canonical_form);

    std::cout << "\n=== Results ===\n";
    std::cout << "Total: " << total << ", Passed: " << (total - failed)
              << ", Failed: " << failed << std::endl;

    return failed > 0 ? 1 : 0;
}
