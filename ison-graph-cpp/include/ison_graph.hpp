/**
 * ISONGraph - A Token-Efficient Graph Store for C++
 *
 * A header-only property graph implementation with ISON persistence.
 * Supports multi-hop traversal, path finding, and fluent API.
 *
 * Example:
 * ```cpp
 * #include "ison_graph.hpp"
 *
 * using namespace ison_graph;
 *
 * ISONGraph graph("social");
 * graph.addNode("person", "1", {{"name", "Alice"}, {"age", "30"}});
 * graph.addNode("person", "2", {{"name", "Bob"}, {"age", "25"}});
 * graph.addEdge("KNOWS", {"person", "1"}, {"person", "2"}, {{"since", "2020"}});
 *
 * auto friends = graph.neighbors({"person", "1"}, "KNOWS");
 * auto fof = graph.multiHop({"person", "1"}, "KNOWS", 2);
 * ```
 *
 * Author: Mahesh Vaikri
 * Version: 1.1.0
 */

#ifndef ISON_GRAPH_HPP
#define ISON_GRAPH_HPP

// ISON syntax lives in one place. Including the parser rather than
// vendoring a copy means a parser fix reaches ISONGraph on the next
// build instead of when someone remembers to re-cut the copy.
#include "ison_parser.hpp"

// Require a parser new enough to have what this port depends on: canonical
// serialization that sorts on the full field tuple, and the name rules that
// reject what cannot be read back. A stale ison_parser.hpp would otherwise
// compile fine and quietly emit different bytes.
//
// Checked with the preprocessor rather than static_assert because that also
// catches a header old enough to predate the macros - static_assert cannot
// fire on a symbol that does not exist, and ison::VERSION is a const char*
// that no compile-time comparison can reach.
#ifndef ISON_VERSION_MAJOR
#  error "ison_parser.hpp predates the ISON_VERSION_* macros. ISONGraph needs ison-cpp >= 1.2.0; earlier releases lose floats in transit."
#endif
#if (ISON_VERSION_MAJOR * 10000 + ISON_VERSION_MINOR * 100 + ISON_VERSION_PATCH) < 10200
#  error "ison_parser.hpp is older than 1.2.0; ISONGraph needs its float-preserving canonical writer."
#endif

#include <memory>
#include <set>
#include <algorithm>

#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <set>
#include <queue>
#include <optional>
#include <memory>
#include <algorithm>
#include <sstream>
#include <functional>
#include <stdexcept>
#include <fstream>
#include <tuple>
#include <regex>

namespace ison_graph {

constexpr const char* VERSION = "1.1.0";

// =============================================================================
// Types
// =============================================================================

/** Node reference: (type, id) */
struct NodeRef {
    std::string type;
    std::string id;

    NodeRef() = default;
    NodeRef(const std::string& t, const std::string& i) : type(t), id(i) {}
    NodeRef(const char* t, const char* i) : type(t), id(i) {}

    std::string key() const { return type + ":" + id; }
    std::string toIsonRef() const { return ":" + type + ":" + id; }

    bool operator==(const NodeRef& other) const {
        return type == other.type && id == other.id;
    }
    bool operator!=(const NodeRef& other) const {
        return !(*this == other);
    }
    bool operator<(const NodeRef& other) const {
        if (type != other.type) return type < other.type;
        return id < other.id;
    }
};

/** Hash function for NodeRef */
struct NodeRefHash {
    std::size_t operator()(const NodeRef& ref) const {
        return std::hash<std::string>()(ref.key());
    }
};

/** Properties map */
/// Property values are ISON values. Storing strings here was what made this
/// port emit every value quoted and disagree with the typed ports; the
/// parser already models exactly the types the format has, so it owns them.
using Properties = std::map<std::string, ison::Value>;

/// Render a property as text - the form every value had before properties
/// carried types. Query string operators, schema validation and the
/// visualiser use it so their behaviour is unchanged by typing the storage.
inline std::string valueToText(const ison::Value& value) {
    if (value.is_null()) return std::string();
    if (value.is_bool()) return value.as_bool() ? "true" : "false";
    if (value.is_int()) return std::to_string(value.as_int());
    if (value.is_float()) return std::to_string(value.as_float());
    if (value.is_string()) return value.as_string();
    if (value.is_reference()) return value.as_reference_ptr()->to_ison();
    return std::string();
}

/** Traversal direction */
enum class Direction {
    Out,
    In,
    Both
};

// =============================================================================
// Data Classes
// =============================================================================

/** Represents a graph node with properties */
struct Node {
    std::string type;
    std::string id;
    Properties properties;

    Node() = default;
    Node(const std::string& t, const std::string& i) : type(t), id(i) {}
    Node(const std::string& t, const std::string& i, const Properties& props)
        : type(t), id(i), properties(props) {}

    NodeRef ref() const { return NodeRef(type, id); }
    std::string key() const { return type + ":" + id; }
    std::string toIsonRef() const { return ":" + type + ":" + id; }
};

/** Represents a graph edge with properties */
struct Edge {
    std::string relType;
    NodeRef source;
    NodeRef target;
    Properties properties;

    Edge() = default;
    Edge(const std::string& rel, const NodeRef& src, const NodeRef& tgt)
        : relType(rel), source(src), target(tgt) {}
    Edge(const std::string& rel, const NodeRef& src, const NodeRef& tgt, const Properties& props)
        : relType(rel), source(src), target(tgt), properties(props) {}

    std::string key() const {
        return relType + ":" + source.key() + ":" + target.key();
    }
};

/** Represents a path through the graph */
struct Path {
    std::vector<NodeRef> nodes;
    std::vector<Edge> edges;

    Path() = default;
    Path(const std::vector<NodeRef>& n, const std::vector<Edge>& e)
        : nodes(n), edges(e) {}

    /** Number of hops in the path */
    size_t length() const { return edges.size(); }

    /** Starting node */
    std::optional<NodeRef> start() const {
        return nodes.empty() ? std::nullopt : std::optional<NodeRef>(nodes.front());
    }

    /** Ending node */
    std::optional<NodeRef> end() const {
        return nodes.empty() ? std::nullopt : std::optional<NodeRef>(nodes.back());
    }
};

// =============================================================================
// Exceptions
// =============================================================================

class GraphError : public std::runtime_error {
public:
    explicit GraphError(const std::string& msg) : std::runtime_error(msg) {}
};

class NodeNotFoundError : public GraphError {
public:
    NodeRef nodeRef;
    explicit NodeNotFoundError(const NodeRef& ref)
        : GraphError("Node not found: :" + ref.type + ":" + ref.id), nodeRef(ref) {}
};

class EdgeNotFoundError : public GraphError {
public:
    std::string edgeKey;
    explicit EdgeNotFoundError(const std::string& key)
        : GraphError("Edge not found: " + key), edgeKey(key) {}
};

class DuplicateNodeError : public GraphError {
public:
    NodeRef nodeRef;
    explicit DuplicateNodeError(const NodeRef& ref)
        : GraphError("Node already exists: :" + ref.type + ":" + ref.id), nodeRef(ref) {}
};

class DuplicateEdgeError : public GraphError {
public:
    std::string edgeKey;
    explicit DuplicateEdgeError(const std::string& key)
        : GraphError("Edge already exists: " + key), edgeKey(key) {}
};

// =============================================================================
// ISONGraph - Main Graph Class
// =============================================================================

// Forward declaration (defined after ISONGraph)
class GraphTraversal;

/**
 * In-memory property graph store with ISON persistence.
 *
 * Features:
 * - Property graph model (nodes and edges with properties)
 * - Multiple node types and relationship types
 * - O(1) node lookup by (type, id)
 * - Multi-hop traversal
 * - Shortest path finding (BFS)
 * - ISON/ISONL persistence
 */
class ISONGraph {
public:
    std::string name;
    bool directed;

private:
    // Node storage: type -> id -> Node
    std::unordered_map<std::string, std::unordered_map<std::string, Node>> nodes_;

    // Edge storage: relType -> edges
    std::unordered_map<std::string, std::vector<Edge>> edges_;

    // Index: outgoing edges per node
    std::unordered_map<std::string, std::vector<Edge>> outEdges_;

    // Index: incoming edges per node
    std::unordered_map<std::string, std::vector<Edge>> inEdges_;

    // Edge uniqueness set
    std::unordered_set<std::string> edgeSet_;

public:
    explicit ISONGraph(const std::string& graphName = "graph", bool isDirected = true)
        : name(graphName), directed(isDirected) {}

    // =========================================================================
    // Node Operations
    // =========================================================================

    /**
     * Add a node to the graph.
     * @throws std::invalid_argument if type or id contains ':' or '|'
     * @throws DuplicateNodeError if node already exists
     */
    Node& addNode(const std::string& nodeType, const std::string& nodeId,
                  const Properties& properties = {}) {
        checkIdentifier("Node type", nodeType);
        checkIdentifier("Node id", nodeId);
        checkPropertyNames("Node property", properties);
        auto& typeNodes = nodes_[nodeType];
        if (typeNodes.find(nodeId) != typeNodes.end()) {
            throw DuplicateNodeError(NodeRef(nodeType, nodeId));
        }

        typeNodes[nodeId] = Node(nodeType, nodeId, properties);
        return typeNodes[nodeId];
    }

    /**
     * Get a node by type and ID.
     * @throws NodeNotFoundError if node doesn't exist
     */
    Node& getNode(const std::string& nodeType, const std::string& nodeId) {
        auto typeIt = nodes_.find(nodeType);
        if (typeIt == nodes_.end()) {
            throw NodeNotFoundError(NodeRef(nodeType, nodeId));
        }
        auto nodeIt = typeIt->second.find(nodeId);
        if (nodeIt == typeIt->second.end()) {
            throw NodeNotFoundError(NodeRef(nodeType, nodeId));
        }
        return nodeIt->second;
    }

    const Node& getNode(const std::string& nodeType, const std::string& nodeId) const {
        auto typeIt = nodes_.find(nodeType);
        if (typeIt == nodes_.end()) {
            throw NodeNotFoundError(NodeRef(nodeType, nodeId));
        }
        auto nodeIt = typeIt->second.find(nodeId);
        if (nodeIt == typeIt->second.end()) {
            throw NodeNotFoundError(NodeRef(nodeType, nodeId));
        }
        return nodeIt->second;
    }

    /** Get node by reference */
    Node& getNodeByRef(const NodeRef& ref) {
        return getNode(ref.type, ref.id);
    }

    const Node& getNodeByRef(const NodeRef& ref) const {
        return getNode(ref.type, ref.id);
    }

    /** Check if node exists */
    bool hasNode(const std::string& nodeType, const std::string& nodeId) const {
        auto typeIt = nodes_.find(nodeType);
        if (typeIt == nodes_.end()) return false;
        return typeIt->second.find(nodeId) != typeIt->second.end();
    }

    bool hasNode(const NodeRef& ref) const {
        return hasNode(ref.type, ref.id);
    }

    /**
     * Remove a node and all its edges.
     * @throws NodeNotFoundError if node doesn't exist
     */
    void removeNode(const std::string& nodeType, const std::string& nodeId) {
        NodeRef ref(nodeType, nodeId);
        if (!hasNode(nodeType, nodeId)) {
            throw NodeNotFoundError(ref);
        }

        std::string nodeKey = ref.key();

        // Collect edges to remove
        std::vector<Edge> toRemove;
        if (outEdges_.find(nodeKey) != outEdges_.end()) {
            for (const auto& e : outEdges_[nodeKey]) {
                toRemove.push_back(e);
            }
        }
        if (inEdges_.find(nodeKey) != inEdges_.end()) {
            for (const auto& e : inEdges_[nodeKey]) {
                toRemove.push_back(e);
            }
        }

        for (const auto& edge : toRemove) {
            removeEdgeInternal(edge);
        }

        // Remove node
        nodes_[nodeType].erase(nodeId);
        if (nodes_[nodeType].empty()) {
            nodes_.erase(nodeType);
        }
    }

    /** Update node properties */
    void updateNode(const std::string& nodeType, const std::string& nodeId,
                    const Properties& properties) {
        Node& node = getNode(nodeType, nodeId);
        for (const auto& [k, v] : properties) {
            node.properties[k] = v;
        }
    }

    /** Count all nodes */
    size_t nodeCount() const {
        size_t count = 0;
        for (const auto& [type, typeNodes] : nodes_) {
            count += typeNodes.size();
        }
        return count;
    }

    /** Count nodes of a specific type */
    size_t nodeCount(const std::string& nodeType) const {
        auto it = nodes_.find(nodeType);
        return it != nodes_.end() ? it->second.size() : 0;
    }

    /** Get all node types */
    std::vector<std::string> nodeTypes() const {
        std::vector<std::string> types;
        for (const auto& [type, _] : nodes_) {
            types.push_back(type);
        }
        return types;
    }

    /** Iterate over all nodes */
    template<typename Func>
    void forEachNode(Func&& func) const {
        for (const auto& [type, typeNodes] : nodes_) {
            for (const auto& [id, node] : typeNodes) {
                func(node);
            }
        }
    }

    /** Iterate over nodes of a type */
    template<typename Func>
    void forEachNode(const std::string& nodeType, Func&& func) const {
        auto it = nodes_.find(nodeType);
        if (it != nodes_.end()) {
            for (const auto& [id, node] : it->second) {
                func(node);
            }
        }
    }

    // =========================================================================
    // Edge Operations
    // =========================================================================

    /**
     * Add an edge to the graph.
     * Returns the forward edge (source -> target) by value; for undirected
     * graphs the reverse edge is stored as well but not returned.
     * @throws std::invalid_argument if relType contains ':' or '|'
     * @throws NodeNotFoundError if source or target doesn't exist
     * @throws DuplicateEdgeError if edge already exists
     */
    Edge addEdge(const std::string& relType, const NodeRef& source, const NodeRef& target,
                 const Properties& properties = {}) {
        checkIdentifier("Relationship type", relType);
        checkPropertyNames("Edge property", properties);

        if (!hasNode(source)) {
            throw NodeNotFoundError(source);
        }
        if (!hasNode(target)) {
            throw NodeNotFoundError(target);
        }

        Edge edge(relType, source, target, properties);
        std::string edgeKey = edge.key();

        if (edgeSet_.find(edgeKey) != edgeSet_.end()) {
            throw DuplicateEdgeError(edgeKey);
        }

        // Add to storage
        edges_[relType].push_back(edge);
        outEdges_[source.key()].push_back(edge);
        inEdges_[target.key()].push_back(edge);
        edgeSet_.insert(edgeKey);

        // For undirected graphs, add reverse edge
        if (!directed) {
            Edge reverseEdge(relType, target, source, properties);
            std::string reverseKey = reverseEdge.key();
            if (edgeSet_.find(reverseKey) == edgeSet_.end()) {
                edges_[relType].push_back(reverseEdge);
                outEdges_[target.key()].push_back(reverseEdge);
                inEdges_[source.key()].push_back(reverseEdge);
                edgeSet_.insert(reverseKey);
            }
        }

        return edge;
    }

private:
    void removeEdgeInternal(const Edge& edge) {
        std::string edgeKey = edge.key();
        if (edgeSet_.find(edgeKey) == edgeSet_.end()) {
            return;
        }

        edgeSet_.erase(edgeKey);

        // Remove from edges_
        auto& relEdges = edges_[edge.relType];
        relEdges.erase(
            std::remove_if(relEdges.begin(), relEdges.end(),
                [&edgeKey](const Edge& e) { return e.key() == edgeKey; }),
            relEdges.end()
        );

        // Remove from outEdges_
        std::string sourceKey = edge.source.key();
        if (outEdges_.find(sourceKey) != outEdges_.end()) {
            auto& out = outEdges_[sourceKey];
            out.erase(
                std::remove_if(out.begin(), out.end(),
                    [&edgeKey](const Edge& e) { return e.key() == edgeKey; }),
                out.end()
            );
        }

        // Remove from inEdges_
        std::string targetKey = edge.target.key();
        if (inEdges_.find(targetKey) != inEdges_.end()) {
            auto& in = inEdges_[targetKey];
            in.erase(
                std::remove_if(in.begin(), in.end(),
                    [&edgeKey](const Edge& e) { return e.key() == edgeKey; }),
                in.end()
            );
        }
    }

public:
    /** Remove an edge. For undirected graphs the stored reverse edge is removed too. */
    void removeEdge(const std::string& relType, const NodeRef& source, const NodeRef& target) {
        Edge edge(relType, source, target);
        std::string edgeKey = edge.key();

        if (edgeSet_.find(edgeKey) == edgeSet_.end()) {
            throw EdgeNotFoundError(edgeKey);
        }

        removeEdgeInternal(edge);

        if (!directed) {
            // Remove the mirrored edge as well (no-op if it doesn't exist)
            removeEdgeInternal(Edge(relType, target, source));
        }
    }

    /** Check if edge exists */
    bool hasEdge(const std::string& relType, const NodeRef& source, const NodeRef& target) const {
        Edge edge(relType, source, target);
        return edgeSet_.find(edge.key()) != edgeSet_.end();
    }

    /** Count all edges */
    size_t edgeCount() const {
        return edgeSet_.size();
    }

    /** Count edges of a specific type */
    size_t edgeCount(const std::string& relType) const {
        auto it = edges_.find(relType);
        return it != edges_.end() ? it->second.size() : 0;
    }

    /** Get all edge types */
    std::vector<std::string> edgeTypes() const {
        std::vector<std::string> types;
        for (const auto& [type, _] : edges_) {
            types.push_back(type);
        }
        return types;
    }

    /** Get edges of a specific relationship type */
    std::vector<Edge> getEdges(const std::string& relType) const {
        auto it = edges_.find(relType);
        if (it != edges_.end()) {
            return it->second;
        }
        return {};
    }

    /** Get all edges */
    std::vector<Edge> getAllEdges() const {
        std::vector<Edge> result;
        for (const auto& [type, edges] : edges_) {
            result.insert(result.end(), edges.begin(), edges.end());
        }
        return result;
    }

    /** Get internal nodes storage (for validation) */
    const std::unordered_map<std::string, std::unordered_map<std::string, Node>>& getNodes() const {
        return nodes_;
    }

    // =========================================================================
    // Traversal Operations
    // =========================================================================

    /** Get neighboring nodes */
    std::vector<NodeRef> neighbors(const NodeRef& nodeRef,
                                    const std::string& relType = "",
                                    Direction direction = Direction::Out) const {
        std::vector<NodeRef> result;
        std::string nodeKey = nodeRef.key();

        if (direction == Direction::Out || direction == Direction::Both) {
            auto it = outEdges_.find(nodeKey);
            if (it != outEdges_.end()) {
                for (const auto& edge : it->second) {
                    if (relType.empty() || edge.relType == relType) {
                        result.push_back(edge.target);
                    }
                }
            }
        }

        if (direction == Direction::In || direction == Direction::Both) {
            auto it = inEdges_.find(nodeKey);
            if (it != inEdges_.end()) {
                for (const auto& edge : it->second) {
                    if (relType.empty() || edge.relType == relType) {
                        result.push_back(edge.source);
                    }
                }
            }
        }

        return result;
    }

    /** Get nodes N hops away */
    std::vector<NodeRef> multiHop(const NodeRef& start,
                                   const std::string& relType = "",
                                   size_t hops = 1,
                                   Direction direction = Direction::Out) const {
        if (hops == 0) {
            return {start};
        }

        std::unordered_set<std::string> current;
        current.insert(start.key());

        std::unordered_set<std::string> visited;
        visited.insert(start.key());

        std::unordered_map<std::string, NodeRef> refMap;
        refMap[start.key()] = start;

        for (size_t i = 0; i < hops; ++i) {
            std::unordered_set<std::string> nextLevel;

            for (const auto& key : current) {
                auto it = refMap.find(key);
                if (it != refMap.end()) {
                    auto neighborRefs = neighbors(it->second, relType, direction);
                    for (const auto& neighbor : neighborRefs) {
                        std::string neighborKey = neighbor.key();
                        if (visited.find(neighborKey) == visited.end()) {
                            nextLevel.insert(neighborKey);
                            refMap[neighborKey] = neighbor;
                        }
                    }
                }
            }

            for (const auto& key : nextLevel) {
                visited.insert(key);
            }
            current = std::move(nextLevel);
        }

        std::vector<NodeRef> result;
        for (const auto& key : current) {
            result.push_back(refMap[key]);
        }
        return result;
    }

    /** Get nodes within a range of hops */
    std::vector<NodeRef> multiHopRange(const NodeRef& start,
                                        const std::string& relType = "",
                                        size_t minHops = 1,
                                        size_t maxHops = 3,
                                        Direction direction = Direction::Out) const {
        std::unordered_set<std::string> result;
        std::unordered_set<std::string> current;
        current.insert(start.key());

        std::unordered_set<std::string> visited;
        visited.insert(start.key());

        std::unordered_map<std::string, NodeRef> refMap;
        refMap[start.key()] = start;

        for (size_t hop = 1; hop <= maxHops; ++hop) {
            std::unordered_set<std::string> nextLevel;

            for (const auto& key : current) {
                auto it = refMap.find(key);
                if (it != refMap.end()) {
                    auto neighborRefs = neighbors(it->second, relType, direction);
                    for (const auto& neighbor : neighborRefs) {
                        std::string neighborKey = neighbor.key();
                        if (visited.find(neighborKey) == visited.end()) {
                            nextLevel.insert(neighborKey);
                            refMap[neighborKey] = neighbor;
                            if (hop >= minHops) {
                                result.insert(neighborKey);
                            }
                        }
                    }
                }
            }

            for (const auto& key : nextLevel) {
                visited.insert(key);
            }
            current = std::move(nextLevel);

            if (current.empty()) break;
        }

        std::vector<NodeRef> resultVec;
        for (const auto& key : result) {
            resultVec.push_back(refMap[key]);
        }
        return resultVec;
    }

    // =========================================================================
    // Path Finding
    // =========================================================================

    /** Find shortest path between two nodes using BFS */
    std::optional<Path> shortestPath(const NodeRef& start, const NodeRef& end,
                                      const std::string& relType = "",
                                      size_t maxHops = 10,
                                      Direction direction = Direction::Out) const {
        if (start == end) {
            return Path({start}, {});
        }

        std::string endKey = end.key();
        std::unordered_set<std::string> visited;
        visited.insert(start.key());

        struct QueueItem {
            NodeRef current;
            std::vector<NodeRef> pathNodes;
            std::vector<Edge> pathEdges;
        };

        std::queue<QueueItem> queue;
        queue.push({start, {start}, {}});

        while (!queue.empty()) {
            QueueItem item = queue.front();
            queue.pop();

            if (item.pathNodes.size() > maxHops + 1) {
                continue;
            }

            std::string currentKey = item.current.key();

            if (direction != Direction::In) {
                auto it = outEdges_.find(currentKey);
                if (it != outEdges_.end()) {
                    for (const auto& edge : it->second) {
                        if (!relType.empty() && edge.relType != relType) continue;

                        std::string targetKey = edge.target.key();
                        if (targetKey == endKey) {
                            auto nodes = item.pathNodes;
                            nodes.push_back(edge.target);
                            auto edges = item.pathEdges;
                            edges.push_back(edge);
                            return Path(nodes, edges);
                        }

                        if (visited.find(targetKey) == visited.end()) {
                            visited.insert(targetKey);
                            auto nodes = item.pathNodes;
                            nodes.push_back(edge.target);
                            auto edges = item.pathEdges;
                            edges.push_back(edge);
                            queue.push({edge.target, nodes, edges});
                        }
                    }
                }
            }

            if (direction == Direction::In || direction == Direction::Both) {
                auto it = inEdges_.find(currentKey);
                if (it != inEdges_.end()) {
                    for (const auto& edge : it->second) {
                        if (!relType.empty() && edge.relType != relType) continue;

                        std::string sourceKey = edge.source.key();
                        if (sourceKey == endKey) {
                            auto nodes = item.pathNodes;
                            nodes.push_back(edge.source);
                            auto edges = item.pathEdges;
                            edges.push_back(edge);
                            return Path(nodes, edges);
                        }

                        if (visited.find(sourceKey) == visited.end()) {
                            visited.insert(sourceKey);
                            auto nodes = item.pathNodes;
                            nodes.push_back(edge.source);
                            auto edges = item.pathEdges;
                            edges.push_back(edge);
                            queue.push({edge.source, nodes, edges});
                        }
                    }
                }
            }
        }

        return std::nullopt;
    }

    /** Check if a path exists */
    bool pathExists(const NodeRef& start, const NodeRef& end,
                    const std::string& relType = "",
                    size_t maxHops = 10) const {
        return shortestPath(start, end, relType, maxHops).has_value();
    }

    // =========================================================================
    // Graph Analysis
    // =========================================================================

    /** Count incoming edges */
    size_t inDegree(const NodeRef& nodeRef) const {
        auto it = inEdges_.find(nodeRef.key());
        return it != inEdges_.end() ? it->second.size() : 0;
    }

    /** Count outgoing edges */
    size_t outDegree(const NodeRef& nodeRef) const {
        auto it = outEdges_.find(nodeRef.key());
        return it != outEdges_.end() ? it->second.size() : 0;
    }

    /** Total degree */
    size_t degree(const NodeRef& nodeRef) const {
        return inDegree(nodeRef) + outDegree(nodeRef);
    }

    /** Check if graph is connected */
    bool isConnected() const {
        if (nodes_.empty()) return true;

        // Get first node
        const Node* firstNode = nullptr;
        for (const auto& [type, typeNodes] : nodes_) {
            if (!typeNodes.empty()) {
                firstNode = &typeNodes.begin()->second;
                break;
            }
        }
        if (!firstNode) return true;

        std::unordered_set<std::string> visited;
        std::queue<std::string> queue;

        std::string startKey = firstNode->key();
        visited.insert(startKey);
        queue.push(startKey);

        while (!queue.empty()) {
            std::string currentKey = queue.front();
            queue.pop();

            // Parse key to get NodeRef
            size_t colonPos = currentKey.find(':');
            if (colonPos != std::string::npos) {
                NodeRef ref(currentKey.substr(0, colonPos), currentKey.substr(colonPos + 1));
                auto neighborRefs = neighbors(ref, "", Direction::Both);
                for (const auto& neighbor : neighborRefs) {
                    std::string neighborKey = neighbor.key();
                    if (visited.find(neighborKey) == visited.end()) {
                        visited.insert(neighborKey);
                        queue.push(neighborKey);
                    }
                }
            }
        }

        return visited.size() == nodeCount();
    }

    // =========================================================================
    // Serialization
    // =========================================================================

    /**
     * Build the ISON Document this graph serializes to.
     *
     * ISONGraph decides *what* to emit - which blocks, which rows, which
     * columns - and hands every byte-level decision to ison_parser's
     * canonical writer: quoting, escaping, delimiters, column layout, and
     * the final block and row order.
     *
     * This used to be hand-rolled here, which meant ISON syntax had two
     * implementations per language that had to agree forever. They did not:
     * the id column was written unquoted, so a node id containing a space
     * produced output that would not reparse.
     */
    ison::Document buildDocument() const {
        ison::Document doc;

        std::vector<std::string> nodeTypes;
        for (auto it = nodes_.begin(); it != nodes_.end(); ++it) {
            nodeTypes.push_back(it->first);
        }
        std::sort(nodeTypes.begin(), nodeTypes.end());

        for (const auto& nodeType : nodeTypes) {
            const auto& typeNodes = nodes_.at(nodeType);
            if (typeNodes.empty()) continue;

            std::set<std::string> propKeys;
            for (auto it = typeNodes.begin(); it != typeNodes.end(); ++it) {
                for (auto pit = it->second.properties.begin();
                     pit != it->second.properties.end(); ++pit) {
                    propKeys.insert(pit->first);
                }
            }

            ison::Block block("nodes", nodeType);
            block.fields.push_back("id");
            for (const auto& key : propKeys) block.fields.push_back(key);

            for (auto it = typeNodes.begin(); it != typeNodes.end(); ++it) {
                const Node& node = it->second;
                ison::Row row;
                row["id"] = ison::Value(node.id);
                for (const auto& key : propKeys) {
                    auto found = node.properties.find(key);
                    row[key] = (found == node.properties.end())
                        ? ison::Value(nullptr)
                        : ison::Value(found->second);
                }
                block.rows.push_back(row);
            }
            doc.blocks.push_back(block);
        }

        std::vector<std::string> relTypes;
        for (auto it = edges_.begin(); it != edges_.end(); ++it) {
            relTypes.push_back(it->first);
        }
        std::sort(relTypes.begin(), relTypes.end());

        for (const auto& relType : relTypes) {
            const auto& edges = edges_.at(relType);
            if (edges.empty()) continue;

            std::set<std::string> propKeys;
            for (const auto& edge : edges) {
                for (auto pit = edge.properties.begin();
                     pit != edge.properties.end(); ++pit) {
                    propKeys.insert(pit->first);
                }
            }

            ison::Block block("edges", relType);
            block.fields.push_back("source");
            block.fields.push_back("target");
            for (const auto& key : propKeys) block.fields.push_back(key);

            for (const auto& edge : edges) {
                ison::Row row;
                row["source"] = ison::Value(std::make_shared<ison::Reference>(
                    edge.source.id, edge.source.type));
                row["target"] = ison::Value(std::make_shared<ison::Reference>(
                    edge.target.id, edge.target.type));
                for (const auto& key : propKeys) {
                    auto found = edge.properties.find(key);
                    row[key] = (found == edge.properties.end())
                        ? ison::Value(nullptr)
                        : ison::Value(found->second);
                }
                block.rows.push_back(row);
            }
            doc.blocks.push_back(block);
        }

        return doc;
    }

    /**
     * Serialize to canonical ISON (ISONCS). The same logical graph always
     * serializes to the same bytes regardless of construction order.
     */
    std::string toIson() const {
        return ison::dumps_canonical(buildDocument());
    }

    /** Serialize to canonical ISONL. Row order matches toIson(). */
    std::string toIsonl() const {
        return ison::dumps_canonical_isonl(buildDocument());
    }

private:
    /**
     * Reject ':' or '|' in a node type, node id, or relationship type. Both
     * are structurally significant to the wire format (':' delimits
     * `:type:id` references, '|' delimits ISONL columns); allowing them
     * here would build a graph that throws on toIson()/toIsonl()
     * round-trip instead of failing at construction.
     */
    static void checkIdentifier(const std::string& kind, const std::string& value) {
        // Types become block names, which ISONL additionally cannot quote;
        // ids only have to survive a reference, which has no quoting at all.
        bool isType = kind.find("type") != std::string::npos ||
                      kind.find("Type") != std::string::npos;
        bool bad = value.empty();
        for (size_t i = 0; !bad && i < value.size(); ++i) {
            char c = value[i];
            bad = (c == ' ' || c == '\t' || c == '\n' || c == '\r' ||
                   c == ':' || c == '|' ||
                   (isType && (c == '"' || c == '\\')));
        }
        if (bad) {
            throw std::invalid_argument(
                kind + " '" + value + "' is not representable: it must not be empty "
                "or contain whitespace, ':' or '|'" +
                (isType ? std::string(", '\"' or '\\'") : std::string()));
        }
    }

    /**
     * Reject property names that cannot survive a serialization round trip.
     *
     * Property names become ISON field names, and the format quotes values
     * but not names: a space splits the field in two, ':' has the remainder
     * eaten as a type annotation, '.' is a dot path, and a leading '#' turns
     * the header into a comment and loses the whole block.
     */
    static void checkPropertyNames(const std::string& kind, const Properties& props) {
        for (Properties::const_iterator it = props.begin(); it != props.end(); ++it) {
            const std::string& name = it->first;
            bool bad = name.empty() || name[0] == '#';
            for (size_t i = 0; !bad && i < name.size(); ++i) {
                char c = name[i];
                bad = (c == ' ' || c == '\t' || c == '\n' || c == '\r' ||
                       c == ':' || c == '|' || c == '"' || c == '\\' || c == '.');
            }
            if (bad) {
                throw std::invalid_argument(
                    kind + " name '" + name + "' cannot be encoded: property names "
                    "must not be empty, start with '#', or contain whitespace, "
                    "':', '|', '\"', '\\' or '.'");
            }
        }
    }

    /** Node rows within a type block, sorted by id (ordinal string compare). */
    static std::vector<const Node*> sortedNodes(const std::unordered_map<std::string, Node>& typeNodes) {
        std::vector<const Node*> nodes;
        nodes.reserve(typeNodes.size());
        for (const auto& [id, node] : typeNodes) {
            nodes.push_back(&node);
        }
        std::sort(nodes.begin(), nodes.end(), [](const Node* a, const Node* b) {
            return a->id < b->id;
        });
        return nodes;
    }

    /**
     * Edge rows within a rel_type block, sorted by
     * (source.type, source.id, target.type, target.id) - ordinal.
     */
    static std::vector<const Edge*> sortedEdges(const std::vector<Edge>& edges) {
        std::vector<const Edge*> result;
        result.reserve(edges.size());
        for (const auto& edge : edges) {
            result.push_back(&edge);
        }
        std::sort(result.begin(), result.end(), [](const Edge* a, const Edge* b) {
            auto ka = std::tie(a->source.type, a->source.id, a->target.type, a->target.id);
            auto kb = std::tie(b->source.type, b->source.id, b->target.type, b->target.id);
            return ka < kb;
        });
        return result;
    }

    /** Helper to trim whitespace */
    static std::string trim(const std::string& s) {
        size_t start = s.find_first_not_of(" \t\r\n");
        if (start == std::string::npos) return "";
        size_t end = s.find_last_not_of(" \t\r\n");
        return s.substr(start, end - start + 1);
    }

    /** Helper to split string by delimiter */
    static std::vector<std::string> split(const std::string& s, char delim) {
        std::vector<std::string> result;
        std::istringstream iss(s);
        std::string token;
        while (std::getline(iss, token, delim)) {
            result.push_back(token);
        }
        return result;
    }

    /**
     * Quote a value for ISON/ISONL output.
     * Standardized rule (all ISON ports): double-quote when the value contains
     * a space, '|', '"', newline, or is empty. Escape '"' as \", newline as \n,
     * backslash as \\ so the value round-trips losslessly.
     */
    static std::string quoteValue(const std::string& v) {
        bool needsQuoting = v.empty();
        for (char c : v) {
            if (c == ' ' || c == '|' || c == '"' || c == '\n') {
                needsQuoting = true;
                break;
            }
        }
        if (!needsQuoting) return v;

        std::string out = "\"";
        for (char c : v) {
            if (c == '"') out += "\\\"";
            else if (c == '\n') out += "\\n";
            else if (c == '\\') out += "\\\\";
            else out += c;
        }
        out += "\"";
        return out;
    }

    /** Helper to split by whitespace, respecting quotes and unescaping \" \n \\ */
    static std::vector<std::string> splitFields(const std::string& s) {
        std::vector<std::string> result;
        std::string current;
        bool inQuotes = false;
        bool hasToken = false;  // true once a token started (so "" yields an empty field)

        for (size_t i = 0; i < s.size(); ++i) {
            char c = s[i];
            if (inQuotes) {
                if (c == '\\' && i + 1 < s.size()) {
                    char next = s[i + 1];
                    if (next == '"') { current += '"'; ++i; }
                    else if (next == 'n') { current += '\n'; ++i; }
                    else if (next == '\\') { current += '\\'; ++i; }
                    else current += c;
                } else if (c == '"') {
                    inQuotes = false;
                } else {
                    current += c;
                }
            } else if (c == '"') {
                inQuotes = true;
                hasToken = true;
            } else if (c == ' ' || c == '\t') {
                if (hasToken) {
                    result.push_back(current);
                    current.clear();
                    hasToken = false;
                }
            } else {
                current += c;
                hasToken = true;
            }
        }
        if (hasToken) {
            result.push_back(current);
        }
        return result;
    }

    /** Split on '|' while respecting double-quoted sections (for ISONL lines) */
    static std::vector<std::string> splitPipeAware(const std::string& s) {
        std::vector<std::string> result;
        std::string current;
        bool inQuotes = false;

        for (size_t i = 0; i < s.size(); ++i) {
            char c = s[i];
            if (inQuotes && c == '\\' && i + 1 < s.size()) {
                current += c;
                current += s[i + 1];
                ++i;
            } else if (c == '"') {
                inQuotes = !inQuotes;
                current += c;
            } else if (c == '|' && !inQuotes) {
                result.push_back(current);
                current.clear();
            } else {
                current += c;
            }
        }
        result.push_back(current);
        return result;
    }

    /** Parse node reference string ":type:id" */
    static NodeRef parseNodeRef(const std::string& s) {
        if (s.empty() || s[0] != ':') {
            throw GraphError("Invalid node reference: " + s);
        }
        size_t secondColon = s.find(':', 1);
        if (secondColon == std::string::npos) {
            throw GraphError("Invalid node reference: " + s);
        }
        std::string type = s.substr(1, secondColon - 1);
        std::string id = s.substr(secondColon + 1);
        return NodeRef(type, id);
    }

public:
    /**
     * Turn an ISON value into the text ISONGraph stores.
     *
     * Every id and property in this port is a string, so a null becomes an
     * absent property rather than the literal "null".
     */
    /// Node ids are identifiers rather than values, so they are always text.
    /// Property values keep whatever type the parser produced - flattening
    /// them here was what made this port emit every value quoted.
    static bool idText(const ison::Value& value, std::string& out) {
        if (value.is_null()) return false;
        if (value.is_string()) { out = value.as_string(); return true; }
        if (value.is_reference()) { out = value.as_reference_ptr()->to_ison(); return true; }
        if (value.is_bool()) { out = value.as_bool() ? "true" : "false"; return true; }
        if (value.is_int()) { out = std::to_string(value.as_int()); return true; }
        if (value.is_float()) { out = std::to_string(value.as_float()); return true; }
        return false;
    }

    static ISONGraph buildFromDocument(const ison::Document& doc,
                                       const std::string& graphName) {
        ISONGraph graph(graphName);

        for (size_t b = 0; b < doc.blocks.size(); ++b) {
            const ison::Block& block = doc.blocks[b];
            if (block.kind != "nodes" && block.kind != "edges") {
                throw GraphError("unknown block kind '" + block.kind +
                                 "' (expected 'nodes' or 'edges')");
            }
        }

        // Nodes first regardless of block order - the canonical writer sorts
        // blocks by name, which puts 'edges' ahead of 'nodes'.
        for (size_t b = 0; b < doc.blocks.size(); ++b) {
            const ison::Block& block = doc.blocks[b];
            if (block.kind != "nodes") continue;
            for (size_t r = 0; r < block.rows.size(); ++r) {
                const ison::Row& row = block.rows[r];
                ison::Row::const_iterator idIt = row.find("id");
                std::string id;
                if (idIt == row.end() || !idText(idIt->second, id)) {
                    throw GraphError("fromIson: node row has no id");
                }
                Properties props;
                for (ison::Row::const_iterator it = row.begin(); it != row.end(); ++it) {
                    if (it->first == "id") continue;
                    if (!it->second.is_null()) props[it->first] = it->second;
                }
                graph.addNode(block.name, id, props);
            }
        }

        for (size_t b = 0; b < doc.blocks.size(); ++b) {
            const ison::Block& block = doc.blocks[b];
            if (block.kind != "edges") continue;
            for (size_t r = 0; r < block.rows.size(); ++r) {
                const ison::Row& row = block.rows[r];
                ison::Row::const_iterator sIt = row.find("source");
                ison::Row::const_iterator tIt = row.find("target");
                if (sIt == row.end() || tIt == row.end() ||
                    !sIt->second.is_reference() || !tIt->second.is_reference()) {
                    throw GraphError(
                        "fromIson: Invalid node reference: edge row is missing a "
                        "source or target");
                }
                const ison::Reference& sref = *sIt->second.as_reference_ptr();
                const ison::Reference& tref = *tIt->second.as_reference_ptr();

                Properties props;
                for (ison::Row::const_iterator it = row.begin(); it != row.end(); ++it) {
                    if (it->first == "source" || it->first == "target") continue;
                    if (!it->second.is_null()) props[it->first] = it->second;
                }
                // Reference::type is optional; an untyped reference cannot name
                // a node in this graph, so treat it as a malformed edge.
                if (!sref.type.has_value() || !tref.type.has_value()) {
                    throw GraphError(
                        "fromIson: Invalid node reference: edge endpoint has no type");
                }
                graph.addEdge(block.name, NodeRef(sref.type.value(), sref.id),
                              NodeRef(tref.type.value(), tref.id), props);
            }
        }

        return graph;
    }

    /** Parse a graph from ISON. */
    static ISONGraph fromIson(const std::string& text,
                              const std::string& graphName = "graph") {
        return buildFromDocument(ison::loads(text), graphName);
    }

    /** Parse a graph from ISONL. */
    static ISONGraph fromIsonl(const std::string& text,
                               const std::string& graphName = "graph") {
        return buildFromDocument(ison::loads_isonl(text), graphName);
    }


    // =========================================================================
    // File I/O
    // =========================================================================

    /** Save graph to file */
    void save(const std::string& path, const std::string& format = "auto") const {
        std::string actualFormat = format;
        if (format == "auto") {
            actualFormat = (path.size() >= 6 && path.substr(path.size() - 6) == ".isonl")
                           ? "isonl" : "ison";
        }

        std::string content = (actualFormat == "isonl") ? toIsonl() : toIson();

        std::ofstream file(path);
        if (!file) {
            throw GraphError("Cannot open file for writing: " + path);
        }
        file << content;
    }

    /** Load graph from file */
    static ISONGraph load(const std::string& path, const std::string& format = "auto") {
        std::ifstream file(path);
        if (!file) {
            throw GraphError("Cannot open file for reading: " + path);
        }

        std::ostringstream ss;
        ss << file.rdbuf();
        std::string content = ss.str();

        std::string actualFormat = format;
        if (format == "auto") {
            actualFormat = (path.size() >= 6 && path.substr(path.size() - 6) == ".isonl")
                           ? "isonl" : "ison";
        }

        // Extract filename without extension for graph name
        size_t lastSlash = path.find_last_of("/\\");
        size_t lastDot = path.find_last_of('.');
        std::string graphName = path.substr(
            lastSlash == std::string::npos ? 0 : lastSlash + 1,
            lastDot == std::string::npos ? std::string::npos : lastDot - (lastSlash == std::string::npos ? 0 : lastSlash + 1)
        );

        return (actualFormat == "isonl")
            ? fromIsonl(content, graphName)
            : fromIson(content, graphName);
    }

    // =========================================================================
    // Additional Edge Operations
    // =========================================================================

    /** Get an edge by its components */
    Edge getEdge(const std::string& relType, const NodeRef& source, const NodeRef& target) const {
        std::string edgeKey = relType + ":" + source.key() + ":" + target.key();
        if (edgeSet_.find(edgeKey) == edgeSet_.end()) {
            throw EdgeNotFoundError(edgeKey);
        }

        auto it = edges_.find(relType);
        if (it != edges_.end()) {
            for (const auto& edge : it->second) {
                if (edge.source == source && edge.target == target) {
                    return edge;
                }
            }
        }
        throw EdgeNotFoundError(edgeKey);
    }

    // =========================================================================
    // Additional Graph Analysis
    // =========================================================================

    /** Check if graph has cycles (iterative; handles directed and undirected graphs) */
    bool hasCycle(const std::string& relType = "") const {
        return directed ? hasCycleDirected(relType) : hasCycleUndirected(relType);
    }

private:
    /** Iterative DFS with white/gray/black coloring (no recursion) */
    bool hasCycleDirected(const std::string& relType) const {
        // 0 = white (unvisited), 1 = gray (on stack), 2 = black (done)
        std::unordered_map<std::string, int> color;

        struct Frame {
            std::string key;
            size_t idx;
        };

        for (const auto& [type, typeNodes] : nodes_) {
            for (const auto& [id, node] : typeNodes) {
                std::string startKey = node.key();
                if (color[startKey] != 0) continue;

                std::vector<Frame> stack;
                color[startKey] = 1;
                stack.push_back({startKey, 0});

                while (!stack.empty()) {
                    Frame& frame = stack.back();

                    const std::vector<Edge>* out = nullptr;
                    auto it = outEdges_.find(frame.key);
                    if (it != outEdges_.end()) out = &it->second;

                    bool descended = false;
                    while (out && frame.idx < out->size()) {
                        const Edge& edge = (*out)[frame.idx++];
                        if (!relType.empty() && edge.relType != relType) continue;

                        std::string targetKey = edge.target.key();
                        int targetColor = 0;
                        auto cit = color.find(targetKey);
                        if (cit != color.end()) targetColor = cit->second;

                        if (targetColor == 1) return true;  // back edge -> cycle
                        if (targetColor == 0) {
                            color[targetKey] = 1;
                            stack.push_back({targetKey, 0});  // invalidates 'frame'; break immediately
                            descended = true;
                            break;
                        }
                    }

                    if (!descended) {
                        color[stack.back().key] = 2;
                        stack.pop_back();
                    }
                }
            }
        }
        return false;
    }

    /**
     * Iterative undirected cycle check with parent-edge tracking: the single
     * stored reverse of the edge used to enter a node is not treated as a cycle,
     * so one undirected edge (stored as two directed edges) is not a false positive.
     */
    bool hasCycleUndirected(const std::string& relType) const {
        std::unordered_set<std::string> visited;

        struct Frame {
            std::string key;
            size_t idx;
            std::string skipEdgeKey;  // key of the stored reverse of the entering edge
        };

        for (const auto& [type, typeNodes] : nodes_) {
            for (const auto& [id, node] : typeNodes) {
                std::string startKey = node.key();
                if (visited.count(startKey)) continue;

                std::vector<Frame> stack;
                visited.insert(startKey);
                stack.push_back({startKey, 0, ""});

                while (!stack.empty()) {
                    Frame& frame = stack.back();

                    const std::vector<Edge>* out = nullptr;
                    auto it = outEdges_.find(frame.key);
                    if (it != outEdges_.end()) out = &it->second;

                    bool descended = false;
                    while (out && frame.idx < out->size()) {
                        const Edge& edge = (*out)[frame.idx++];
                        if (!relType.empty() && edge.relType != relType) continue;
                        if (edge.key() == frame.skipEdgeKey) continue;  // don't go back along entering edge

                        std::string targetKey = edge.target.key();
                        if (visited.count(targetKey)) return true;  // revisit via another edge -> cycle

                        visited.insert(targetKey);
                        // Reverse of (u -> v) as stored is rel:v:u
                        std::string skip = edge.relType + ":" + edge.target.key() + ":" + edge.source.key();
                        stack.push_back({targetKey, 0, skip});  // invalidates 'frame'; break immediately
                        descended = true;
                        break;
                    }

                    if (!descended) {
                        stack.pop_back();
                    }
                }
            }
        }
        return false;
    }

public:
    /** Get all connected components */
    std::vector<std::set<NodeRef>> connectedComponents() const {
        std::unordered_set<std::string> visited;
        std::vector<std::set<NodeRef>> components;

        for (const auto& [type, typeNodes] : nodes_) {
            for (const auto& [id, node] : typeNodes) {
                NodeRef ref = node.ref();
                std::string nodeKey = ref.key();

                if (visited.find(nodeKey) == visited.end()) {
                    std::set<NodeRef> component;
                    std::queue<NodeRef> queue;
                    queue.push(ref);

                    while (!queue.empty()) {
                        NodeRef current = queue.front();
                        queue.pop();
                        std::string currentKey = current.key();

                        if (visited.find(currentKey) != visited.end()) continue;
                        visited.insert(currentKey);
                        component.insert(current);

                        // Get neighbors in both directions
                        auto neighborRefs = neighbors(current, "", Direction::Both);
                        for (const auto& neighbor : neighborRefs) {
                            if (visited.find(neighbor.key()) == visited.end()) {
                                queue.push(neighbor);
                            }
                        }
                    }

                    components.push_back(component);
                }
            }
        }

        return components;
    }

    /** Find all simple paths between two nodes (iterative DFS, no recursion) */
    std::vector<Path> allPaths(const NodeRef& start, const NodeRef& end,
                               const std::string& relType = "",
                               size_t maxHops = 5,
                               Direction direction = Direction::Out) const {
        std::vector<Path> paths;
        std::unordered_set<std::string> visited;
        std::vector<NodeRef> pathNodes;
        std::vector<Edge> pathEdges;

        struct Frame {
            NodeRef node;
            std::vector<std::pair<Edge, NodeRef>> next;
            size_t idx = 0;
        };

        auto collectEdges = [&](const NodeRef& current) {
            std::vector<std::pair<Edge, NodeRef>> edgesToFollow;
            std::string currentKey = current.key();

            if (direction == Direction::Out || direction == Direction::Both) {
                auto it = outEdges_.find(currentKey);
                if (it != outEdges_.end()) {
                    for (const auto& edge : it->second) {
                        if (relType.empty() || edge.relType == relType) {
                            edgesToFollow.push_back({edge, edge.target});
                        }
                    }
                }
            }

            if (direction == Direction::In || direction == Direction::Both) {
                auto it = inEdges_.find(currentKey);
                if (it != inEdges_.end()) {
                    for (const auto& edge : it->second) {
                        if (relType.empty() || edge.relType == relType) {
                            edgesToFollow.push_back({edge, edge.source});
                        }
                    }
                }
            }

            return edgesToFollow;
        };

        std::vector<Frame> stack;

        // Enter a node whose bookkeeping (visited/pathNodes[/pathEdges]) is already done.
        // Returns true if a frame was pushed; false if the node is a leaf (recorded or pruned).
        auto tryEnter = [&](const NodeRef& node) {
            if (pathNodes.size() > maxHops + 1) return false;
            if (node == end) {
                paths.push_back(Path(pathNodes, pathEdges));
                return false;
            }
            Frame frame;
            frame.node = node;
            frame.next = collectEdges(node);
            stack.push_back(std::move(frame));
            return true;
        };

        visited.insert(start.key());
        pathNodes.push_back(start);
        if (!tryEnter(start)) {
            return paths;
        }

        while (!stack.empty()) {
            Frame& frame = stack.back();
            bool descended = false;

            while (frame.idx < frame.next.size()) {
                auto [edge, nextNode] = frame.next[frame.idx++];
                std::string nextKey = nextNode.key();
                if (visited.count(nextKey)) continue;

                visited.insert(nextKey);
                pathNodes.push_back(nextNode);
                pathEdges.push_back(edge);

                if (tryEnter(nextNode)) {  // may invalidate 'frame'; break immediately
                    descended = true;
                    break;
                }

                // Leaf (goal reached or depth-pruned): undo immediately
                visited.erase(nextKey);
                pathNodes.pop_back();
                pathEdges.pop_back();
            }

            if (!descended) {
                std::string nodeKey = stack.back().node.key();
                stack.pop_back();
                visited.erase(nodeKey);
                pathNodes.pop_back();
                if (!pathEdges.empty()) {
                    pathEdges.pop_back();
                }
            }
        }

        return paths;
    }

public:
    // =========================================================================
    // Pattern-based Traversal
    // =========================================================================

    /** Traverse graph following a pattern of relationship types */
    std::vector<NodeRef> traverse(const NodeRef& start,
                                  const std::vector<std::pair<std::string, Direction>>& pattern,
                                  std::function<bool(const Node&)> filterFn = nullptr) const {
        std::set<std::string> current;
        current.insert(start.key());

        std::unordered_map<std::string, NodeRef> refMap;
        refMap[start.key()] = start;

        for (const auto& [relType, direction] : pattern) {
            std::set<std::string> nextLevel;

            for (const auto& key : current) {
                auto it = refMap.find(key);
                if (it != refMap.end()) {
                    auto neighborRefs = neighbors(it->second, relType, direction);
                    for (const auto& neighbor : neighborRefs) {
                        std::string neighborKey = neighbor.key();

                        if (filterFn == nullptr) {
                            nextLevel.insert(neighborKey);
                            refMap[neighborKey] = neighbor;
                        } else {
                            try {
                                const Node& node = getNodeByRef(neighbor);
                                if (filterFn(node)) {
                                    nextLevel.insert(neighborKey);
                                    refMap[neighborKey] = neighbor;
                                }
                            } catch (...) {}
                        }
                    }
                }
            }

            current = std::move(nextLevel);
            if (current.empty()) break;
        }

        std::vector<NodeRef> result;
        for (const auto& key : current) {
            result.push_back(refMap[key]);
        }
        return result;
    }

    // =========================================================================
    // Query Pattern Syntax
    // =========================================================================

    /** Execute a simple pattern query
     *
     * Pattern syntax:
     *   :type:id -[:REL]-> *           (single hop)
     *   :type:id -[:REL*N]-> *         (N hops)
     *   :type:id -[:REL*1..3]-> *      (1-3 hops range)
     */
    std::vector<NodeRef> query(const std::string& pattern) const {
        std::string p = trim(pattern);

        // Match: :type:id -[:REL*N]-> *
        std::regex hopRegex(R"(:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*)");
        std::smatch hopMatch;
        if (std::regex_match(p, hopMatch, hopRegex)) {
            std::string nodeType = hopMatch[1];
            std::string nodeId = hopMatch[2];
            std::string relType = hopMatch[3];
            int hops = std::stoi(hopMatch[4]);
            return multiHop(NodeRef(nodeType, nodeId), relType, hops);
        }

        // Match: :type:id -[:REL*N..M]-> *
        std::regex rangeRegex(R"(:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*)");
        std::smatch rangeMatch;
        if (std::regex_match(p, rangeMatch, rangeRegex)) {
            std::string nodeType = rangeMatch[1];
            std::string nodeId = rangeMatch[2];
            std::string relType = rangeMatch[3];
            int minHops = std::stoi(rangeMatch[4]);
            int maxHops = std::stoi(rangeMatch[5]);
            return multiHopRange(NodeRef(nodeType, nodeId), relType, minHops, maxHops);
        }

        // Match: :type:id -[:REL]-> *
        std::regex simpleRegex(R"(:(\w+):(\w+)\s*-\[:(\w+)\]->\s*\*)");
        std::smatch simpleMatch;
        if (std::regex_match(p, simpleMatch, simpleRegex)) {
            std::string nodeType = simpleMatch[1];
            std::string nodeId = simpleMatch[2];
            std::string relType = simpleMatch[3];
            return neighbors(NodeRef(nodeType, nodeId), relType);
        }

        throw GraphError("Invalid query pattern: " + pattern);
    }

    // =========================================================================
    // Fluent API Entry Point
    // =========================================================================

    /** Start a fluent traversal from a node */
    GraphTraversal start(const NodeRef& nodeRef) const;
};

// =============================================================================
// Fluent Traversal API
// =============================================================================

class GraphTraversal {
private:
    const ISONGraph& graph_;
    std::unordered_set<std::string> current_;
    std::unordered_set<std::string> visited_;
    std::unordered_map<std::string, NodeRef> refMap_;

public:
    GraphTraversal(const ISONGraph& graph, const NodeRef& start)
        : graph_(graph) {
        std::string startKey = start.key();
        current_.insert(startKey);
        visited_.insert(startKey);
        refMap_[startKey] = start;
    }

    /** Traverse one hop */
    GraphTraversal& hop(const std::string& relType = "",
                        Direction direction = Direction::Out) {
        std::unordered_set<std::string> nextLevel;

        for (const auto& key : current_) {
            auto it = refMap_.find(key);
            if (it != refMap_.end()) {
                auto neighborRefs = graph_.neighbors(it->second, relType, direction);
                for (const auto& neighbor : neighborRefs) {
                    std::string neighborKey = neighbor.key();
                    if (visited_.find(neighborKey) == visited_.end()) {
                        nextLevel.insert(neighborKey);
                        refMap_[neighborKey] = neighbor;
                    }
                }
            }
        }

        for (const auto& key : nextLevel) {
            visited_.insert(key);
        }
        current_ = std::move(nextLevel);
        return *this;
    }

    /** Traverse N hops */
    GraphTraversal& hops(size_t n, const std::string& relType = "",
                         Direction direction = Direction::Out) {
        for (size_t i = 0; i < n; ++i) {
            hop(relType, direction);
        }
        return *this;
    }

    /** Filter current nodes */
    GraphTraversal& filter(std::function<bool(const Node&)> fn) {
        std::unordered_set<std::string> filtered;
        for (const auto& key : current_) {
            auto it = refMap_.find(key);
            if (it != refMap_.end()) {
                try {
                    const Node& node = graph_.getNodeByRef(it->second);
                    if (fn(node)) {
                        filtered.insert(key);
                    }
                } catch (...) {}
            }
        }
        current_ = std::move(filtered);
        return *this;
    }

    /** Return current nodes as vector */
    std::vector<NodeRef> collect() const {
        std::vector<NodeRef> result;
        for (const auto& key : current_) {
            auto it = refMap_.find(key);
            if (it != refMap_.end()) {
                result.push_back(it->second);
            }
        }
        return result;
    }

    /** Count current nodes */
    size_t count() const {
        return current_.size();
    }

    /** Get first node or nullopt */
    std::optional<NodeRef> first() const {
        if (current_.empty()) return std::nullopt;
        auto it = refMap_.find(*current_.begin());
        return it != refMap_.end() ? std::optional<NodeRef>(it->second) : std::nullopt;
    }

    /** Return current nodes as Node objects */
    std::vector<Node> collectNodes() const {
        std::vector<Node> result;
        for (const auto& key : current_) {
            auto it = refMap_.find(key);
            if (it != refMap_.end()) {
                try {
                    result.push_back(graph_.getNodeByRef(it->second));
                } catch (...) {}
            }
        }
        return result;
    }
};

// Implementation of ISONGraph::start() (must be after GraphTraversal definition)
inline GraphTraversal ISONGraph::start(const NodeRef& nodeRef) const {
    return GraphTraversal(*this, nodeRef);
}

} // namespace ison_graph

#endif // ISON_GRAPH_HPP
