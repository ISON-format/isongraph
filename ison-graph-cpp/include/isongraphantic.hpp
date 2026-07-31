/**
 * ISONGraphantic - Graph Schema Validation for ISONGraph
 *
 * A header-only C++17 library for graph schema validation.
 *
 * @example
 * ```cpp
 * #include "isongraphantic.hpp"
 *
 * using namespace isongraphantic;
 *
 * auto person = NodeType("person")
 *     .field("name", StringField().required().max_len(100))
 *     .field("age", IntField().min(0).max(150));
 *
 * auto knows = EdgeType("KNOWS")
 *     .from_node(person)
 *     .to_node(person)
 *     .no_self_loop();
 *
 * auto schema = GraphSchema("social")
 *     .node_type(person)
 *     .edge_type(knows);
 *
 * auto result = schema.validate(graph);
 * ```
 */

#ifndef ISONGRAPHANTIC_HPP
#define ISONGRAPHANTIC_HPP

#include <string>
#include <map>
#include <vector>
#include <set>
#include <optional>
#include <functional>
#include <regex>
#include <memory>
#include "ison_graph.hpp"

namespace isongraphantic {

constexpr const char* VERSION = "1.1.0";

// =============================================================================
// Enums
// =============================================================================

enum class Cardinality {
    ONE_TO_ONE,
    ONE_TO_MANY,
    MANY_TO_ONE,
    MANY_TO_MANY
};

enum class ErrorCode {
    // Field errors
    REQUIRED_FIELD,
    INVALID_TYPE,
    MIN_VALUE,
    MAX_VALUE,
    MIN_LENGTH,
    MAX_LENGTH,
    PATTERN_MISMATCH,
    INVALID_EMAIL,
    INVALID_ENUM,
    // Reference errors
    REF_NOT_FOUND,
    REF_WRONG_TYPE,
    // Edge errors
    SELF_LOOP,
    DUPLICATE_EDGE,
    CARDINALITY_VIOLATION,
    INVALID_SOURCE_TYPE,
    INVALID_TARGET_TYPE,
    // Graph errors
    CYCLE_DETECTED,
    NOT_CONNECTED,
    ORPHAN_NODE,
    MAX_DEPTH_EXCEEDED
};

// =============================================================================
// Validation Error
// =============================================================================

struct ValidationError {
    ErrorCode code;
    std::string message;
    std::string location;
    std::map<std::string, std::string> context;

    ValidationError(ErrorCode c, std::string msg)
        : code(c), message(std::move(msg)) {}

    ValidationError& with_location(std::string loc) {
        location = std::move(loc);
        return *this;
    }

    ValidationError& with_context(std::string key, std::string value) {
        context[key] = value;
        return *this;
    }
};

// =============================================================================
// Validation Result
// =============================================================================

class ValidationResult {
public:
    bool valid = true;
    std::vector<ValidationError> errors;
    std::vector<ValidationError> warnings;

    bool is_valid() const { return valid; }

    void add_error(ValidationError error) {
        errors.push_back(std::move(error));
        valid = false;
    }

    void add_warning(ValidationError warning) {
        warnings.push_back(std::move(warning));
    }

    void merge(const ValidationResult& other) {
        if (!other.valid) valid = false;
        for (const auto& e : other.errors) errors.push_back(e);
        for (const auto& w : other.warnings) warnings.push_back(w);
    }
};

// =============================================================================
// Field Validators
// =============================================================================

class FieldValidator {
public:
    virtual ~FieldValidator() = default;
    virtual ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const = 0;
    virtual bool is_required() const = 0;
};

class StringField : public FieldValidator {
private:
    bool required_ = false;
    std::optional<size_t> min_length_;
    std::optional<size_t> max_length_;
    std::optional<std::regex> pattern_;
    bool email_ = false;
    std::optional<std::vector<std::string>> enum_values_;

public:
    StringField() = default;

    StringField& required() { required_ = true; return *this; }
    StringField& min_len(size_t len) { min_length_ = len; return *this; }
    StringField& max_len(size_t len) { max_length_ = len; return *this; }

    StringField& pattern(const std::string& regex) {
        pattern_ = std::regex(regex);
        return *this;
    }

    StringField& email() { email_ = true; return *this; }

    StringField& enum_values(std::initializer_list<std::string> values) {
        enum_values_ = std::vector<std::string>(values);
        return *this;
    }

    bool is_required() const override { return required_; }

    ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const override {
        ValidationResult result;

        if (!value.has_value() || value->empty()) {
            if (required_) {
                result.add_error(ValidationError(ErrorCode::REQUIRED_FIELD,
                    "Field '" + field_name + "' is required"));
            }
            return result;
        }

        const std::string& val = *value;

        if (min_length_ && val.length() < *min_length_) {
            result.add_error(ValidationError(ErrorCode::MIN_LENGTH,
                "Field '" + field_name + "' must be at least " + std::to_string(*min_length_) + " characters")
                .with_context("min_length", std::to_string(*min_length_))
                .with_context("actual", std::to_string(val.length())));
        }

        if (max_length_ && val.length() > *max_length_) {
            result.add_error(ValidationError(ErrorCode::MAX_LENGTH,
                "Field '" + field_name + "' must be at most " + std::to_string(*max_length_) + " characters")
                .with_context("max_length", std::to_string(*max_length_))
                .with_context("actual", std::to_string(val.length())));
        }

        if (pattern_ && !std::regex_match(val, *pattern_)) {
            result.add_error(ValidationError(ErrorCode::PATTERN_MISMATCH,
                "Field '" + field_name + "' does not match pattern"));
        }

        if (email_) {
            std::regex email_pattern(R"(^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$)");
            if (!std::regex_match(val, email_pattern)) {
                result.add_error(ValidationError(ErrorCode::INVALID_EMAIL,
                    "Field '" + field_name + "' is not a valid email"));
            }
        }

        if (enum_values_) {
            bool found = false;
            for (const auto& ev : *enum_values_) {
                if (ev == val) { found = true; break; }
            }
            if (!found) {
                std::string allowed;
                for (size_t i = 0; i < enum_values_->size(); ++i) {
                    if (i > 0) allowed += ", ";
                    allowed += (*enum_values_)[i];
                }
                result.add_error(ValidationError(ErrorCode::INVALID_ENUM,
                    "Field '" + field_name + "' must be one of: " + allowed)
                    .with_context("allowed", allowed)
                    .with_context("actual", val));
            }
        }

        return result;
    }
};

class IntField : public FieldValidator {
private:
    bool required_ = false;
    std::optional<int64_t> min_;
    std::optional<int64_t> max_;

public:
    IntField() = default;

    IntField& required() { required_ = true; return *this; }
    IntField& min(int64_t val) { min_ = val; return *this; }
    IntField& max(int64_t val) { max_ = val; return *this; }
    IntField& range(int64_t min_val, int64_t max_val) { min_ = min_val; max_ = max_val; return *this; }

    bool is_required() const override { return required_; }

    ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const override {
        ValidationResult result;

        if (!value.has_value() || value->empty()) {
            if (required_) {
                result.add_error(ValidationError(ErrorCode::REQUIRED_FIELD,
                    "Field '" + field_name + "' is required"));
            }
            return result;
        }

        int64_t parsed;
        try {
            parsed = std::stoll(*value);
        } catch (...) {
            result.add_error(ValidationError(ErrorCode::INVALID_TYPE,
                "Field '" + field_name + "' must be an integer"));
            return result;
        }

        if (min_ && parsed < *min_) {
            result.add_error(ValidationError(ErrorCode::MIN_VALUE,
                "Field '" + field_name + "' must be at least " + std::to_string(*min_))
                .with_context("min", std::to_string(*min_))
                .with_context("actual", std::to_string(parsed)));
        }

        if (max_ && parsed > *max_) {
            result.add_error(ValidationError(ErrorCode::MAX_VALUE,
                "Field '" + field_name + "' must be at most " + std::to_string(*max_))
                .with_context("max", std::to_string(*max_))
                .with_context("actual", std::to_string(parsed)));
        }

        return result;
    }
};

class FloatField : public FieldValidator {
private:
    bool required_ = false;
    std::optional<double> min_;
    std::optional<double> max_;

public:
    FloatField() = default;

    FloatField& required() { required_ = true; return *this; }
    FloatField& min(double val) { min_ = val; return *this; }
    FloatField& max(double val) { max_ = val; return *this; }
    FloatField& range(double min_val, double max_val) { min_ = min_val; max_ = max_val; return *this; }

    bool is_required() const override { return required_; }

    ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const override {
        ValidationResult result;

        if (!value.has_value() || value->empty()) {
            if (required_) {
                result.add_error(ValidationError(ErrorCode::REQUIRED_FIELD,
                    "Field '" + field_name + "' is required"));
            }
            return result;
        }

        double parsed;
        try {
            parsed = std::stod(*value);
        } catch (...) {
            result.add_error(ValidationError(ErrorCode::INVALID_TYPE,
                "Field '" + field_name + "' must be a number"));
            return result;
        }

        if (min_ && parsed < *min_) {
            result.add_error(ValidationError(ErrorCode::MIN_VALUE,
                "Field '" + field_name + "' must be at least " + std::to_string(*min_)));
        }

        if (max_ && parsed > *max_) {
            result.add_error(ValidationError(ErrorCode::MAX_VALUE,
                "Field '" + field_name + "' must be at most " + std::to_string(*max_)));
        }

        return result;
    }
};

class BoolField : public FieldValidator {
private:
    bool required_ = false;

public:
    BoolField() = default;

    BoolField& required() { required_ = true; return *this; }

    bool is_required() const override { return required_; }

    ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const override {
        ValidationResult result;

        if (!value.has_value() || value->empty()) {
            if (required_) {
                result.add_error(ValidationError(ErrorCode::REQUIRED_FIELD,
                    "Field '" + field_name + "' is required"));
            }
            return result;
        }

        std::string lower = *value;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        if (lower != "true" && lower != "false" && lower != "1" && lower != "0"
            && lower != "yes" && lower != "no") {
            result.add_error(ValidationError(ErrorCode::INVALID_TYPE,
                "Field '" + field_name + "' must be a boolean"));
        }

        return result;
    }
};

class RefField : public FieldValidator {
private:
    bool required_ = false;
    std::optional<std::string> node_type_;

public:
    RefField() = default;

    RefField& required() { required_ = true; return *this; }
    RefField& to_node(const std::string& type) { node_type_ = type; return *this; }

    bool is_required() const override { return required_; }

    ValidationResult validate(const std::optional<std::string>& value, const std::string& field_name) const override {
        ValidationResult result;

        if (!value.has_value() || value->empty()) {
            if (required_) {
                result.add_error(ValidationError(ErrorCode::REQUIRED_FIELD,
                    "Field '" + field_name + "' is required"));
            }
            return result;
        }

        const std::string& val = *value;

        // Reference format: :type:id
        if (val.empty() || val[0] != ':') {
            result.add_error(ValidationError(ErrorCode::INVALID_TYPE,
                "Field '" + field_name + "' must be a reference (format :type:id)"));
            return result;
        }

        size_t second_colon = val.find(':', 1);
        if (second_colon == std::string::npos) {
            result.add_error(ValidationError(ErrorCode::INVALID_TYPE,
                "Field '" + field_name + "' must be a reference (format :type:id)"));
            return result;
        }

        std::string type = val.substr(1, second_colon - 1);

        if (node_type_ && type != *node_type_) {
            result.add_error(ValidationError(ErrorCode::REF_WRONG_TYPE,
                "Field '" + field_name + "' must reference '" + *node_type_ + "', got '" + type + "'")
                .with_context("expected", *node_type_)
                .with_context("actual", type));
        }

        return result;
    }
};

// =============================================================================
// Node Type Schema
// =============================================================================

class NodeType {
public:
    std::string name;

private:
    std::shared_ptr<FieldValidator> id_validator_;
    std::map<std::string, std::shared_ptr<FieldValidator>> fields_;
    std::vector<std::function<std::optional<ValidationError>(const ison_graph::Node&)>> constraints_;

public:
    explicit NodeType(std::string n) : name(std::move(n)) {}

    template<typename F>
    NodeType& id(F validator) {
        id_validator_ = std::make_shared<F>(std::move(validator));
        return *this;
    }

    template<typename F>
    NodeType& field(const std::string& field_name, F validator) {
        fields_[field_name] = std::make_shared<F>(std::move(validator));
        return *this;
    }

    NodeType& constraint(std::function<std::optional<ValidationError>(const ison_graph::Node&)> fn) {
        constraints_.push_back(std::move(fn));
        return *this;
    }

    ValidationResult validate_node(const ison_graph::Node& node) const {
        ValidationResult result;
        std::string location = "nodes." + name + "[" + node.id + "]";

        // Validate ID
        if (id_validator_) {
            auto id_result = id_validator_->validate(node.id, "id");
            for (auto& error : id_result.errors) {
                error.location = location;
            }
            result.merge(id_result);
        }

        // Validate fields
        for (const auto& [field_name, validator] : fields_) {
            std::optional<std::string> value;
            auto it = node.properties.find(field_name);
            if (it != node.properties.end()) {
                value = it->second;
            }

            auto field_result = validator->validate(value, field_name);
            for (auto& error : field_result.errors) {
                error.location = location + "." + field_name;
            }
            result.merge(field_result);
        }

        // Custom constraints
        for (const auto& constraint : constraints_) {
            auto error = constraint(node);
            if (error) {
                error->location = location;
                result.add_error(std::move(*error));
            }
        }

        return result;
    }
};

// =============================================================================
// Edge Type Schema
// =============================================================================

class EdgeType {
public:
    std::string name;

private:
    std::optional<std::string> source_type_;
    std::optional<std::string> target_type_;
    std::map<std::string, std::shared_ptr<FieldValidator>> fields_;
    bool no_self_loop_ = false;
    bool unique_ = false;
    bool acyclic_ = false;
    bool bidirectional_ = false;
    std::optional<Cardinality> cardinality_;
    std::vector<std::function<std::optional<ValidationError>(const ison_graph::Edge&)>> constraints_;

public:
    explicit EdgeType(std::string n) : name(std::move(n)) {}

    EdgeType& from_node(const NodeType& node_type) { source_type_ = node_type.name; return *this; }
    EdgeType& from_node(const std::string& type) { source_type_ = type; return *this; }
    EdgeType& to_node(const NodeType& node_type) { target_type_ = node_type.name; return *this; }
    EdgeType& to_node(const std::string& type) { target_type_ = type; return *this; }

    template<typename F>
    EdgeType& field(const std::string& field_name, F validator) {
        fields_[field_name] = std::make_shared<F>(std::move(validator));
        return *this;
    }

    EdgeType& no_self_loop() { no_self_loop_ = true; return *this; }
    EdgeType& unique() { unique_ = true; return *this; }
    EdgeType& acyclic() { acyclic_ = true; return *this; }
    EdgeType& bidirectional() { bidirectional_ = true; return *this; }
    EdgeType& cardinality(Cardinality card) { cardinality_ = card; return *this; }

    EdgeType& constraint(std::function<std::optional<ValidationError>(const ison_graph::Edge&)> fn) {
        constraints_.push_back(std::move(fn));
        return *this;
    }

    bool is_unique() const { return unique_; }
    bool is_acyclic() const { return acyclic_; }
    bool is_bidirectional() const { return bidirectional_; }
    std::optional<Cardinality> get_cardinality() const { return cardinality_; }

    ValidationResult validate_edge(const ison_graph::Edge& edge, const ison_graph::ISONGraph& graph) const {
        ValidationResult result;
        std::string location = "edges." + name + "[:" + edge.source.type + ":" + edge.source.id
                             + " -> :" + edge.target.type + ":" + edge.target.id + "]";

        // Validate source type
        if (source_type_ && edge.source.type != *source_type_) {
            result.add_error(ValidationError(ErrorCode::INVALID_SOURCE_TYPE,
                "Edge source must be '" + *source_type_ + "', got '" + edge.source.type + "'")
                .with_location(location));
        }

        // Validate target type
        if (target_type_ && edge.target.type != *target_type_) {
            result.add_error(ValidationError(ErrorCode::INVALID_TARGET_TYPE,
                "Edge target must be '" + *target_type_ + "', got '" + edge.target.type + "'")
                .with_location(location));
        }

        // Validate source exists
        if (!graph.hasNode(edge.source.type, edge.source.id)) {
            result.add_error(ValidationError(ErrorCode::REF_NOT_FOUND,
                "Source node :" + edge.source.type + ":" + edge.source.id + " does not exist")
                .with_location(location));
        }

        // Validate target exists
        if (!graph.hasNode(edge.target.type, edge.target.id)) {
            result.add_error(ValidationError(ErrorCode::REF_NOT_FOUND,
                "Target node :" + edge.target.type + ":" + edge.target.id + " does not exist")
                .with_location(location));
        }

        // Validate self-loop
        if (no_self_loop_ && edge.source.type == edge.target.type && edge.source.id == edge.target.id) {
            result.add_error(ValidationError(ErrorCode::SELF_LOOP,
                "Self-loop not allowed: :" + edge.source.type + ":" + edge.source.id)
                .with_location(location));
        }

        // Validate fields
        for (const auto& [field_name, validator] : fields_) {
            std::optional<std::string> value;
            auto it = edge.properties.find(field_name);
            if (it != edge.properties.end()) {
                value = it->second;
            }

            auto field_result = validator->validate(value, field_name);
            for (auto& error : field_result.errors) {
                error.location = location + "." + field_name;
            }
            result.merge(field_result);
        }

        // Custom constraints
        for (const auto& constraint : constraints_) {
            auto error = constraint(edge);
            if (error) {
                error->location = location;
                result.add_error(std::move(*error));
            }
        }

        return result;
    }
};

// =============================================================================
// Graph Schema
// =============================================================================

class GraphSchema {
public:
    std::string name;

private:
    std::map<std::string, NodeType> node_types_;
    std::map<std::string, EdgeType> edge_types_;
    bool require_connected_ = false;
    bool require_no_orphans_ = false;
    std::optional<size_t> max_depth_;
    std::vector<std::function<std::vector<ValidationError>(const ison_graph::ISONGraph&)>> constraints_;

public:
    explicit GraphSchema(std::string n) : name(std::move(n)) {}

    GraphSchema& node_type(NodeType type) {
        node_types_.emplace(type.name, std::move(type));
        return *this;
    }

    GraphSchema& edge_type(EdgeType type) {
        edge_types_.emplace(type.name, std::move(type));
        return *this;
    }

    GraphSchema& connected() { require_connected_ = true; return *this; }
    GraphSchema& no_orphans() { require_no_orphans_ = true; return *this; }
    GraphSchema& max_depth(size_t depth) { max_depth_ = depth; return *this; }

    GraphSchema& constraint(std::function<std::vector<ValidationError>(const ison_graph::ISONGraph&)> fn) {
        constraints_.push_back(std::move(fn));
        return *this;
    }

    ValidationResult validate(const ison_graph::ISONGraph& graph) const {
        ValidationResult result;

        // Validate nodes
        for (const auto& [type, nodes] : graph.getNodes()) {
            auto it = node_types_.find(type);
            if (it != node_types_.end()) {
                for (const auto& [id, node] : nodes) {
                    auto node_result = it->second.validate_node(node);
                    result.merge(node_result);
                }
            }
        }

        // Validate edges
        for (const auto& [rel_type, edge_type] : edge_types_) {
            auto edges = graph.getEdges(rel_type);

            // Check uniqueness
            if (edge_type.is_unique()) {
                std::set<std::string> seen;
                for (const auto& edge : edges) {
                    std::string key = edge.source.type + ":" + edge.source.id
                                    + " -> " + edge.target.type + ":" + edge.target.id;
                    if (seen.count(key)) {
                        result.add_error(ValidationError(ErrorCode::DUPLICATE_EDGE,
                            "Duplicate edge: " + key)
                            .with_location("edges." + rel_type));
                    }
                    seen.insert(key);
                }
            }

            // Check cardinality
            if (edge_type.get_cardinality()) {
                check_cardinality(edges, *edge_type.get_cardinality(), rel_type, result);
            }

            // Check acyclic (only edges of THIS relationship type may not form a cycle)
            if (edge_type.is_acyclic()) {
                if (graph.hasCycle(rel_type)) {
                    result.add_error(ValidationError(ErrorCode::CYCLE_DETECTED,
                        "Cycle detected in '" + rel_type + "' edges (must be DAG)")
                        .with_location("edges." + rel_type));
                }
            }

            // Check bidirectional: build the key set once (O(E)) instead of
            // re-fetching and scanning all edges for every edge (O(E^2) with copies)
            if (edge_type.is_bidirectional()) {
                std::set<std::string> edge_keys;
                for (const auto& e : edges) {
                    edge_keys.insert(e.source.type + ":" + e.source.id
                                   + ">" + e.target.type + ":" + e.target.id);
                }
                for (const auto& edge : edges) {
                    std::string reverse_key = edge.target.type + ":" + edge.target.id
                                            + ">" + edge.source.type + ":" + edge.source.id;
                    if (edge_keys.find(reverse_key) == edge_keys.end()) {
                        result.add_error(ValidationError(ErrorCode::DUPLICATE_EDGE,
                            "Missing reverse edge for bidirectional: :" + edge.target.type + ":" + edge.target.id +
                            " -> :" + edge.source.type + ":" + edge.source.id)
                            .with_location("edges." + rel_type));
                    }
                }
            }

            // Validate individual edges
            for (const auto& edge : edges) {
                auto edge_result = edge_type.validate_edge(edge, graph);
                result.merge(edge_result);
            }
        }

        // Graph-level constraints
        if (require_connected_ && !graph.isConnected()) {
            result.add_error(ValidationError(ErrorCode::NOT_CONNECTED,
                "Graph is not connected (some nodes are unreachable)")
                .with_location("graph"));
        }

        if (require_no_orphans_) {
            for (const auto& [type, nodes] : graph.getNodes()) {
                for (const auto& [id, node] : nodes) {
                    ison_graph::NodeRef ref{type, id};
                    if (graph.degree(ref) == 0) {
                        result.add_error(ValidationError(ErrorCode::ORPHAN_NODE,
                            "Orphan node: :" + type + ":" + id)
                            .with_location("nodes." + type + "[" + id + "]"));
                    }
                }
            }
        }

        // Custom constraints
        for (const auto& constraint : constraints_) {
            auto errors = constraint(graph);
            for (auto& error : errors) {
                result.add_error(std::move(error));
            }
        }

        return result;
    }

private:
    void check_cardinality(const std::vector<ison_graph::Edge>& edges,
                          Cardinality cardinality,
                          const std::string& rel_type,
                          ValidationResult& result) const {
        std::string location = "edges." + rel_type;
        std::map<std::string, size_t> source_counts;
        std::map<std::string, size_t> target_counts;

        for (const auto& edge : edges) {
            std::string source_key = edge.source.type + ":" + edge.source.id;
            std::string target_key = edge.target.type + ":" + edge.target.id;
            source_counts[source_key]++;
            target_counts[target_key]++;
        }

        switch (cardinality) {
            case Cardinality::ONE_TO_ONE:
                for (const auto& [source, count] : source_counts) {
                    if (count > 1) {
                        result.add_error(ValidationError(ErrorCode::CARDINALITY_VIOLATION,
                            "ONE_TO_ONE violation: " + source + " has " + std::to_string(count) + " outgoing edges")
                            .with_location(location));
                    }
                }
                for (const auto& [target, count] : target_counts) {
                    if (count > 1) {
                        result.add_error(ValidationError(ErrorCode::CARDINALITY_VIOLATION,
                            "ONE_TO_ONE violation: " + target + " has " + std::to_string(count) + " incoming edges")
                            .with_location(location));
                    }
                }
                break;

            case Cardinality::ONE_TO_MANY:
                for (const auto& [target, count] : target_counts) {
                    if (count > 1) {
                        result.add_error(ValidationError(ErrorCode::CARDINALITY_VIOLATION,
                            "ONE_TO_MANY violation: " + target + " has " + std::to_string(count) + " incoming edges")
                            .with_location(location));
                    }
                }
                break;

            case Cardinality::MANY_TO_ONE:
                for (const auto& [source, count] : source_counts) {
                    if (count > 1) {
                        result.add_error(ValidationError(ErrorCode::CARDINALITY_VIOLATION,
                            "MANY_TO_ONE violation: " + source + " has " + std::to_string(count) + " outgoing edges")
                            .with_location(location));
                    }
                }
                break;

            case Cardinality::MANY_TO_MANY:
                // No constraints
                break;
        }
    }
};

} // namespace isongraphantic

#endif // ISONGRAPHANTIC_HPP
