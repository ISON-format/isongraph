/**
 * ISONQL - Pure Property Graph Query Language for ISONGraph
 *
 * A declarative query language for property graph operations.
 *
 * Supported Query Types:
 * - NODES: Select and filter nodes
 * - EDGES: Select and filter edges
 * - TRAVERSE: Graph traversal with patterns
 * - PATH: Shortest path finding
 * - COUNT: Count nodes matching criteria
 * - SUM/AVG/MIN/MAX: Numeric aggregations
 *
 * @example
 * ```cpp
 * #include "isonql.hpp"
 *
 * using namespace isonql;
 *
 * ISONGraph graph;
 * graph.addNode("person", "alice", {{"name", "Alice"}, {"age", "30"}});
 * graph.addNode("person", "bob", {{"name", "Bob"}, {"age", "25"}});
 * graph.addEdge("KNOWS", {"person", "alice"}, {"person", "bob"}, {{"since", "2020"}});
 *
 * QueryEngine engine(graph);
 *
 * // Execute ISONQL queries
 * auto result = engine.execute("NODES person WHERE age > 25");
 * auto result2 = engine.execute("TRAVERSE person:alice -> KNOWS -> person");
 * auto result3 = engine.execute("PATH person:alice TO person:bob VIA KNOWS");
 * auto result4 = engine.execute("COUNT person WHERE age > 20");
 * auto result5 = engine.execute("AVG person.age");
 *
 * // Fluent API alternative
 * auto result6 = engine.match("person")
 *     .where("age", ">", 25)
 *     .orderBy("name")
 *     .limit(10)
 *     .execute();
 * ```
 */

#ifndef ISONQL_HPP
#define ISONQL_HPP

#include <string>
#include <vector>
#include <map>
#include <set>
#include <optional>
#include <functional>
#include <regex>
#include <chrono>
#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <variant>
#include "ison_graph.hpp"

namespace isonql {

constexpr const char* VERSION = "1.1.0";

// =============================================================================
// Enums
// =============================================================================

enum class Operator {
    EQ,          // =
    NE,          // !=
    GT,          // >
    GE,          // >=
    LT,          // <
    LE,          // <=
    IN,          // IN
    NOT_IN,      // NOT IN
    CONTAINS,    // CONTAINS
    STARTS_WITH, // STARTS_WITH
    ENDS_WITH,   // ENDS_WITH
    MATCHES,     // MATCHES (regex)
    EXISTS,      // EXISTS
    NOT_EXISTS   // NOT EXISTS
};

enum class SortOrder {
    ASC,
    DESC
};

enum class QueryType {
    NODES,
    EDGES,
    TRAVERSE,
    PATH,
    COUNT,
    SUM,
    AVG,
    MIN,
    MAX
};

// =============================================================================
// Value Type
// =============================================================================

using Value = std::variant<std::monostate, bool, int64_t, double, std::string, std::vector<std::string>>;

inline std::string valueToString(const Value& v) {
    if (std::holds_alternative<std::monostate>(v)) return "null";
    if (std::holds_alternative<bool>(v)) return std::get<bool>(v) ? "true" : "false";
    if (std::holds_alternative<int64_t>(v)) return std::to_string(std::get<int64_t>(v));
    if (std::holds_alternative<double>(v)) return std::to_string(std::get<double>(v));
    if (std::holds_alternative<std::string>(v)) return std::get<std::string>(v);
    return "";
}

// =============================================================================
// Condition
// =============================================================================

struct Condition {
    std::string field;
    Operator op;
    Value value;

    Condition(std::string f, Operator o, Value v = std::monostate{})
        : field(std::move(f)), op(o), value(std::move(v)) {}

    bool evaluate(const std::map<std::string, std::string>& properties) const {
        // EXISTS / NOT_EXISTS checks
        if (op == Operator::EXISTS) {
            return properties.count(field) > 0;
        }
        if (op == Operator::NOT_EXISTS) {
            return properties.count(field) == 0;
        }

        // Field must exist for other comparisons
        auto it = properties.find(field);
        if (it == properties.end()) {
            return false;
        }

        const std::string& propValue = it->second;

        // Try numeric comparison first
        if (std::holds_alternative<int64_t>(value) || std::holds_alternative<double>(value)) {
            try {
                double propNum = std::stod(propValue);
                double valNum = std::holds_alternative<int64_t>(value)
                    ? static_cast<double>(std::get<int64_t>(value))
                    : std::get<double>(value);

                switch (op) {
                    case Operator::EQ: return propNum == valNum;
                    case Operator::NE: return propNum != valNum;
                    case Operator::GT: return propNum > valNum;
                    case Operator::GE: return propNum >= valNum;
                    case Operator::LT: return propNum < valNum;
                    case Operator::LE: return propNum <= valNum;
                    default: break;
                }
            } catch (...) {
                return false;
            }
        }

        // String comparison
        std::string valStr = valueToString(value);

        switch (op) {
            case Operator::EQ: return propValue == valStr;
            case Operator::NE: return propValue != valStr;
            case Operator::GT: return propValue > valStr;
            case Operator::GE: return propValue >= valStr;
            case Operator::LT: return propValue < valStr;
            case Operator::LE: return propValue <= valStr;
            case Operator::CONTAINS: return propValue.find(valStr) != std::string::npos;
            case Operator::STARTS_WITH: return propValue.substr(0, valStr.size()) == valStr;
            case Operator::ENDS_WITH:
                return propValue.size() >= valStr.size() &&
                       propValue.substr(propValue.size() - valStr.size()) == valStr;
            case Operator::MATCHES: {
                try {
                    std::regex re(valStr);
                    return std::regex_match(propValue, re);
                } catch (...) {
                    return false;
                }
            }
            case Operator::IN: {
                if (std::holds_alternative<std::vector<std::string>>(value)) {
                    const auto& list = std::get<std::vector<std::string>>(value);
                    return std::find(list.begin(), list.end(), propValue) != list.end();
                }
                return false;
            }
            case Operator::NOT_IN: {
                if (std::holds_alternative<std::vector<std::string>>(value)) {
                    const auto& list = std::get<std::vector<std::string>>(value);
                    return std::find(list.begin(), list.end(), propValue) == list.end();
                }
                return true;
            }
            default: return false;
        }
    }

    std::string toString() const {
        std::string opStr;
        switch (op) {
            case Operator::EQ: opStr = "="; break;
            case Operator::NE: opStr = "!="; break;
            case Operator::GT: opStr = ">"; break;
            case Operator::GE: opStr = ">="; break;
            case Operator::LT: opStr = "<"; break;
            case Operator::LE: opStr = "<="; break;
            case Operator::IN: opStr = "IN"; break;
            case Operator::NOT_IN: opStr = "NOT IN"; break;
            case Operator::CONTAINS: opStr = "CONTAINS"; break;
            case Operator::STARTS_WITH: opStr = "STARTS_WITH"; break;
            case Operator::ENDS_WITH: opStr = "ENDS_WITH"; break;
            case Operator::MATCHES: opStr = "MATCHES"; break;
            case Operator::EXISTS: opStr = "EXISTS"; break;
            case Operator::NOT_EXISTS: opStr = "NOT EXISTS"; break;
        }

        if (op == Operator::EXISTS || op == Operator::NOT_EXISTS) {
            return opStr + " " + field;
        }

        // Quote string values (escaping '"' and newline) so the generated query
        // re-parses losslessly even when the value contains spaces.
        std::string valStr;
        if (std::holds_alternative<std::string>(value)) {
            valStr = "\"";
            for (char c : std::get<std::string>(value)) {
                if (c == '"') valStr += "\\\"";
                else if (c == '\n') valStr += "\\n";
                else if (c == '\\') valStr += "\\\\";
                else valStr += c;
            }
            valStr += "\"";
        } else if (std::holds_alternative<std::vector<std::string>>(value)) {
            valStr = "(";
            const auto& list = std::get<std::vector<std::string>>(value);
            for (size_t i = 0; i < list.size(); ++i) {
                if (i > 0) valStr += ", ";
                valStr += "\"";
                for (char c : list[i]) {
                    if (c == '"') valStr += "\\\"";
                    else if (c == '\n') valStr += "\\n";
                    else if (c == '\\') valStr += "\\\\";
                    else valStr += c;
                }
                valStr += "\"";
            }
            valStr += ")";
        } else {
            valStr = valueToString(value);
        }

        return field + " " + opStr + " " + valStr;
    }
};

// =============================================================================
// Query Result
// =============================================================================

struct NodeResult {
    std::string type;
    std::string id;
    std::map<std::string, std::string> properties;
};

struct EdgeResult {
    std::string relType;
    ison_graph::NodeRef source;
    ison_graph::NodeRef target;
    std::map<std::string, std::string> properties;
};

struct PathResult {
    std::vector<ison_graph::NodeRef> nodes;
    std::vector<EdgeResult> edges;
    size_t length;
};

using ResultData = std::variant<
    std::vector<NodeResult>,
    std::vector<EdgeResult>,
    std::vector<ison_graph::NodeRef>,
    std::vector<PathResult>,
    int64_t,
    double
>;

class QueryResult {
public:
    ResultData data;
    size_t count = 0;
    size_t totalCount = 0;
    double executionTimeMs = 0.0;
    std::string query;
    std::string queryType;

    QueryResult() = default;

    bool empty() const { return count == 0; }

    std::vector<NodeResult> toNodes() const {
        if (std::holds_alternative<std::vector<NodeResult>>(data)) {
            return std::get<std::vector<NodeResult>>(data);
        }
        return {};
    }

    std::vector<EdgeResult> toEdges() const {
        if (std::holds_alternative<std::vector<EdgeResult>>(data)) {
            return std::get<std::vector<EdgeResult>>(data);
        }
        return {};
    }

    std::vector<ison_graph::NodeRef> toNodeRefs() const {
        if (std::holds_alternative<std::vector<ison_graph::NodeRef>>(data)) {
            return std::get<std::vector<ison_graph::NodeRef>>(data);
        }
        return {};
    }

    std::optional<int64_t> toInt() const {
        if (std::holds_alternative<int64_t>(data)) {
            return std::get<int64_t>(data);
        }
        return std::nullopt;
    }

    std::optional<double> toDouble() const {
        if (std::holds_alternative<double>(data)) {
            return std::get<double>(data);
        }
        if (std::holds_alternative<int64_t>(data)) {
            return static_cast<double>(std::get<int64_t>(data));
        }
        return std::nullopt;
    }
};

// =============================================================================
// Parsed Query Structure
// =============================================================================

struct ParsedQuery {
    QueryType type;
    std::optional<std::string> nodeType;
    std::optional<std::string> relType;
    // WHERE clause with AND-precedence: outer vector = OR-groups,
    // inner vector = AND-ed conditions. Empty means "match everything".
    std::vector<std::vector<Condition>> conditions;
    std::optional<std::string> orderBy;
    SortOrder orderDir = SortOrder::ASC;
    std::optional<size_t> limit;
    size_t offset = 0;
    std::optional<std::vector<std::string>> returnFields;

    // For TRAVERSE
    std::optional<ison_graph::NodeRef> start;
    struct TraverseStep {
        ison_graph::Direction direction;
        std::string relType;
        std::string targetType;
    };
    std::vector<TraverseStep> pattern;
    std::optional<size_t> maxDepth;

    // For PATH
    std::optional<ison_graph::NodeRef> source;
    std::optional<ison_graph::NodeRef> target;
    std::optional<std::string> via;
    size_t maxHops = 10;

    // For aggregations
    std::optional<std::string> property;
};

// =============================================================================
// ISONQL Parser
// =============================================================================

class ISONQLParser {
public:
    ParsedQuery parse(const std::string& query) {
        tokens_ = tokenize(query);
        pos_ = 0;

        if (tokens_.empty()) {
            throw std::runtime_error("Empty query");
        }

        std::string keyword = toUpper(tokens_[0]);

        if (keyword == "NODES") return parseNodesQuery();
        if (keyword == "EDGES") return parseEdgesQuery();
        if (keyword == "TRAVERSE") return parseTraverseQuery();
        if (keyword == "PATH") return parsePathQuery();
        if (keyword == "COUNT") return parseCountQuery();
        if (keyword == "SUM" || keyword == "AVG" || keyword == "MIN" || keyword == "MAX") {
            return parseAggregationQuery(keyword);
        }

        throw std::runtime_error("Unknown query type: " + keyword +
            ". Supported: NODES, EDGES, TRAVERSE, PATH, COUNT, SUM, AVG, MIN, MAX");
    }

private:
    std::vector<std::string> tokens_;
    size_t pos_ = 0;

    static std::string toUpper(const std::string& s) {
        std::string result = s;
        std::transform(result.begin(), result.end(), result.begin(), ::toupper);
        return result;
    }

    std::vector<std::string> tokenize(const std::string& query) {
        std::vector<std::string> tokens;
        size_t i = 0;

        while (i < query.size()) {
            // Skip whitespace
            if (std::isspace(static_cast<unsigned char>(query[i]))) {
                i++;
                continue;
            }

            // String literals (unescape \" \' \n \\)
            if (query[i] == '"' || query[i] == '\'') {
                char quote = query[i];
                i++;
                std::string literal;
                while (i < query.size() && query[i] != quote) {
                    if (query[i] == '\\' && i + 1 < query.size()) {
                        char next = query[i + 1];
                        if (next == 'n') literal += '\n';
                        else literal += next;
                        i += 2;
                    } else {
                        literal += query[i];
                        i++;
                    }
                }
                tokens.push_back(literal);
                i++;
                continue;
            }

            // Multi-character operators
            if (i + 1 < query.size()) {
                std::string two = query.substr(i, 2);
                if (two == "==" || two == "!=" || two == ">=" || two == "<=" ||
                    two == "<>" || two == "->" || two == "<-" || two == "--") {
                    tokens.push_back(two);
                    i += 2;
                    continue;
                }
            }

            // Single-character operators
            if (query[i] == '=' || query[i] == '<' || query[i] == '>' ||
                query[i] == '!' || query[i] == '(' || query[i] == ')' ||
                query[i] == ',' || query[i] == '.') {
                tokens.push_back(std::string(1, query[i]));
                i++;
                continue;
            }

            // Node reference :type:id
            if (query[i] == ':') {
                size_t start = i;
                i++;
                while (i < query.size() && (std::isalnum(static_cast<unsigned char>(query[i])) ||
                                            query[i] == ':' || query[i] == '_' || query[i] == '-')) {
                    i++;
                }
                tokens.push_back(query.substr(start, i - start));
                continue;
            }

            // Words and numbers (a ':' followed by an alphanumeric/underscore joins the
            // word so that node references like "person:alice" stay one token)
            if (std::isalnum(static_cast<unsigned char>(query[i])) || query[i] == '_') {
                size_t start = i;
                while (i < query.size()) {
                    char c = query[i];
                    if (std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '.' || c == '-') {
                        i++;
                        continue;
                    }
                    if (c == ':' && i + 1 < query.size() &&
                        (std::isalnum(static_cast<unsigned char>(query[i + 1])) || query[i + 1] == '_')) {
                        i++;
                        continue;
                    }
                    break;
                }
                tokens.push_back(query.substr(start, i - start));
                continue;
            }

            i++;
        }

        return tokens;
    }

    std::string current() const {
        if (pos_ < tokens_.size()) return tokens_[pos_];
        return "";
    }

    std::string advance() {
        if (pos_ < tokens_.size()) return tokens_[pos_++];
        return "";
    }

    bool match(const std::vector<std::string>& expected) {
        std::string curr = toUpper(current());
        for (const auto& e : expected) {
            if (curr == toUpper(e)) return true;
        }
        return false;
    }

    void expect(const std::string& expected) {
        std::string token = advance();
        if (toUpper(token) != toUpper(expected)) {
            throw std::runtime_error("Expected '" + expected + "', got '" + token + "'");
        }
    }

    // -------------------------------------------------------------------------
    // Query Parsers
    // -------------------------------------------------------------------------

    ParsedQuery parseNodesQuery() {
        ParsedQuery result;
        result.type = QueryType::NODES;
        advance(); // Skip 'NODES'

        // Node type (optional)
        if (!current().empty() && !match({"WHERE", "ORDER", "LIMIT", "RETURN"})) {
            result.nodeType = advance();
        }

        // WHERE clause
        if (match({"WHERE"})) {
            advance();
            result.conditions = parseConditions();
        }

        // ORDER BY clause
        if (match({"ORDER"})) {
            advance();
            expect("BY");
            result.orderBy = advance();
            if (match({"ASC", "DESC"})) {
                result.orderDir = (toUpper(advance()) == "DESC") ? SortOrder::DESC : SortOrder::ASC;
            }
        }

        // LIMIT clause
        if (match({"LIMIT"})) {
            advance();
            result.limit = static_cast<size_t>(std::stoll(advance()));
        }

        // OFFSET clause
        if (match({"OFFSET"})) {
            advance();
            result.offset = static_cast<size_t>(std::stoll(advance()));
        }

        // RETURN clause
        if (match({"RETURN"})) {
            advance();
            result.returnFields = parseFieldList();
        }

        return result;
    }

    ParsedQuery parseEdgesQuery() {
        ParsedQuery result;
        result.type = QueryType::EDGES;
        advance(); // Skip 'EDGES'

        // Edge type (optional)
        if (!current().empty() && !match({"WHERE", "LIMIT"})) {
            result.relType = advance();
        }

        // WHERE clause
        if (match({"WHERE"})) {
            advance();
            result.conditions = parseConditions();
        }

        // LIMIT clause
        if (match({"LIMIT"})) {
            advance();
            result.limit = static_cast<size_t>(std::stoll(advance()));
        }

        return result;
    }

    ParsedQuery parseTraverseQuery() {
        ParsedQuery result;
        result.type = QueryType::TRAVERSE;
        advance(); // Skip 'TRAVERSE'

        // Start node
        result.start = parseNodeRef(advance());

        // Parse traversal pattern: -> REL -> target
        while (match({"->", "<-", "--"})) {
            std::string dir1 = advance();
            std::string relType = advance();

            ParsedQuery::TraverseStep step;
            step.relType = relType;

            if (match({"->", "<-", "--"})) {
                std::string dir2 = advance();
                step.direction = directionFromArrows(dir1, dir2);
                if (!current().empty() && !match({"MAX", "LIMIT"})) {
                    step.targetType = advance();
                } else {
                    step.targetType = "*";
                }
            } else {
                step.direction = directionFromArrows(dir1, dir1);
                step.targetType = "*";
            }

            result.pattern.push_back(step);
        }

        // MAX depth
        if (match({"MAX"})) {
            advance();
            result.maxDepth = static_cast<size_t>(std::stoll(advance()));
        }

        // LIMIT
        if (match({"LIMIT"})) {
            advance();
            result.limit = static_cast<size_t>(std::stoll(advance()));
        }

        return result;
    }

    ParsedQuery parsePathQuery() {
        ParsedQuery result;
        result.type = QueryType::PATH;
        advance(); // Skip 'PATH'

        // Source node
        result.source = parseNodeRef(advance());

        // TO keyword
        expect("TO");

        // Target node
        result.target = parseNodeRef(advance());

        // VIA relationship type (optional)
        if (match({"VIA"})) {
            advance();
            result.via = advance();
        }

        // MAX hops
        if (match({"MAX"})) {
            advance();
            result.maxHops = static_cast<size_t>(std::stoll(advance()));
        }

        return result;
    }

    ParsedQuery parseCountQuery() {
        ParsedQuery result;
        result.type = QueryType::COUNT;
        advance(); // Skip 'COUNT'

        // Node type
        if (!current().empty() && !match({"WHERE"})) {
            result.nodeType = advance();
        }

        // WHERE clause
        if (match({"WHERE"})) {
            advance();
            result.conditions = parseConditions();
        }

        return result;
    }

    ParsedQuery parseAggregationQuery(const std::string& aggType) {
        ParsedQuery result;
        if (aggType == "SUM") result.type = QueryType::SUM;
        else if (aggType == "AVG") result.type = QueryType::AVG;
        else if (aggType == "MIN") result.type = QueryType::MIN;
        else if (aggType == "MAX") result.type = QueryType::MAX;

        advance(); // Skip aggregation keyword

        // type.property
        std::string typeProp = advance();
        size_t dotPos = typeProp.find('.');
        if (dotPos != std::string::npos) {
            result.nodeType = typeProp.substr(0, dotPos);
            result.property = typeProp.substr(dotPos + 1);
        } else {
            result.property = typeProp;
        }

        // WHERE clause
        if (match({"WHERE"})) {
            advance();
            result.conditions = parseConditions();
        }

        return result;
    }

    // -------------------------------------------------------------------------
    // Condition Parsing
    // -------------------------------------------------------------------------

    // Parses "c1 AND c2 OR c3 AND c4" into OR-groups of AND-ed conditions
    // (AND binds tighter than OR): [[c1, c2], [c3, c4]]
    std::vector<std::vector<Condition>> parseConditions() {
        std::vector<std::vector<Condition>> groups;
        std::vector<Condition> currentGroup;

        while (true) {
            auto cond = parseSingleCondition();
            if (cond) {
                currentGroup.push_back(*cond);
            } else {
                break;
            }

            if (match({"AND"})) {
                advance();
                continue;
            }
            if (match({"OR"})) {
                advance();
                groups.push_back(std::move(currentGroup));
                currentGroup.clear();
                continue;
            }
            break;
        }

        if (!currentGroup.empty()) {
            groups.push_back(std::move(currentGroup));
        }

        return groups;
    }

    std::optional<Condition> parseSingleCondition() {
        if (current().empty()) return std::nullopt;

        // EXISTS / NOT EXISTS
        if (match({"EXISTS"})) {
            advance();
            std::string field = advance();
            return Condition(field, Operator::EXISTS);
        }

        if (match({"NOT"})) {
            advance();
            if (match({"EXISTS"})) {
                advance();
                std::string field = advance();
                return Condition(field, Operator::NOT_EXISTS);
            }
        }

        std::string field = advance();
        if (field.empty() || isKeyword(field)) {
            pos_--;
            return std::nullopt;
        }

        std::string opToken = current();
        if (opToken.empty()) return std::nullopt;

        Operator op;
        std::string opUpper = toUpper(opToken);

        if (opToken == "=" || opToken == "==") { advance(); op = Operator::EQ; }
        else if (opToken == "!=" || opToken == "<>") { advance(); op = Operator::NE; }
        else if (opToken == ">") { advance(); op = Operator::GT; }
        else if (opToken == ">=") { advance(); op = Operator::GE; }
        else if (opToken == "<") { advance(); op = Operator::LT; }
        else if (opToken == "<=") { advance(); op = Operator::LE; }
        else if (opUpper == "IN") { advance(); op = Operator::IN; }
        else if (opUpper == "CONTAINS") { advance(); op = Operator::CONTAINS; }
        else if (opUpper == "STARTS_WITH") { advance(); op = Operator::STARTS_WITH; }
        else if (opUpper == "ENDS_WITH") { advance(); op = Operator::ENDS_WITH; }
        else if (opUpper == "MATCHES") { advance(); op = Operator::MATCHES; }
        else if (opUpper == "EXISTS") {
            advance();
            return Condition(field, Operator::EXISTS);
        }
        else if (opUpper == "NOT") {
            std::string nxt = (pos_ + 1 < tokens_.size()) ? toUpper(tokens_[pos_ + 1]) : "";
            if (nxt == "EXISTS") {
                advance();
                advance();
                return Condition(field, Operator::NOT_EXISTS);
            }
            if (nxt == "IN") {
                advance();
                advance();
                op = Operator::NOT_IN;
            } else {
                throw std::runtime_error("Parse error: expected EXISTS or IN after NOT, got '" + nxt + "'");
            }
        }
        else {
            throw std::runtime_error("Parse error: unknown operator '" + opToken + "' in condition");
        }

        Value value = parseValue();
        return Condition(field, op, value);
    }

    Value parseValue() {
        std::string token = current();
        if (token.empty()) return std::monostate{};

        // List: (val1, val2, ...)
        if (token == "(") {
            advance();
            std::vector<std::string> values;
            while (current() != ")") {
                if (current().empty()) {
                    throw std::runtime_error("Parse error: unclosed list, expected ')'");
                }
                values.push_back(advance());
                if (current() == ",") advance();
            }
            advance(); // Skip ')'
            return values;
        }

        return parseSingleValue();
    }

    Value parseSingleValue() {
        std::string token = advance();
        if (token.empty()) return std::monostate{};

        std::string upper = toUpper(token);

        // Booleans
        if (upper == "TRUE") return true;
        if (upper == "FALSE") return false;

        // Null
        if (upper == "NULL" || upper == "NONE" || upper == "NIL") {
            return std::monostate{};
        }

        // Numbers
        try {
            if (token.find('.') != std::string::npos) {
                return std::stod(token);
            }
            return static_cast<int64_t>(std::stoll(token));
        } catch (...) {}

        // String
        return token;
    }

    std::vector<std::string> parseFieldList() {
        std::vector<std::string> fields;
        while (!current().empty() && !match({"LIMIT", "OFFSET", "ORDER"})) {
            fields.push_back(advance());
            if (current() == ",") advance();
            else break;
        }
        return fields;
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    ison_graph::NodeRef parseNodeRef(const std::string& token) {
        std::string t = token;
        if (!t.empty() && t[0] == ':') t = t.substr(1);

        size_t colonPos = t.find(':');
        if (colonPos == std::string::npos) {
            throw std::runtime_error("Invalid node reference: " + token + ". Expected format: type:id");
        }

        return ison_graph::NodeRef{t.substr(0, colonPos), t.substr(colonPos + 1)};
    }

    ison_graph::Direction directionFromArrows(const std::string& arrow1, const std::string& arrow2) {
        if (arrow1 == "->" || arrow2 == "->") return ison_graph::Direction::Out;
        if (arrow1 == "<-" || arrow2 == "<-") return ison_graph::Direction::In;
        return ison_graph::Direction::Both;
    }

    bool isKeyword(const std::string& token) {
        static const std::set<std::string> keywords = {
            "NODES", "EDGES", "TRAVERSE", "PATH", "COUNT", "SUM", "AVG", "MIN", "MAX",
            "WHERE", "AND", "OR", "NOT", "ORDER", "BY", "ASC", "DESC", "LIMIT", "OFFSET",
            "TO", "VIA", "RETURN", "AS", "IN", "CONTAINS", "STARTS_WITH", "ENDS_WITH",
            "MATCHES", "EXISTS", "TRUE", "FALSE", "NULL", "NONE", "NIL"
        };
        return keywords.count(toUpper(token)) > 0;
    }
};

// =============================================================================
// Forward declarations
// =============================================================================

class QueryBuilder;
class EdgeQueryBuilder;

// =============================================================================
// Query Engine
// =============================================================================

class QueryEngine {
public:
    explicit QueryEngine(ison_graph::ISONGraph& graph) : graph_(graph) {}

    QueryResult execute(const std::string& query) {
        auto startTime = std::chrono::high_resolution_clock::now();

        ParsedQuery parsed;
        try {
            parsed = parser_.parse(query);
        } catch (const std::exception& e) {
            throw std::runtime_error(std::string("Parse error: ") + e.what());
        }

        QueryResult result;
        result.query = query;

        switch (parsed.type) {
            case QueryType::NODES:
                result = executeNodes(parsed);
                result.queryType = "NODES";
                break;
            case QueryType::EDGES:
                result = executeEdges(parsed);
                result.queryType = "EDGES";
                break;
            case QueryType::TRAVERSE:
                result = executeTraverse(parsed);
                result.queryType = "TRAVERSE";
                break;
            case QueryType::PATH:
                result = executePath(parsed);
                result.queryType = "PATH";
                break;
            case QueryType::COUNT:
                result = executeCount(parsed);
                result.queryType = "COUNT";
                break;
            case QueryType::SUM:
            case QueryType::AVG:
            case QueryType::MIN:
            case QueryType::MAX:
                result = executeAggregation(parsed);
                result.queryType = (parsed.type == QueryType::SUM) ? "SUM" :
                                   (parsed.type == QueryType::AVG) ? "AVG" :
                                   (parsed.type == QueryType::MIN) ? "MIN" : "MAX";
                break;
        }

        auto endTime = std::chrono::high_resolution_clock::now();
        result.executionTimeMs = std::chrono::duration<double, std::milli>(endTime - startTime).count();
        result.query = query;

        return result;
    }

    QueryBuilder match(const std::string& nodeType);
    EdgeQueryBuilder matchEdges(const std::string& relType = "");

    ison_graph::ISONGraph& graph() { return graph_; }

private:
    ison_graph::ISONGraph& graph_;
    ISONQLParser parser_;

    // OR across groups, AND within a group. No groups = match everything.
    bool matchesConditions(const std::map<std::string, std::string>& properties,
                          const std::vector<std::vector<Condition>>& conditionGroups) {
        if (conditionGroups.empty()) return true;
        for (const auto& group : conditionGroups) {
            bool allMatch = true;
            for (const auto& cond : group) {
                if (!cond.evaluate(properties)) {
                    allMatch = false;
                    break;
                }
            }
            if (allMatch) return true;
        }
        return false;
    }

    QueryResult executeNodes(const ParsedQuery& parsed) {
        QueryResult result;
        std::vector<NodeResult> nodes;

        // Get all nodes of the specified type
        for (const auto& [type, nodeMap] : graph_.getNodes()) {
            if (parsed.nodeType && type != *parsed.nodeType) continue;

            for (const auto& [id, node] : nodeMap) {
                if (matchesConditions(node.properties, parsed.conditions)) {
                    nodes.push_back({node.type, node.id, node.properties});
                }
            }
        }

        result.totalCount = nodes.size();

        // Sort
        if (parsed.orderBy) {
            std::sort(nodes.begin(), nodes.end(), [&](const NodeResult& a, const NodeResult& b) {
                auto itA = a.properties.find(*parsed.orderBy);
                auto itB = b.properties.find(*parsed.orderBy);
                std::string valA = (itA != a.properties.end()) ? itA->second : "";
                std::string valB = (itB != b.properties.end()) ? itB->second : "";

                if (parsed.orderDir == SortOrder::DESC) {
                    return valA > valB;
                }
                return valA < valB;
            });
        }

        // Pagination
        size_t start = parsed.offset;
        if (start < nodes.size()) {
            nodes.erase(nodes.begin(), nodes.begin() + start);
        } else {
            nodes.clear();
        }

        if (parsed.limit && *parsed.limit < nodes.size()) {
            nodes.resize(*parsed.limit);
        }

        // RETURN projection: keep only the requested property fields
        if (parsed.returnFields && !parsed.returnFields->empty()) {
            for (auto& node : nodes) {
                std::map<std::string, std::string> projected;
                for (const auto& field : *parsed.returnFields) {
                    auto it = node.properties.find(field);
                    if (it != node.properties.end()) {
                        projected[field] = it->second;
                    }
                }
                node.properties = std::move(projected);
            }
        }

        result.data = std::move(nodes);
        result.count = std::get<std::vector<NodeResult>>(result.data).size();
        return result;
    }

    QueryResult executeEdges(const ParsedQuery& parsed) {
        QueryResult result;
        std::vector<EdgeResult> edges;

        auto graphEdges = parsed.relType
            ? graph_.getEdges(*parsed.relType)
            : graph_.getAllEdges();

        for (const auto& edge : graphEdges) {
            if (matchesConditions(edge.properties, parsed.conditions)) {
                edges.push_back({edge.relType, edge.source, edge.target, edge.properties});
            }
        }

        result.totalCount = edges.size();

        if (parsed.limit && *parsed.limit < edges.size()) {
            edges.resize(*parsed.limit);
        }

        result.data = std::move(edges);
        result.count = std::get<std::vector<EdgeResult>>(result.data).size();
        return result;
    }

    QueryResult executeTraverse(const ParsedQuery& parsed) {
        QueryResult result;

        if (!parsed.start) {
            throw std::runtime_error("TRAVERSE requires a start node");
        }

        std::set<std::string> currentSet;
        std::set<std::string> visited;

        auto refKey = [](const ison_graph::NodeRef& ref) {
            return ref.type + ":" + ref.id;
        };

        currentSet.insert(refKey(*parsed.start));
        visited.insert(refKey(*parsed.start));

        for (const auto& step : parsed.pattern) {
            std::set<std::string> nextLevel;

            for (const auto& key : currentSet) {
                size_t colonPos = key.find(':');
                ison_graph::NodeRef nodeRef{key.substr(0, colonPos), key.substr(colonPos + 1)};

                auto neighbors = graph_.neighbors(nodeRef, step.relType, step.direction);
                for (const auto& neighbor : neighbors) {
                    std::string neighborKey = refKey(neighbor);
                    if (visited.find(neighborKey) == visited.end()) {
                        if (step.targetType == "*" || neighbor.type == step.targetType) {
                            nextLevel.insert(neighborKey);
                        }
                    }
                }
            }

            for (const auto& key : nextLevel) {
                visited.insert(key);
            }
            currentSet = nextLevel;

            if (currentSet.empty()) break;
        }

        // Convert to NodeRef vector
        std::vector<ison_graph::NodeRef> refs;
        for (const auto& key : currentSet) {
            size_t colonPos = key.find(':');
            refs.push_back({key.substr(0, colonPos), key.substr(colonPos + 1)});
        }

        result.totalCount = refs.size();

        if (parsed.limit && *parsed.limit < refs.size()) {
            refs.resize(*parsed.limit);
        }

        result.data = std::move(refs);
        result.count = std::get<std::vector<ison_graph::NodeRef>>(result.data).size();
        return result;
    }

    QueryResult executePath(const ParsedQuery& parsed) {
        QueryResult result;

        if (!parsed.source || !parsed.target) {
            throw std::runtime_error("PATH requires source and target nodes");
        }

        auto path = graph_.shortestPath(*parsed.source, *parsed.target,
                                        parsed.via.value_or(""), parsed.maxHops);

        std::vector<PathResult> paths;
        if (path.has_value()) {
            PathResult pr;
            pr.nodes = path->nodes;
            pr.length = path->length();
            for (const auto& edge : path->edges) {
                pr.edges.push_back({edge.relType, edge.source, edge.target, edge.properties});
            }
            paths.push_back(pr);
        }

        result.data = std::move(paths);
        result.count = std::get<std::vector<PathResult>>(result.data).size();
        result.totalCount = result.count;
        return result;
    }

    QueryResult executeCount(const ParsedQuery& parsed) {
        QueryResult result;
        int64_t count = 0;

        for (const auto& [type, nodeMap] : graph_.getNodes()) {
            if (parsed.nodeType && type != *parsed.nodeType) continue;

            for (const auto& [id, node] : nodeMap) {
                if (matchesConditions(node.properties, parsed.conditions)) {
                    count++;
                }
            }
        }

        result.data = count;
        result.count = 1;
        result.totalCount = count;
        return result;
    }

    QueryResult executeAggregation(const ParsedQuery& parsed) {
        QueryResult result;

        if (!parsed.property) {
            throw std::runtime_error("Aggregation requires a property name");
        }

        std::vector<double> values;

        for (const auto& [type, nodeMap] : graph_.getNodes()) {
            if (parsed.nodeType && type != *parsed.nodeType) continue;

            for (const auto& [id, node] : nodeMap) {
                if (matchesConditions(node.properties, parsed.conditions)) {
                    auto it = node.properties.find(*parsed.property);
                    if (it != node.properties.end()) {
                        try {
                            values.push_back(std::stod(it->second));
                        } catch (...) {}
                    }
                }
            }
        }

        if (values.empty()) {
            result.data = 0.0;
            result.count = 0;
            result.totalCount = 0;
            return result;
        }

        double aggResult = 0.0;
        switch (parsed.type) {
            case QueryType::SUM:
                for (double v : values) aggResult += v;
                break;
            case QueryType::AVG:
                for (double v : values) aggResult += v;
                aggResult /= values.size();
                break;
            case QueryType::MIN:
                aggResult = *std::min_element(values.begin(), values.end());
                break;
            case QueryType::MAX:
                aggResult = *std::max_element(values.begin(), values.end());
                break;
            default:
                break;
        }

        result.data = aggResult;
        result.count = 1;
        result.totalCount = values.size();
        return result;
    }
};

// =============================================================================
// Query Builder (Fluent API)
// =============================================================================

class QueryBuilder {
public:
    QueryBuilder(QueryEngine& engine, const std::string& nodeType)
        : engine_(engine), nodeType_(nodeType) {}

    QueryBuilder& where(const std::string& field, const std::string& op, const Value& value) {
        Operator opEnum = Operator::EQ;
        std::string opUpper = op;
        std::transform(opUpper.begin(), opUpper.end(), opUpper.begin(), ::toupper);

        if (op == "=" || op == "==") opEnum = Operator::EQ;
        else if (op == "!=" || op == "<>") opEnum = Operator::NE;
        else if (op == ">") opEnum = Operator::GT;
        else if (op == ">=") opEnum = Operator::GE;
        else if (op == "<") opEnum = Operator::LT;
        else if (op == "<=") opEnum = Operator::LE;
        else if (opUpper == "IN") opEnum = Operator::IN;
        else if (opUpper == "NOT IN") opEnum = Operator::NOT_IN;
        else if (opUpper == "CONTAINS") opEnum = Operator::CONTAINS;
        else if (opUpper == "STARTS_WITH") opEnum = Operator::STARTS_WITH;
        else if (opUpper == "ENDS_WITH") opEnum = Operator::ENDS_WITH;
        else if (opUpper == "MATCHES") opEnum = Operator::MATCHES;

        conditions_.emplace_back(field, opEnum, value);
        return *this;
    }

    QueryBuilder& whereExists(const std::string& field) {
        conditions_.emplace_back(field, Operator::EXISTS);
        return *this;
    }

    QueryBuilder& whereNotExists(const std::string& field) {
        conditions_.emplace_back(field, Operator::NOT_EXISTS);
        return *this;
    }

    QueryBuilder& orderBy(const std::string& field, const std::string& direction = "ASC") {
        orderBy_ = field;
        orderDir_ = (direction == "DESC") ? SortOrder::DESC : SortOrder::ASC;
        return *this;
    }

    QueryBuilder& limit(size_t n) {
        limit_ = n;
        return *this;
    }

    QueryBuilder& offset(size_t n) {
        offset_ = n;
        return *this;
    }

    QueryBuilder& returnFields(const std::vector<std::string>& fields) {
        returnFields_ = fields;
        return *this;
    }

    QueryResult execute() {
        auto startTime = std::chrono::high_resolution_clock::now();

        // Build query string (clause order matches the parser:
        // WHERE, ORDER BY, LIMIT, OFFSET, RETURN)
        std::string queryStr = "NODES " + nodeType_;
        if (!conditions_.empty()) {
            queryStr += " WHERE ";
            for (size_t i = 0; i < conditions_.size(); i++) {
                if (i > 0) queryStr += " AND ";
                queryStr += conditions_[i].toString();
            }
        }
        if (orderBy_) {
            queryStr += " ORDER BY " + *orderBy_;
            queryStr += (orderDir_ == SortOrder::DESC) ? " DESC" : " ASC";
        }
        if (limit_) {
            queryStr += " LIMIT " + std::to_string(*limit_);
        }
        if (offset_ > 0) {
            queryStr += " OFFSET " + std::to_string(offset_);
        }
        if (returnFields_ && !returnFields_->empty()) {
            queryStr += " RETURN ";
            for (size_t i = 0; i < returnFields_->size(); i++) {
                if (i > 0) queryStr += ", ";
                queryStr += (*returnFields_)[i];
            }
        }

        QueryResult result = engine_.execute(queryStr);

        auto endTime = std::chrono::high_resolution_clock::now();
        result.executionTimeMs = std::chrono::duration<double, std::milli>(endTime - startTime).count();

        return result;
    }

    int64_t count() {
        std::string queryStr = "COUNT " + nodeType_;
        if (!conditions_.empty()) {
            queryStr += " WHERE ";
            for (size_t i = 0; i < conditions_.size(); i++) {
                if (i > 0) queryStr += " AND ";
                queryStr += conditions_[i].toString();
            }
        }

        auto result = engine_.execute(queryStr);
        return result.toInt().value_or(0);
    }

private:
    QueryEngine& engine_;
    std::string nodeType_;
    std::vector<Condition> conditions_;
    std::optional<std::string> orderBy_;
    SortOrder orderDir_ = SortOrder::ASC;
    std::optional<size_t> limit_;
    size_t offset_ = 0;
    std::optional<std::vector<std::string>> returnFields_;
};

// =============================================================================
// Edge Query Builder
// =============================================================================

class EdgeQueryBuilder {
public:
    EdgeQueryBuilder(QueryEngine& engine, const std::string& relType = "")
        : engine_(engine), relType_(relType) {}

    EdgeQueryBuilder& where(const std::string& field, const std::string& op, const Value& value) {
        Operator opEnum = Operator::EQ;
        if (op == "=" || op == "==") opEnum = Operator::EQ;
        else if (op == "!=" || op == "<>") opEnum = Operator::NE;
        else if (op == ">") opEnum = Operator::GT;
        else if (op == ">=") opEnum = Operator::GE;
        else if (op == "<") opEnum = Operator::LT;
        else if (op == "<=") opEnum = Operator::LE;

        conditions_.emplace_back(field, opEnum, value);
        return *this;
    }

    EdgeQueryBuilder& limit(size_t n) {
        limit_ = n;
        return *this;
    }

    QueryResult execute() {
        std::string queryStr = "EDGES";
        if (!relType_.empty()) queryStr += " " + relType_;
        if (!conditions_.empty()) {
            queryStr += " WHERE ";
            for (size_t i = 0; i < conditions_.size(); i++) {
                if (i > 0) queryStr += " AND ";
                queryStr += conditions_[i].toString();
            }
        }
        if (limit_) {
            queryStr += " LIMIT " + std::to_string(*limit_);
        }

        return engine_.execute(queryStr);
    }

private:
    QueryEngine& engine_;
    std::string relType_;
    std::vector<Condition> conditions_;
    std::optional<size_t> limit_;
};

// =============================================================================
// QueryEngine method implementations
// =============================================================================

inline QueryBuilder QueryEngine::match(const std::string& nodeType) {
    return QueryBuilder(*this, nodeType);
}

inline EdgeQueryBuilder QueryEngine::matchEdges(const std::string& relType) {
    return EdgeQueryBuilder(*this, relType);
}

} // namespace isonql

#endif // ISONQL_HPP
