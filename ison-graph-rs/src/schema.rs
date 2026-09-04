//! ISONGraph Schema Validation Module
//!
//! Provides graph schema validation with:
//! - Node type schemas with property validation
//! - Edge type schemas with reference integrity
//! - Graph-level constraints (cycles, connectivity, cardinality)
//! - Builder pattern for schema definition
//!
//! # Example
//!
//! ```rust
//! use ison_graph::schema::{
//!     GraphSchema, NodeType, EdgeType,
//!     StringField, IntField, Cardinality,
//! };
//! use ison_graph::ISONGraph;
//!
//! // Define node types
//! let person = NodeType::new("person")
//!     .id(IntField::new())
//!     .field("name", StringField::new().required().max(100))
//!     .field("age", IntField::new().min(0).max(150));
//!
//! let company = NodeType::new("company")
//!     .id(IntField::new())
//!     .field("name", StringField::new().required());
//!
//! // Define edge types
//! let knows = EdgeType::new("KNOWS")
//!     .from_node("person")
//!     .to_node("person")
//!     .no_self_loop()
//!     .unique();
//!
//! let works_at = EdgeType::new("WORKS_AT")
//!     .from_node("person")
//!     .to_node("company")
//!     .cardinality(Cardinality::ManyToOne);
//!
//! // Define graph schema
//! let schema = GraphSchema::new("social")
//!     .node_type(person)
//!     .node_type(company)
//!     .edge_type(knows)
//!     .edge_type(works_at)
//!     .no_orphans();
//!
//! // Validate
//! let mut graph = ISONGraph::new("test");
//! // ... add nodes and edges ...
//! let result = schema.validate(&graph);
//! if !result.is_valid() {
//!     for error in result.errors() {
//!         println!("{}", error);
//!     }
//! }
//! ```

use crate::{Edge, ISONGraph, Node};
use regex::Regex;
use std::collections::{HashMap, HashSet};
use std::fmt;
use std::sync::OnceLock;

// =============================================================================
// Enums
// =============================================================================

/// Edge cardinality constraints
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Cardinality {
    OneToOne,
    OneToMany,
    ManyToOne,
    ManyToMany,
}

impl fmt::Display for Cardinality {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cardinality::OneToOne => write!(f, "1:1"),
            Cardinality::OneToMany => write!(f, "1:N"),
            Cardinality::ManyToOne => write!(f, "N:1"),
            Cardinality::ManyToMany => write!(f, "N:N"),
        }
    }
}

/// Validation error codes
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCode {
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

impl fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ErrorCode::RequiredField => write!(f, "REQUIRED_FIELD"),
            ErrorCode::InvalidType => write!(f, "INVALID_TYPE"),
            ErrorCode::MinValue => write!(f, "MIN_VALUE"),
            ErrorCode::MaxValue => write!(f, "MAX_VALUE"),
            ErrorCode::MinLength => write!(f, "MIN_LENGTH"),
            ErrorCode::MaxLength => write!(f, "MAX_LENGTH"),
            ErrorCode::PatternMismatch => write!(f, "PATTERN_MISMATCH"),
            ErrorCode::InvalidEmail => write!(f, "INVALID_EMAIL"),
            ErrorCode::InvalidEnum => write!(f, "INVALID_ENUM"),
            ErrorCode::RefNotFound => write!(f, "REF_NOT_FOUND"),
            ErrorCode::RefWrongType => write!(f, "REF_WRONG_TYPE"),
            ErrorCode::SelfLoop => write!(f, "SELF_LOOP"),
            ErrorCode::DuplicateEdge => write!(f, "DUPLICATE_EDGE"),
            ErrorCode::CardinalityViolation => write!(f, "CARDINALITY_VIOLATION"),
            ErrorCode::InvalidSourceType => write!(f, "INVALID_SOURCE_TYPE"),
            ErrorCode::InvalidTargetType => write!(f, "INVALID_TARGET_TYPE"),
            ErrorCode::CycleDetected => write!(f, "CYCLE_DETECTED"),
            ErrorCode::NotConnected => write!(f, "NOT_CONNECTED"),
            ErrorCode::OrphanNode => write!(f, "ORPHAN_NODE"),
            ErrorCode::MaxDepthExceeded => write!(f, "MAX_DEPTH_EXCEEDED"),
        }
    }
}

// =============================================================================
// Validation Result
// =============================================================================

/// Represents a single validation error
#[derive(Debug, Clone)]
pub struct ValidationError {
    pub code: ErrorCode,
    pub message: String,
    pub location: String,
}

impl ValidationError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            location: String::new(),
        }
    }

    pub fn with_location(mut self, location: impl Into<String>) -> Self {
        self.location = location.into();
        self
    }
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.location.is_empty() {
            write!(f, "{}: {}", self.code, self.message)
        } else {
            write!(f, "[{}] {}: {}", self.location, self.code, self.message)
        }
    }
}

/// Result of schema validation
#[derive(Debug, Clone)]
pub struct ValidationResult {
    valid: bool,
    errors: Vec<ValidationError>,
    warnings: Vec<ValidationError>,
}

impl ValidationResult {
    pub fn new() -> Self {
        Self {
            valid: true,
            errors: Vec::new(),
            warnings: Vec::new(),
        }
    }

    pub fn is_valid(&self) -> bool {
        self.valid
    }

    pub fn errors(&self) -> &[ValidationError] {
        &self.errors
    }

    pub fn warnings(&self) -> &[ValidationError] {
        &self.warnings
    }

    pub fn add_error(&mut self, error: ValidationError) {
        self.errors.push(error);
        self.valid = false;
    }

    pub fn add_warning(&mut self, warning: ValidationError) {
        self.warnings.push(warning);
    }

    pub fn merge(&mut self, other: ValidationResult) {
        self.errors.extend(other.errors);
        self.warnings.extend(other.warnings);
        if !other.valid {
            self.valid = false;
        }
    }
}

impl Default for ValidationResult {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// Field Types
// =============================================================================

/// Trait for field validators
pub trait FieldValidator: Send + Sync {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult;
    fn is_required(&self) -> bool;
}

/// String field validator
#[derive(Debug, Clone)]
pub struct StringField {
    required: bool,
    min_length: Option<usize>,
    max_length: Option<usize>,
    pattern: Option<Regex>,
    email: bool,
    allowed_values: Option<Vec<String>>,
}

impl StringField {
    pub fn new() -> Self {
        Self {
            required: false,
            min_length: None,
            max_length: None,
            pattern: None,
            email: false,
            allowed_values: None,
        }
    }

    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }

    pub fn min(mut self, length: usize) -> Self {
        self.min_length = Some(length);
        self
    }

    pub fn max(mut self, length: usize) -> Self {
        self.max_length = Some(length);
        self
    }

    pub fn pattern(mut self, regex: &str) -> Self {
        self.pattern = Regex::new(regex).ok();
        self
    }

    pub fn email(mut self) -> Self {
        self.email = true;
        self
    }

    pub fn allowed(mut self, values: Vec<&str>) -> Self {
        self.allowed_values = Some(values.into_iter().map(String::from).collect());
        self
    }
}

impl Default for StringField {
    fn default() -> Self {
        Self::new()
    }
}

impl FieldValidator for StringField {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult {
        let mut result = ValidationResult::new();

        match value {
            None | Some("") | Some("null") => {
                if self.required {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::RequiredField,
                            format!("Field '{}' is required", field_name),
                        )
                        .with_location(field_name),
                    );
                }
                return result;
            }
            Some(val) => {
                if let Some(min) = self.min_length {
                    if val.len() < min {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::MinLength,
                                format!(
                                    "Field '{}' must be at least {} characters",
                                    field_name, min
                                ),
                            )
                            .with_location(field_name),
                        );
                    }
                }

                if let Some(max) = self.max_length {
                    if val.len() > max {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::MaxLength,
                                format!(
                                    "Field '{}' must be at most {} characters",
                                    field_name, max
                                ),
                            )
                            .with_location(field_name),
                        );
                    }
                }

                if let Some(ref pattern) = self.pattern {
                    if !pattern.is_match(val) {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::PatternMismatch,
                                format!("Field '{}' does not match pattern", field_name),
                            )
                            .with_location(field_name),
                        );
                    }
                }

                if self.email {
                    static EMAIL_REGEX: OnceLock<Regex> = OnceLock::new();
                    let email_re = EMAIL_REGEX.get_or_init(|| {
                        Regex::new(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$").unwrap()
                    });
                    if !email_re.is_match(val) {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::InvalidEmail,
                                format!("Field '{}' is not a valid email address", field_name),
                            )
                            .with_location(field_name),
                        );
                    }
                }

                if let Some(ref allowed) = self.allowed_values {
                    if !allowed.contains(&val.to_string()) {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::InvalidEnum,
                                format!(
                                    "Field '{}' must be one of: {}",
                                    field_name,
                                    allowed.join(", ")
                                ),
                            )
                            .with_location(field_name),
                        );
                    }
                }
            }
        }

        result
    }

    fn is_required(&self) -> bool {
        self.required
    }
}

/// Integer field validator
#[derive(Debug, Clone)]
pub struct IntField {
    required: bool,
    min: Option<i64>,
    max: Option<i64>,
}

impl IntField {
    pub fn new() -> Self {
        Self {
            required: false,
            min: None,
            max: None,
        }
    }

    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }

    pub fn min(mut self, value: i64) -> Self {
        self.min = Some(value);
        self
    }

    pub fn max(mut self, value: i64) -> Self {
        self.max = Some(value);
        self
    }

    pub fn range(mut self, min: i64, max: i64) -> Self {
        self.min = Some(min);
        self.max = Some(max);
        self
    }
}

impl Default for IntField {
    fn default() -> Self {
        Self::new()
    }
}

impl FieldValidator for IntField {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult {
        let mut result = ValidationResult::new();

        match value {
            None | Some("") | Some("null") => {
                if self.required {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::RequiredField,
                            format!("Field '{}' is required", field_name),
                        )
                        .with_location(field_name),
                    );
                }
                return result;
            }
            Some(val) => {
                let parsed: Result<i64, _> = val.parse();
                match parsed {
                    Ok(num) => {
                        if let Some(min) = self.min {
                            if num < min {
                                result.add_error(
                                    ValidationError::new(
                                        ErrorCode::MinValue,
                                        format!("Field '{}' must be at least {}", field_name, min),
                                    )
                                    .with_location(field_name),
                                );
                            }
                        }

                        if let Some(max) = self.max {
                            if num > max {
                                result.add_error(
                                    ValidationError::new(
                                        ErrorCode::MaxValue,
                                        format!("Field '{}' must be at most {}", field_name, max),
                                    )
                                    .with_location(field_name),
                                );
                            }
                        }
                    }
                    Err(_) => {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::InvalidType,
                                format!("Field '{}' must be an integer", field_name),
                            )
                            .with_location(field_name),
                        );
                    }
                }
            }
        }

        result
    }

    fn is_required(&self) -> bool {
        self.required
    }
}

/// Float field validator
#[derive(Debug, Clone)]
pub struct FloatField {
    required: bool,
    min: Option<f64>,
    max: Option<f64>,
}

impl FloatField {
    pub fn new() -> Self {
        Self {
            required: false,
            min: None,
            max: None,
        }
    }

    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }

    pub fn min(mut self, value: f64) -> Self {
        self.min = Some(value);
        self
    }

    pub fn max(mut self, value: f64) -> Self {
        self.max = Some(value);
        self
    }

    pub fn range(mut self, min: f64, max: f64) -> Self {
        self.min = Some(min);
        self.max = Some(max);
        self
    }
}

impl Default for FloatField {
    fn default() -> Self {
        Self::new()
    }
}

impl FieldValidator for FloatField {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult {
        let mut result = ValidationResult::new();

        match value {
            None | Some("") | Some("null") => {
                if self.required {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::RequiredField,
                            format!("Field '{}' is required", field_name),
                        )
                        .with_location(field_name),
                    );
                }
                return result;
            }
            Some(val) => {
                let parsed: Result<f64, _> = val.parse();
                match parsed {
                    Ok(num) => {
                        if let Some(min) = self.min {
                            if num < min {
                                result.add_error(
                                    ValidationError::new(
                                        ErrorCode::MinValue,
                                        format!("Field '{}' must be at least {}", field_name, min),
                                    )
                                    .with_location(field_name),
                                );
                            }
                        }

                        if let Some(max) = self.max {
                            if num > max {
                                result.add_error(
                                    ValidationError::new(
                                        ErrorCode::MaxValue,
                                        format!("Field '{}' must be at most {}", field_name, max),
                                    )
                                    .with_location(field_name),
                                );
                            }
                        }
                    }
                    Err(_) => {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::InvalidType,
                                format!("Field '{}' must be a number", field_name),
                            )
                            .with_location(field_name),
                        );
                    }
                }
            }
        }

        result
    }

    fn is_required(&self) -> bool {
        self.required
    }
}

/// Boolean field validator
#[derive(Debug, Clone)]
pub struct BoolField {
    required: bool,
}

impl BoolField {
    pub fn new() -> Self {
        Self { required: false }
    }

    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }
}

impl Default for BoolField {
    fn default() -> Self {
        Self::new()
    }
}

impl FieldValidator for BoolField {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult {
        let mut result = ValidationResult::new();

        match value {
            None | Some("") | Some("null") => {
                if self.required {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::RequiredField,
                            format!("Field '{}' is required", field_name),
                        )
                        .with_location(field_name),
                    );
                }
                return result;
            }
            Some(val) => {
                let lower = val.to_lowercase();
                if lower != "true" && lower != "false" && lower != "1" && lower != "0" {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::InvalidType,
                            format!("Field '{}' must be a boolean", field_name),
                        )
                        .with_location(field_name),
                    );
                }
            }
        }

        result
    }

    fn is_required(&self) -> bool {
        self.required
    }
}

/// Reference field validator
#[derive(Debug, Clone)]
pub struct RefField {
    required: bool,
    node_type: Option<String>,
}

impl RefField {
    pub fn new() -> Self {
        Self {
            required: false,
            node_type: None,
        }
    }

    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }

    pub fn to_node(mut self, node_type: impl Into<String>) -> Self {
        self.node_type = Some(node_type.into());
        self
    }
}

impl Default for RefField {
    fn default() -> Self {
        Self::new()
    }
}

impl FieldValidator for RefField {
    fn validate(&self, value: Option<&str>, field_name: &str) -> ValidationResult {
        let mut result = ValidationResult::new();

        match value {
            None | Some("") | Some("null") => {
                if self.required {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::RequiredField,
                            format!("Field '{}' is required", field_name),
                        )
                        .with_location(field_name),
                    );
                }
                return result;
            }
            Some(val) => {
                // Reference format: :type:id
                if val.is_empty() || !val.starts_with(':') {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::InvalidType,
                            format!("Field '{}' must be a reference (format :type:id)", field_name),
                        )
                        .with_location(field_name),
                    );
                    return result;
                }

                // Find second colon
                let rest = &val[1..];
                match rest.find(':') {
                    None => {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::InvalidType,
                                format!("Field '{}' must be a reference (format :type:id)", field_name),
                            )
                            .with_location(field_name),
                        );
                    }
                    Some(pos) => {
                        let ref_type = &rest[..pos];

                        if let Some(ref expected_type) = self.node_type {
                            if ref_type != expected_type {
                                result.add_error(
                                    ValidationError::new(
                                        ErrorCode::RefWrongType,
                                        format!(
                                            "Field '{}' must reference '{}', got '{}'",
                                            field_name, expected_type, ref_type
                                        ),
                                    )
                                    .with_location(field_name),
                                );
                            }
                        }
                    }
                }
            }
        }

        result
    }

    fn is_required(&self) -> bool {
        self.required
    }
}

// =============================================================================
// Node Type Schema
// =============================================================================

/// Schema definition for a node type
pub struct NodeType {
    pub name: String,
    id_validator: Option<Box<dyn FieldValidator>>,
    fields: HashMap<String, Box<dyn FieldValidator>>,
}

impl NodeType {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            id_validator: None,
            fields: HashMap::new(),
        }
    }

    pub fn id<V: FieldValidator + 'static>(mut self, validator: V) -> Self {
        self.id_validator = Some(Box::new(validator));
        self
    }

    pub fn field<V: FieldValidator + 'static>(mut self, name: impl Into<String>, validator: V) -> Self {
        self.fields.insert(name.into(), Box::new(validator));
        self
    }

    pub fn validate_node(&self, node: &Node) -> ValidationResult {
        let mut result = ValidationResult::new();
        let location = format!("nodes.{}[{}]", self.name, node.id);

        // Validate ID
        if let Some(ref id_validator) = self.id_validator {
            let id_result = id_validator.validate(Some(&node.id), "id");
            if !id_result.is_valid() {
                for mut err in id_result.errors {
                    err.location = location.clone();
                    result.add_error(err);
                }
            }
        }

        // Validate fields
        for (field_name, validator) in &self.fields {
            // Rendered to text so validation behaves exactly as it did when
            // properties were strings. Type-aware validation is a separate
            // change; typing the storage should not silently alter what a
            // schema accepts.
            let rendered = node.properties.get(field_name).map(crate::value_to_text);
            let value = rendered.as_deref();
            let field_result = validator.validate(value, field_name);
            if !field_result.is_valid() {
                for mut err in field_result.errors {
                    err.location = format!("{}.{}", location, field_name);
                    result.add_error(err);
                }
            }
        }

        result
    }
}

// =============================================================================
// Edge Type Schema
// =============================================================================

/// Schema definition for an edge/relationship type
pub struct EdgeType {
    pub name: String,
    source_type: Option<String>,
    target_type: Option<String>,
    fields: HashMap<String, Box<dyn FieldValidator>>,
    no_self_loop: bool,
    unique: bool,
    acyclic: bool,
    bidirectional: bool,
    cardinality: Option<Cardinality>,
}

impl EdgeType {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            source_type: None,
            target_type: None,
            fields: HashMap::new(),
            no_self_loop: false,
            unique: false,
            acyclic: false,
            bidirectional: false,
            cardinality: None,
        }
    }

    pub fn from_node(mut self, node_type: impl Into<String>) -> Self {
        self.source_type = Some(node_type.into());
        self
    }

    pub fn to_node(mut self, node_type: impl Into<String>) -> Self {
        self.target_type = Some(node_type.into());
        self
    }

    pub fn field<V: FieldValidator + 'static>(mut self, name: impl Into<String>, validator: V) -> Self {
        self.fields.insert(name.into(), Box::new(validator));
        self
    }

    pub fn no_self_loop(mut self) -> Self {
        self.no_self_loop = true;
        self
    }

    pub fn unique(mut self) -> Self {
        self.unique = true;
        self
    }

    pub fn acyclic(mut self) -> Self {
        self.acyclic = true;
        self
    }

    pub fn bidirectional(mut self) -> Self {
        self.bidirectional = true;
        self
    }

    pub fn cardinality(mut self, card: Cardinality) -> Self {
        self.cardinality = Some(card);
        self
    }

    pub fn is_unique(&self) -> bool {
        self.unique
    }

    pub fn is_acyclic(&self) -> bool {
        self.acyclic
    }

    pub fn is_bidirectional(&self) -> bool {
        self.bidirectional
    }

    pub fn cardinality_constraint(&self) -> Option<Cardinality> {
        self.cardinality
    }

    pub fn validate_edge(&self, edge: &Edge, graph: &ISONGraph) -> ValidationResult {
        let mut result = ValidationResult::new();
        let location = format!(
            "edges.{}[{}->{}]",
            self.name,
            edge.source.to_key(),
            edge.target.to_key()
        );

        // Validate source type
        if let Some(ref src_type) = self.source_type {
            if &edge.source.node_type != src_type {
                result.add_error(
                    ValidationError::new(
                        ErrorCode::InvalidSourceType,
                        format!(
                            "Edge source must be '{}', got '{}'",
                            src_type, edge.source.node_type
                        ),
                    )
                    .with_location(&location),
                );
            }
        }

        // Validate target type
        if let Some(ref tgt_type) = self.target_type {
            if &edge.target.node_type != tgt_type {
                result.add_error(
                    ValidationError::new(
                        ErrorCode::InvalidTargetType,
                        format!(
                            "Edge target must be '{}', got '{}'",
                            tgt_type, edge.target.node_type
                        ),
                    )
                    .with_location(&location),
                );
            }
        }

        // Validate source exists
        if !graph.has_node(&edge.source.node_type, &edge.source.id) {
            result.add_error(
                ValidationError::new(
                    ErrorCode::RefNotFound,
                    format!(
                        "Source node :{}:{} does not exist",
                        edge.source.node_type, edge.source.id
                    ),
                )
                .with_location(&location),
            );
        }

        // Validate target exists
        if !graph.has_node(&edge.target.node_type, &edge.target.id) {
            result.add_error(
                ValidationError::new(
                    ErrorCode::RefNotFound,
                    format!(
                        "Target node :{}:{} does not exist",
                        edge.target.node_type, edge.target.id
                    ),
                )
                .with_location(&location),
            );
        }

        // Validate self-loop constraint
        if self.no_self_loop && edge.source == edge.target {
            result.add_error(
                ValidationError::new(
                    ErrorCode::SelfLoop,
                    format!(
                        "Self-loop not allowed: :{}:{}",
                        edge.source.node_type, edge.source.id
                    ),
                )
                .with_location(&location),
            );
        }

        // Validate fields
        for (field_name, validator) in &self.fields {
            let rendered = edge.properties.get(field_name).map(crate::value_to_text);
            let value = rendered.as_deref();
            let field_result = validator.validate(value, field_name);
            if !field_result.is_valid() {
                for mut err in field_result.errors {
                    err.location = format!("{}.{}", location, field_name);
                    result.add_error(err);
                }
            }
        }

        result
    }
}

// =============================================================================
// Graph Schema
// =============================================================================

/// Complete graph schema definition
pub struct GraphSchema {
    pub name: String,
    node_types: HashMap<String, NodeType>,
    edge_types: HashMap<String, EdgeType>,
    require_connected: bool,
    require_no_orphans: bool,
    max_depth: Option<usize>,
}

impl GraphSchema {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            node_types: HashMap::new(),
            edge_types: HashMap::new(),
            require_connected: false,
            require_no_orphans: false,
            max_depth: None,
        }
    }

    pub fn node_type(mut self, node_type: NodeType) -> Self {
        self.node_types.insert(node_type.name.clone(), node_type);
        self
    }

    pub fn edge_type(mut self, edge_type: EdgeType) -> Self {
        self.edge_types.insert(edge_type.name.clone(), edge_type);
        self
    }

    pub fn connected(mut self) -> Self {
        self.require_connected = true;
        self
    }

    pub fn no_orphans(mut self) -> Self {
        self.require_no_orphans = true;
        self
    }

    pub fn max_depth(mut self, depth: usize) -> Self {
        self.max_depth = Some(depth);
        self
    }

    /// Validate a graph against this schema
    pub fn validate(&self, graph: &ISONGraph) -> ValidationResult {
        let mut result = ValidationResult::new();

        // Validate nodes
        for node in graph.nodes() {
            if let Some(node_type) = self.node_types.get(&node.node_type) {
                let node_result = node_type.validate_node(node);
                result.merge(node_result);
            }
        }

        // Validate edges
        for (rel_type, edge_type) in &self.edge_types {
            let edges: Vec<_> = graph.edges_of_type(rel_type).collect();

            // Check uniqueness
            if edge_type.is_unique() {
                let mut seen = HashSet::new();
                for edge in &edges {
                    let key = format!(
                        "{}:{}->{}:{}",
                        edge.source.node_type,
                        edge.source.id,
                        edge.target.node_type,
                        edge.target.id
                    );
                    if seen.contains(&key) {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::DuplicateEdge,
                                format!("Duplicate edge: {} -> {}", edge.source.to_key(), edge.target.to_key()),
                            )
                            .with_location(format!("edges.{}", rel_type)),
                        );
                    }
                    seen.insert(key);
                }
            }

            // Check cardinality
            if edge_type.cardinality_constraint().is_some() {
                self.check_cardinality(graph, edge_type, &edges, &mut result);
            }

            // Check acyclic
            if edge_type.is_acyclic() && graph.has_cycle(Some(rel_type)) {
                result.add_error(
                    ValidationError::new(
                        ErrorCode::CycleDetected,
                        format!("Cycle detected in '{}' edges (must be DAG)", rel_type),
                    )
                    .with_location(format!("edges.{}", rel_type)),
                );
            }

            // Check bidirectional
            if edge_type.is_bidirectional() {
                for edge in &edges {
                    if !graph.has_edge(
                        rel_type,
                        (&edge.target.node_type, &edge.target.id),
                        (&edge.source.node_type, &edge.source.id),
                    ) {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::DuplicateEdge,
                                format!(
                                    "Missing reverse edge for bidirectional: {} -> {}",
                                    edge.target.to_key(),
                                    edge.source.to_key()
                                ),
                            )
                            .with_location(format!("edges.{}", rel_type)),
                        );
                    }
                }
            }

            // Validate individual edges
            for edge in &edges {
                let edge_result = edge_type.validate_edge(edge, graph);
                result.merge(edge_result);
            }
        }

        // Graph-level constraints
        if self.require_connected && !graph.is_connected() {
            result.add_error(
                ValidationError::new(
                    ErrorCode::NotConnected,
                    "Graph is not connected (some nodes are unreachable)",
                )
                .with_location("graph"),
            );
        }

        if self.require_no_orphans {
            for node in graph.nodes() {
                let node_ref = (&node.node_type as &str, &node.id as &str);
                if graph.degree(&node_ref) == 0 {
                    result.add_error(
                        ValidationError::new(
                            ErrorCode::OrphanNode,
                            format!(
                                "Orphan node (no edges): :{}:{}",
                                node.node_type, node.id
                            ),
                        )
                        .with_location(format!("nodes.{}[{}]", node.node_type, node.id)),
                    );
                }
            }
        }

        result
    }

    fn check_cardinality(
        &self,
        _graph: &ISONGraph,
        edge_type: &EdgeType,
        edges: &[&Edge],
        result: &mut ValidationResult,
    ) {
        let cardinality = match edge_type.cardinality_constraint() {
            Some(c) => c,
            None => return,
        };
        let location = format!("edges.{}", edge_type.name);

        // Count outgoing edges per source
        let mut source_counts: HashMap<String, usize> = HashMap::new();
        // Count incoming edges per target
        let mut target_counts: HashMap<String, usize> = HashMap::new();

        for edge in edges {
            let source_key = edge.source.to_key();
            let target_key = edge.target.to_key();
            *source_counts.entry(source_key).or_insert(0) += 1;
            *target_counts.entry(target_key).or_insert(0) += 1;
        }

        match cardinality {
            Cardinality::OneToOne => {
                for (source, count) in &source_counts {
                    if *count > 1 {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::CardinalityViolation,
                                format!(
                                    "ONE_TO_ONE violation: :{} has {} outgoing edges",
                                    source, count
                                ),
                            )
                            .with_location(&location),
                        );
                    }
                }
                for (target, count) in &target_counts {
                    if *count > 1 {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::CardinalityViolation,
                                format!(
                                    "ONE_TO_ONE violation: :{} has {} incoming edges",
                                    target, count
                                ),
                            )
                            .with_location(&location),
                        );
                    }
                }
            }
            Cardinality::OneToMany => {
                for (target, count) in &target_counts {
                    if *count > 1 {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::CardinalityViolation,
                                format!(
                                    "ONE_TO_MANY violation: :{} has {} incoming edges",
                                    target, count
                                ),
                            )
                            .with_location(&location),
                        );
                    }
                }
            }
            Cardinality::ManyToOne => {
                for (source, count) in &source_counts {
                    if *count > 1 {
                        result.add_error(
                            ValidationError::new(
                                ErrorCode::CardinalityViolation,
                                format!(
                                    "MANY_TO_ONE violation: :{} has {} outgoing edges",
                                    source, count
                                ),
                            )
                            .with_location(&location),
                        );
                    }
                }
            }
            Cardinality::ManyToMany => {
                // No restrictions
            }
        }
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Value;

    #[test]
    fn test_string_field_required() {
        let field = StringField::new().required();
        let result = field.validate(None, "name");
        assert!(!result.is_valid());
        assert_eq!(result.errors()[0].code, ErrorCode::RequiredField);
    }

    #[test]
    fn test_string_field_length() {
        let field = StringField::new().min(3).max(10);

        let result = field.validate(Some("ab"), "name");
        assert!(!result.is_valid());

        let result = field.validate(Some("hello"), "name");
        assert!(result.is_valid());

        let result = field.validate(Some("this is too long"), "name");
        assert!(!result.is_valid());
    }

    #[test]
    fn test_int_field_range() {
        let field = IntField::new().min(0).max(150);

        let result = field.validate(Some("-1"), "age");
        assert!(!result.is_valid());

        let result = field.validate(Some("30"), "age");
        assert!(result.is_valid());

        let result = field.validate(Some("200"), "age");
        assert!(!result.is_valid());
    }

    #[test]
    fn test_node_type_validation() {
        let person = NodeType::new("person")
            .field("name", StringField::new().required())
            .field("age", IntField::new().min(0).max(150));

        let mut node = Node::new("person", "1");
        node.properties.insert("name".to_string(), Value::String("Alice".to_string()));
        node.properties.insert("age".to_string(), Value::String("30".to_string()));

        let result = person.validate_node(&node);
        assert!(result.is_valid());

        let mut invalid_node = Node::new("person", "2");
        invalid_node.properties.insert("age".to_string(), Value::String("200".to_string()));

        let result = person.validate_node(&invalid_node);
        assert!(!result.is_valid());
        assert!(result.errors().len() >= 2); // missing required name + age out of range
    }

    #[test]
    fn test_graph_schema_validation() {
        let person = NodeType::new("person")
            .field("name", StringField::new().required());

        let knows = EdgeType::new("KNOWS")
            .from_node("person")
            .to_node("person")
            .no_self_loop();

        let schema = GraphSchema::new("social")
            .node_type(person)
            .edge_type(knows);

        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![("name", "Alice")]).unwrap();
        graph.add_node("person", "2", props![("name", "Bob")]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();

        let result = schema.validate(&graph);
        assert!(result.is_valid());
    }

    #[test]
    fn test_self_loop_constraint() {
        let knows = EdgeType::new("KNOWS")
            .from_node("person")
            .to_node("person")
            .no_self_loop();

        let schema = GraphSchema::new("social")
            .edge_type(knows);

        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "1"), props![]).unwrap();

        let result = schema.validate(&graph);
        assert!(!result.is_valid());
        assert!(result.errors().iter().any(|e| e.code == ErrorCode::SelfLoop));
    }

    #[test]
    fn test_orphan_constraint() {
        let schema = GraphSchema::new("social")
            .no_orphans();

        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();

        let result = schema.validate(&graph);
        assert!(!result.is_valid());
        assert!(result.errors().iter().any(|e| e.code == ErrorCode::OrphanNode));
    }

    #[test]
    fn test_ref_field_required() {
        let field = RefField::new().required();

        // Missing value should fail
        let result = field.validate(None, "manager");
        assert!(!result.is_valid());
        assert_eq!(result.errors()[0].code, ErrorCode::RequiredField);

        // Valid reference should pass
        let result = field.validate(Some(":person:1"), "manager");
        assert!(result.is_valid());
    }

    #[test]
    fn test_ref_field_format() {
        let field = RefField::new();

        // Invalid format - missing colon prefix
        let result = field.validate(Some("person:1"), "manager");
        assert!(!result.is_valid());
        assert_eq!(result.errors()[0].code, ErrorCode::InvalidType);

        // Invalid format - missing second colon
        let result = field.validate(Some(":person"), "manager");
        assert!(!result.is_valid());

        // Valid format
        let result = field.validate(Some(":person:1"), "manager");
        assert!(result.is_valid());
    }

    #[test]
    fn test_ref_field_type_constraint() {
        let field = RefField::new().to_node("person");

        // Wrong node type
        let result = field.validate(Some(":company:1"), "manager");
        assert!(!result.is_valid());
        assert_eq!(result.errors()[0].code, ErrorCode::RefWrongType);

        // Correct node type
        let result = field.validate(Some(":person:1"), "manager");
        assert!(result.is_valid());
    }
}
