//! ISONQL - Pure Property Graph Query Language for ISONGraph (Rust)
//!
//! A declarative query language for property graph operations.
//!
//! # Supported Query Types
//! - NODES: Select and filter nodes
//! - EDGES: Select and filter edges
//! - TRAVERSE: Graph traversal with patterns
//! - PATH: Shortest path finding
//! - COUNT: Count nodes matching criteria
//! - SUM/AVG/MIN/MAX: Numeric aggregations
//!
//! # Example
//!
//! ```rust
//! use ison_graph::{ISONGraph, props, query::{QueryEngine, QueryResult}};
//!
//! let mut graph = ISONGraph::new("social");
//! graph.add_node("person", "alice", props![("name", "Alice"), ("age", 30i64)]).unwrap();
//! graph.add_node("person", "bob", props![("name", "Bob"), ("age", 25i64)]).unwrap();
//! graph.add_edge("KNOWS", ("person", "alice"), ("person", "bob"), props![("since", 2020i64)]).unwrap();
//!
//! let engine = QueryEngine::new(&graph);
//! let result = engine.execute("NODES person WHERE age > 25").unwrap();
//! ```

use std::collections::{HashMap, HashSet};
use std::time::Instant;
use crate::{ISONGraph, Node, Edge, NodeId, Direction, GraphError, Result};
use ison_rs::Value as PropValue;

/// Query operators for conditions
#[derive(Debug, Clone, PartialEq)]
pub enum Operator {
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

impl Operator {
    fn from_str(s: &str) -> Option<Self> {
        match s {
            "=" | "==" => Some(Operator::Eq),
            "!=" | "<>" => Some(Operator::Ne),
            ">" => Some(Operator::Gt),
            ">=" => Some(Operator::Ge),
            "<" => Some(Operator::Lt),
            "<=" => Some(Operator::Le),
            _ => None,
        }
    }
}

/// Sort order for results
#[derive(Debug, Clone, PartialEq)]
pub enum SortOrder {
    Asc,
    Desc,
}

/// A query condition for filtering
#[derive(Debug, Clone)]
pub struct Condition {
    pub field: String,
    pub operator: Operator,
    pub value: Value,
}

/// Value types in queries
#[derive(Debug, Clone)]
pub enum Value {
    String(String),
    Int(i64),
    Float(f64),
    Bool(bool),
    Null,
    List(Vec<Value>),
}

impl Value {
    fn as_f64(&self) -> Option<f64> {
        match self {
            Value::Float(f) => Some(*f),
            Value::Int(i) => Some(*i as f64),
            _ => None,
        }
    }
}

impl Condition {
    pub fn new(field: impl Into<String>, operator: Operator, value: Value) -> Self {
        Self {
            field: field.into(),
            operator,
            value,
        }
    }

    /// Evaluate condition against properties.
    ///
    /// Properties carry real types now, so a numeric comparison against an
    /// int or float is exact rather than a parse of its rendering. A string
    /// that happens to hold a number still compares numerically, so queries
    /// written against the old string-only storage keep working.
    pub fn evaluate(&self, properties: &HashMap<String, PropValue>) -> bool {
        match self.operator {
            Operator::Exists => properties.contains_key(&self.field),
            Operator::NotExists => !properties.contains_key(&self.field),
            _ => {
                if let Some(prop_value) = properties.get(&self.field) {
                    self.compare(prop_value)
                } else {
                    false
                }
            }
        }
    }

    /// Render a property for the string operators, which had every value as
    /// text before properties were typed.
    fn prop_text(prop: &PropValue) -> String {
        match prop {
            PropValue::Null => String::new(),
            PropValue::Bool(b) => b.to_string(),
            PropValue::Int(i) => i.to_string(),
            PropValue::Float(f) => f.to_string(),
            PropValue::String(s) => s.clone(),
            PropValue::Reference(r) => r.to_ison(),
        }
    }

    /// Numeric view of a property: exact for int/float, lenient for a string
    /// that parses, so `age > 25` still matches an age stored as "30".
    fn prop_f64(prop: &PropValue) -> Option<f64> {
        match prop {
            PropValue::Int(i) => Some(*i as f64),
            PropValue::Float(f) => Some(*f),
            PropValue::String(s) => s.parse::<f64>().ok(),
            _ => None,
        }
    }

    fn compare(&self, prop: &PropValue) -> bool {
        let text = Self::prop_text(prop);
        let prop_value: &str = &text;
        match &self.operator {
            Operator::Eq => self.eq_compare(prop),
            Operator::Ne => !self.eq_compare(prop),
            Operator::Gt => self.numeric_compare(prop, |a, b| a > b),
            Operator::Ge => self.numeric_compare(prop, |a, b| a >= b),
            Operator::Lt => self.numeric_compare(prop, |a, b| a < b),
            Operator::Le => self.numeric_compare(prop, |a, b| a <= b),
            Operator::In => self.in_compare(prop, true),
            Operator::NotIn => self.in_compare(prop, false),
            Operator::Contains => {
                if let Value::String(s) = &self.value {
                    prop_value.contains(s.as_str())
                } else {
                    false
                }
            }
            Operator::StartsWith => {
                if let Value::String(s) = &self.value {
                    prop_value.starts_with(s.as_str())
                } else {
                    false
                }
            }
            Operator::EndsWith => {
                if let Value::String(s) = &self.value {
                    prop_value.ends_with(s.as_str())
                } else {
                    false
                }
            }
            Operator::Matches => {
                if let Value::String(pattern) = &self.value {
                    regex::Regex::new(pattern)
                        .map(|re| re.is_match(prop_value))
                        .unwrap_or(false)
                } else {
                    false
                }
            }
            _ => false,
        }
    }

    fn eq_compare(&self, prop: &PropValue) -> bool {
        match &self.value {
            Value::String(s) => Self::prop_text(prop) == *s,
            Value::Int(i) => Self::prop_f64(prop) == Some(*i as f64),
            Value::Float(f) => Self::prop_f64(prop) == Some(*f),
            Value::Bool(b) => match prop {
                PropValue::Bool(p) => p == b,
                PropValue::String(s) => s.parse::<bool>().ok() == Some(*b),
                _ => false,
            },
            Value::Null => matches!(prop, PropValue::Null)
                || matches!(prop, PropValue::String(s) if s.is_empty()),
            _ => false,
        }
    }

    fn numeric_compare<F>(&self, prop: &PropValue, cmp: F) -> bool
    where
        F: Fn(f64, f64) -> bool,
    {
        let prop_num = Self::prop_f64(prop);
        let val_num = self.value.as_f64();
        match (prop_num, val_num) {
            (Some(a), Some(b)) => cmp(a, b),
            _ => false,
        }
    }

    fn in_compare(&self, prop: &PropValue, should_contain: bool) -> bool {
        if let Value::List(list) = &self.value {
            let found = list.iter().any(|v| {
                if let Value::String(s) = v {
                    Self::prop_text(prop) == *s
                } else if let Value::Int(i) = v {
                    Self::prop_f64(prop) == Some(*i as f64)
                } else {
                    false
                }
            });
            if should_contain { found } else { !found }
        } else {
            false
        }
    }
}

/// Traversal step in TRAVERSE query
#[derive(Debug, Clone)]
pub struct TraversalStep {
    pub direction: Direction,
    pub rel_type: String,
    pub target_type: String,
}

/// Parsed query structure
///
/// WHERE conditions are stored as OR-groups of AND-ed conditions
/// (`c1 AND c2 OR c3` parses as `[[c1, c2], [c3]]`): a row matches when
/// every condition of at least one group matches. An empty list matches
/// everything.
#[derive(Debug, Clone)]
pub struct ParsedQuery {
    pub query_type: String,
    pub node_type: Option<String>,
    pub rel_type: Option<String>,
    pub condition_groups: Vec<Vec<Condition>>,
    pub order_by: Option<String>,
    pub order_dir: SortOrder,
    pub limit: Option<usize>,
    pub offset: usize,
    pub return_fields: Option<Vec<String>>,
    pub start: Option<NodeId>,
    pub target: Option<NodeId>,
    pub source: Option<NodeId>,
    pub pattern: Vec<TraversalStep>,
    pub max_depth: Option<usize>,
    pub max_hops: usize,
    pub via: Option<String>,
    pub property: Option<String>,
}

impl Default for ParsedQuery {
    fn default() -> Self {
        Self {
            query_type: String::new(),
            node_type: None,
            rel_type: None,
            condition_groups: Vec::new(),
            order_by: None,
            order_dir: SortOrder::Asc,
            limit: None,
            offset: 0,
            return_fields: None,
            start: None,
            target: None,
            source: None,
            pattern: Vec::new(),
            max_depth: None,
            max_hops: 10,
            via: None,
            property: None,
        }
    }
}

/// Result of a query execution
#[derive(Debug)]
pub struct QueryResult {
    pub data: Vec<QueryData>,
    pub count: usize,
    pub total_count: usize,
    pub execution_time_ms: f64,
    pub query: String,
    pub query_type: String,
}

/// Query result data variants
#[derive(Debug, Clone)]
pub enum QueryData {
    Node {
        node_type: String,
        id: String,
        properties: HashMap<String, PropValue>,
    },
    Edge {
        rel_type: String,
        source: NodeId,
        target: NodeId,
        properties: HashMap<String, PropValue>,
    },
    NodeRef(NodeId),
    Path {
        nodes: Vec<NodeId>,
        edges: Vec<EdgeData>,
        length: usize,
    },
    Count(usize),
    Aggregate(Option<f64>),
    Fields(HashMap<String, PropValue>),
}

#[derive(Debug, Clone)]
pub struct EdgeData {
    pub rel_type: String,
    pub source: NodeId,
    pub target: NodeId,
}

impl QueryResult {
    /// Get first result
    pub fn first(&self) -> Option<&QueryData> {
        self.data.first()
    }

    /// Check if result is empty
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// Iterate over data
    pub fn iter(&self) -> impl Iterator<Item = &QueryData> {
        self.data.iter()
    }
}

// =============================================================================
// ISONQL Parser
// =============================================================================

/// Parser for ISONQL queries
pub struct ISONQLParser {
    tokens: Vec<String>,
    pos: usize,
}

impl ISONQLParser {
    pub fn new() -> Self {
        Self {
            tokens: Vec::new(),
            pos: 0,
        }
    }

    /// Parse an ISONQL query string
    pub fn parse(&mut self, query: &str) -> Result<ParsedQuery> {
        self.tokens = self.tokenize(query);
        self.pos = 0;

        if self.tokens.is_empty() {
            return Err(GraphError::ParseError("Empty query".into()));
        }

        let keyword = self.tokens[0].to_uppercase();
        match keyword.as_str() {
            "NODES" => self.parse_nodes_query(),
            "EDGES" => self.parse_edges_query(),
            "TRAVERSE" => self.parse_traverse_query(),
            "PATH" => self.parse_path_query(),
            "COUNT" => self.parse_count_query(),
            "SUM" | "AVG" | "MIN" | "MAX" => self.parse_aggregation_query(&keyword),
            _ => Err(GraphError::ParseError(format!(
                "Unknown query type: {}. Supported: NODES, EDGES, TRAVERSE, PATH, COUNT, SUM, AVG, MIN, MAX",
                keyword
            ))),
        }
    }

    fn tokenize(&self, query: &str) -> Vec<String> {
        let mut tokens = Vec::new();
        let chars: Vec<char> = query.chars().collect();
        let mut i = 0;

        while i < chars.len() {
            // Skip whitespace
            if chars[i].is_whitespace() {
                i += 1;
                continue;
            }

            // String literals
            if chars[i] == '"' || chars[i] == '\'' {
                let quote = chars[i];
                i += 1;
                let start = i;
                while i < chars.len() && chars[i] != quote {
                    if chars[i] == '\\' && i + 1 < chars.len() {
                        i += 2;
                    } else {
                        i += 1;
                    }
                }
                tokens.push(chars[start..i].iter().collect());
                i += 1;
                continue;
            }

            // Multi-char operators
            if i + 1 < chars.len() {
                let two: String = chars[i..=i + 1].iter().collect();
                if ["==", "!=", ">=", "<=", "<>", "->", "<-", "--"].contains(&two.as_str()) {
                    tokens.push(two);
                    i += 2;
                    continue;
                }
            }

            // Single-char operators
            if "=<>!(),.".contains(chars[i]) {
                tokens.push(chars[i].to_string());
                i += 1;
                continue;
            }

            // Node reference :type:id
            if chars[i] == ':' {
                let start = i;
                i += 1;
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == ':' || chars[i] == '_' || chars[i] == '-') {
                    i += 1;
                }
                tokens.push(chars[start..i].iter().collect());
                continue;
            }

            // Words (a ':' joins the word when immediately followed by an
            // alphanumeric/underscore char, so `type:id` lexes as one token)
            if chars[i].is_alphanumeric() || chars[i] == '_' {
                let start = i;
                while i < chars.len() {
                    let c = chars[i];
                    let joining_colon = c == ':'
                        && i + 1 < chars.len()
                        && (chars[i + 1].is_alphanumeric() || chars[i + 1] == '_');
                    if c.is_alphanumeric() || c == '_' || c == '.' || c == '-' || joining_colon {
                        i += 1;
                    } else {
                        break;
                    }
                }
                tokens.push(chars[start..i].iter().collect());
                continue;
            }

            i += 1;
        }

        tokens
    }

    fn current(&self) -> Option<&str> {
        self.tokens.get(self.pos).map(|s| s.as_str())
    }

    fn advance(&mut self) -> Option<String> {
        let token = self.tokens.get(self.pos).cloned();
        self.pos += 1;
        token
    }

    fn expect(&mut self, expected: &str) -> Result<String> {
        let token = self.advance();
        match token {
            Some(t) if t.eq_ignore_ascii_case(expected) => Ok(t),
            Some(t) => Err(GraphError::ParseError(format!("Expected '{}', got '{}'", expected, t))),
            None => Err(GraphError::ParseError(format!("Expected '{}', got end of query", expected))),
        }
    }

    fn match_any(&self, expected: &[&str]) -> bool {
        if let Some(current) = self.current() {
            expected.iter().any(|e| current.eq_ignore_ascii_case(e))
        } else {
            false
        }
    }

    // -------------------------------------------------------------------------
    // Query Parsers
    // -------------------------------------------------------------------------

    fn parse_nodes_query(&mut self) -> Result<ParsedQuery> {
        self.advance(); // Skip 'NODES'
        let mut query = ParsedQuery {
            query_type: "NODES".into(),
            ..Default::default()
        };

        // Node type (optional)
        if self.current().is_some() && !self.match_any(&["WHERE", "ORDER", "LIMIT", "RETURN"]) {
            let node_type = self.advance().unwrap();
            query.node_type = Some(node_type);
            if self.match_any(&["("]) {
                self.advance();
                let shorthand = self.parse_shorthand_conditions()?;
                if !shorthand.is_empty() {
                    query.condition_groups = vec![shorthand];
                }
            }
        }

        // WHERE clause
        if self.match_any(&["WHERE"]) {
            self.advance();
            let where_groups = self.parse_conditions()?;
            query.condition_groups = Self::and_combine(query.condition_groups, where_groups);
        }

        // ORDER BY clause
        if self.match_any(&["ORDER"]) {
            self.advance();
            self.expect("BY")?;
            query.order_by = self.advance();
            if self.match_any(&["ASC", "DESC"]) {
                let dir = self.advance().unwrap();
                query.order_dir = if dir.eq_ignore_ascii_case("DESC") {
                    SortOrder::Desc
                } else {
                    SortOrder::Asc
                };
            }
        }

        // LIMIT clause
        if self.match_any(&["LIMIT"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.limit = n.parse().ok();
            }
        }

        // OFFSET clause
        if self.match_any(&["OFFSET"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.offset = n.parse().unwrap_or(0);
            }
        }

        // RETURN clause
        if self.match_any(&["RETURN"]) {
            self.advance();
            query.return_fields = Some(self.parse_field_list());
        }

        Ok(query)
    }

    fn parse_edges_query(&mut self) -> Result<ParsedQuery> {
        self.advance(); // Skip 'EDGES'
        let mut query = ParsedQuery {
            query_type: "EDGES".into(),
            ..Default::default()
        };

        // Edge type (optional)
        if self.current().is_some() && !self.match_any(&["WHERE", "LIMIT"]) {
            query.rel_type = self.advance();
        }

        // WHERE clause
        if self.match_any(&["WHERE"]) {
            self.advance();
            query.condition_groups = self.parse_conditions()?;
        }

        // LIMIT clause
        if self.match_any(&["LIMIT"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.limit = n.parse().ok();
            }
        }

        Ok(query)
    }

    fn parse_traverse_query(&mut self) -> Result<ParsedQuery> {
        self.advance(); // Skip 'TRAVERSE'
        let mut query = ParsedQuery {
            query_type: "TRAVERSE".into(),
            ..Default::default()
        };

        // Start node
        if let Some(start_token) = self.advance() {
            query.start = Some(self.parse_node_ref(&start_token)?);
        }

        // Parse traversal pattern
        while self.match_any(&["->", "<-", "--"]) {
            let direction = self.advance().unwrap();
            let rel_type = self.advance().ok_or_else(|| {
                GraphError::ParseError("Expected relationship type".into())
            })?;

            let mut target_type = "*".to_string();
            let dir2 = if self.match_any(&["->", "<-", "--"]) {
                let d = self.advance().unwrap();
                if self.current().is_some() && !self.match_any(&["MAX", "LIMIT"]) {
                    target_type = self.advance().unwrap();
                }
                d
            } else {
                direction.clone()
            };

            query.pattern.push(TraversalStep {
                direction: self.direction_from_arrows(&direction, &dir2),
                rel_type,
                target_type,
            });
        }

        // MAX depth
        if self.match_any(&["MAX"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.max_depth = n.parse().ok();
            }
        }

        // LIMIT
        if self.match_any(&["LIMIT"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.limit = n.parse().ok();
            }
        }

        Ok(query)
    }

    fn parse_path_query(&mut self) -> Result<ParsedQuery> {
        self.advance(); // Skip 'PATH'
        let mut query = ParsedQuery {
            query_type: "PATH".into(),
            ..Default::default()
        };

        // Source node
        if let Some(source_token) = self.advance() {
            query.source = Some(self.parse_node_ref(&source_token)?);
        }

        // TO keyword
        self.expect("TO")?;

        // Target node
        if let Some(target_token) = self.advance() {
            query.target = Some(self.parse_node_ref(&target_token)?);
        }

        // VIA
        if self.match_any(&["VIA"]) {
            self.advance();
            query.via = self.advance();
        }

        // MAX hops
        if self.match_any(&["MAX"]) {
            self.advance();
            if let Some(n) = self.advance() {
                query.max_hops = n.parse().unwrap_or(10);
            }
        }

        Ok(query)
    }

    fn parse_count_query(&mut self) -> Result<ParsedQuery> {
        self.advance(); // Skip 'COUNT'
        let mut query = ParsedQuery {
            query_type: "COUNT".into(),
            ..Default::default()
        };

        // Node type
        if self.current().is_some() && !self.match_any(&["WHERE"]) {
            query.node_type = self.advance();
        }

        // WHERE clause
        if self.match_any(&["WHERE"]) {
            self.advance();
            query.condition_groups = self.parse_conditions()?;
        }

        Ok(query)
    }

    fn parse_aggregation_query(&mut self, agg_type: &str) -> Result<ParsedQuery> {
        self.advance(); // Skip aggregation keyword
        let mut query = ParsedQuery {
            query_type: agg_type.to_uppercase(),
            ..Default::default()
        };

        // type.property
        if let Some(type_prop) = self.advance() {
            if type_prop.contains('.') {
                let parts: Vec<&str> = type_prop.splitn(2, '.').collect();
                query.node_type = Some(parts[0].to_string());
                query.property = Some(parts[1].to_string());
            } else {
                query.property = Some(type_prop);
            }
        }

        // WHERE clause
        if self.match_any(&["WHERE"]) {
            self.advance();
            query.condition_groups = self.parse_conditions()?;
        }

        Ok(query)
    }

    // -------------------------------------------------------------------------
    // Condition Parsing
    // -------------------------------------------------------------------------

    /// Parse a WHERE condition sequence into OR-groups of AND-ed conditions
    /// (AND binds tighter than OR): `a AND b OR c` -> `[[a, b], [c]]`.
    fn parse_conditions(&mut self) -> Result<Vec<Vec<Condition>>> {
        let mut groups: Vec<Vec<Condition>> = Vec::new();
        let mut current_group: Vec<Condition> = Vec::new();

        loop {
            if let Some(cond) = self.parse_single_condition()? {
                current_group.push(cond);
            }

            if self.match_any(&["AND"]) {
                self.advance();
            } else if self.match_any(&["OR"]) {
                self.advance();
                if !current_group.is_empty() {
                    groups.push(std::mem::take(&mut current_group));
                }
            } else {
                break;
            }
        }

        if !current_group.is_empty() {
            groups.push(current_group);
        }

        Ok(groups)
    }

    /// AND-combine two OR-group sets by distribution:
    /// `(b1 OR b2) AND (o1 OR o2)` -> `b1 o1 OR b1 o2 OR b2 o1 OR b2 o2`.
    fn and_combine(
        base: Vec<Vec<Condition>>,
        other: Vec<Vec<Condition>>,
    ) -> Vec<Vec<Condition>> {
        if base.is_empty() {
            return other;
        }
        if other.is_empty() {
            return base;
        }

        let mut result = Vec::with_capacity(base.len() * other.len());
        for b in &base {
            for o in &other {
                let mut group = b.clone();
                group.extend(o.iter().cloned());
                result.push(group);
            }
        }
        result
    }

    fn parse_single_condition(&mut self) -> Result<Option<Condition>> {
        if self.current().is_none() {
            return Ok(None);
        }

        // EXISTS / NOT EXISTS
        if self.match_any(&["EXISTS"]) {
            self.advance();
            if let Some(field) = self.advance() {
                return Ok(Some(Condition::new(field, Operator::Exists, Value::Null)));
            }
        }

        if self.match_any(&["NOT"]) {
            self.advance();
            if self.match_any(&["EXISTS"]) {
                self.advance();
                if let Some(field) = self.advance() {
                    return Ok(Some(Condition::new(field, Operator::NotExists, Value::Null)));
                }
            }
        }

        let field = match self.advance() {
            Some(f) => f,
            None => return Ok(None),
        };

        // Check if it's a keyword
        let keywords = ["WHERE", "AND", "OR", "ORDER", "LIMIT", "OFFSET", "RETURN"];
        if keywords.iter().any(|k| field.eq_ignore_ascii_case(k)) {
            self.pos -= 1;
            return Ok(None);
        }

        // Operator
        let op_token = match self.current() {
            Some(t) => t.to_string(),
            None => return Ok(None),
        };

        let operator = if let Some(op) = Operator::from_str(&op_token) {
            self.advance();
            op
        } else {
            match op_token.to_uppercase().as_str() {
                "IN" => { self.advance(); Operator::In }
                "CONTAINS" => { self.advance(); Operator::Contains }
                "STARTS_WITH" => { self.advance(); Operator::StartsWith }
                "ENDS_WITH" => { self.advance(); Operator::EndsWith }
                "MATCHES" => { self.advance(); Operator::Matches }
                "EXISTS" => {
                    self.advance();
                    return Ok(Some(Condition::new(field, Operator::Exists, Value::Null)));
                }
                "NOT" => {
                    let next_upper = self
                        .tokens
                        .get(self.pos + 1)
                        .map(|t| t.to_uppercase())
                        .unwrap_or_default();
                    match next_upper.as_str() {
                        "EXISTS" => {
                            self.advance();
                            self.advance();
                            return Ok(Some(Condition::new(
                                field,
                                Operator::NotExists,
                                Value::Null,
                            )));
                        }
                        "IN" => {
                            self.advance();
                            self.advance();
                            Operator::NotIn
                        }
                        _ => {
                            return Err(GraphError::ParseError(format!(
                                "Expected EXISTS or IN after NOT, got '{}'",
                                next_upper
                            )))
                        }
                    }
                }
                _ => {
                    return Err(GraphError::ParseError(format!(
                        "Unknown operator '{}' in condition",
                        op_token
                    )))
                }
            }
        };

        // Value
        let value = self.parse_value()?;

        Ok(Some(Condition::new(field, operator, value)))
    }

    fn parse_value(&mut self) -> Result<Value> {
        if self.match_any(&["("]) {
            self.advance();
            let mut values = Vec::new();
            while !self.match_any(&[")"]) {
                if self.current().is_none() {
                    return Err(GraphError::ParseError(
                        "Unclosed list, expected ')'".into(),
                    ));
                }
                let val = self.parse_single_value()?;
                values.push(val);
                if self.match_any(&[","]) {
                    self.advance();
                }
            }
            self.advance(); // Skip ')'
            return Ok(Value::List(values));
        }

        self.parse_single_value()
    }

    fn parse_single_value(&mut self) -> Result<Value> {
        let token = match self.advance() {
            Some(t) => t,
            None => return Ok(Value::Null),
        };

        let upper = token.to_uppercase();
        match upper.as_str() {
            "TRUE" => Ok(Value::Bool(true)),
            "FALSE" => Ok(Value::Bool(false)),
            "NULL" | "NONE" | "NIL" => Ok(Value::Null),
            _ => {
                // Try parsing as number
                if let Ok(i) = token.parse::<i64>() {
                    Ok(Value::Int(i))
                } else if let Ok(f) = token.parse::<f64>() {
                    Ok(Value::Float(f))
                } else {
                    Ok(Value::String(token))
                }
            }
        }
    }

    fn parse_shorthand_conditions(&mut self) -> Result<Vec<Condition>> {
        let mut conditions = Vec::new();

        while !self.match_any(&[")"]) {
            if let Some(field) = self.advance() {
                if self.match_any(&["="]) {
                    self.advance();
                    let value = self.parse_single_value()?;
                    conditions.push(Condition::new(field, Operator::Eq, value));
                }
            }
            if self.match_any(&[","]) {
                self.advance();
            }
        }

        self.advance(); // Skip ')'
        Ok(conditions)
    }

    fn parse_field_list(&mut self) -> Vec<String> {
        let mut fields = Vec::new();
        while self.current().is_some() {
            if self.match_any(&["LIMIT", "OFFSET", "ORDER"]) {
                break;
            }
            fields.push(self.advance().unwrap());
            if self.match_any(&[","]) {
                self.advance();
            } else {
                break;
            }
        }
        fields
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    fn parse_node_ref(&self, token: &str) -> Result<NodeId> {
        let token = token.trim_start_matches(':');
        let parts: Vec<&str> = token.splitn(2, ':').collect();
        if parts.len() >= 2 {
            Ok(NodeId::new(parts[0], parts[1]))
        } else {
            Err(GraphError::ParseError(format!(
                "Invalid node reference: {}. Expected format: type:id",
                token
            )))
        }
    }

    fn direction_from_arrows(&self, arrow1: &str, arrow2: &str) -> Direction {
        if arrow1 == "->" || arrow2 == "->" {
            Direction::Out
        } else if arrow1 == "<-" || arrow2 == "<-" {
            Direction::In
        } else {
            Direction::Both
        }
    }
}

impl Default for ISONQLParser {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// Query Engine
// =============================================================================

/// ISONQL Query Engine for ISONGraph
pub struct QueryEngine<'a> {
    graph: &'a ISONGraph,
}

impl<'a> QueryEngine<'a> {
    /// Create a new query engine for the given graph
    pub fn new(graph: &'a ISONGraph) -> Self {
        Self { graph }
    }

    /// Execute an ISONQL query string
    pub fn execute(&self, query: &str) -> Result<QueryResult> {
        let start_time = Instant::now();

        let mut parser = ISONQLParser::new();
        let parsed = parser.parse(query)?;

        let (data, total) = match parsed.query_type.as_str() {
            "NODES" => self.execute_nodes(&parsed)?,
            "EDGES" => self.execute_edges(&parsed)?,
            "TRAVERSE" => self.execute_traverse(&parsed)?,
            "PATH" => self.execute_path(&parsed)?,
            "COUNT" => self.execute_count(&parsed)?,
            "SUM" | "AVG" | "MIN" | "MAX" => self.execute_aggregation(&parsed)?,
            _ => return Err(GraphError::ParseError(format!("Unknown query type: {}", parsed.query_type))),
        };

        let execution_time = start_time.elapsed().as_secs_f64() * 1000.0;

        Ok(QueryResult {
            count: data.len(),
            data,
            total_count: total,
            execution_time_ms: execution_time,
            query: query.to_string(),
            query_type: parsed.query_type,
        })
    }

    // -------------------------------------------------------------------------
    // Query Executors
    // -------------------------------------------------------------------------

    fn execute_nodes(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let node_type = parsed.node_type.as_deref();
        let condition_groups = &parsed.condition_groups;

        // Get nodes
        let mut nodes: Vec<&Node> = if let Some(nt) = node_type {
            self.graph.nodes_of_type(nt).collect()
        } else {
            self.graph.nodes().collect()
        };

        // Filter
        if !condition_groups.is_empty() {
            nodes.retain(|n| self.matches_conditions(&n.properties, condition_groups));
        }

        let total = nodes.len();

        // Sort
        if let Some(order_by) = &parsed.order_by {
            let desc = parsed.order_dir == SortOrder::Desc;
            nodes.sort_by(|a, b| {
                // Numbers sort numerically whether they are stored as int,
                // float, or a string that parses; anything else falls back to
                // its text, which is how this ordered before properties were
                // typed.
                let a_num = a.properties.get(order_by).and_then(Condition::prop_f64);
                let b_num = b.properties.get(order_by).and_then(Condition::prop_f64);
                if let (Some(x), Some(y)) = (a_num, b_num) {
                    let ord = x.partial_cmp(&y).unwrap_or(std::cmp::Ordering::Equal);
                    return if desc { ord.reverse() } else { ord };
                }

                let a_val = a.properties.get(order_by).map(Condition::prop_text)
                    .unwrap_or_default();
                let b_val = b.properties.get(order_by).map(Condition::prop_text)
                    .unwrap_or_default();
                if desc {
                    b_val.cmp(&a_val)
                } else {
                    a_val.cmp(&b_val)
                }
            });
        }

        // Pagination
        let offset = parsed.offset;
        let nodes: Vec<&Node> = nodes.into_iter().skip(offset).collect();
        let nodes: Vec<&Node> = if let Some(limit) = parsed.limit {
            nodes.into_iter().take(limit).collect()
        } else {
            nodes
        };

        // Format output
        let data: Vec<QueryData> = if let Some(fields) = &parsed.return_fields {
            nodes.iter().map(|n| {
                let mut props = HashMap::new();
                for f in fields {
                    if let Some(v) = n.properties.get(f) {
                        props.insert(f.clone(), v.clone());
                    }
                }
                QueryData::Fields(props)
            }).collect()
        } else {
            nodes.iter().map(|n| QueryData::Node {
                node_type: n.node_type.clone(),
                id: n.id.clone(),
                properties: n.properties.clone(),
            }).collect()
        };

        Ok((data, total))
    }

    fn execute_edges(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let rel_type = parsed.rel_type.as_deref();
        let condition_groups = &parsed.condition_groups;

        // Get edges
        let mut edges: Vec<&Edge> = if let Some(rt) = rel_type {
            self.graph.edges_of_type(rt).collect()
        } else {
            self.graph.edge_types().iter()
                .flat_map(|rt| self.graph.edges_of_type(rt))
                .collect()
        };

        // Filter
        if !condition_groups.is_empty() {
            edges.retain(|e| self.matches_conditions(&e.properties, condition_groups));
        }

        let total = edges.len();

        // Limit
        let edges: Vec<&Edge> = if let Some(limit) = parsed.limit {
            edges.into_iter().take(limit).collect()
        } else {
            edges
        };

        let data: Vec<QueryData> = edges.iter().map(|e| QueryData::Edge {
            rel_type: e.rel_type.clone(),
            source: e.source.clone(),
            target: e.target.clone(),
            properties: e.properties.clone(),
        }).collect();

        Ok((data, total))
    }

    fn execute_traverse(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let start = parsed.start.as_ref().ok_or_else(|| {
            GraphError::ParseError("TRAVERSE requires start node".into())
        })?;

        let mut current: HashSet<String> = HashSet::new();
        current.insert(start.to_key());
        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start.to_key());
        let mut node_map: HashMap<String, NodeId> = HashMap::new();
        node_map.insert(start.to_key(), start.clone());

        for step in &parsed.pattern {
            let mut next_level: HashSet<String> = HashSet::new();
            let mut next_map: HashMap<String, NodeId> = HashMap::new();

            for key in &current {
                if let Some(node_id) = node_map.get(key) {
                    let neighbors = self.graph.neighbors(
                        &node_id.as_ref(),
                        Some(&step.rel_type),
                        step.direction,
                    );
                    for neighbor in neighbors {
                        let neighbor_key = neighbor.to_key();
                        if !visited.contains(&neighbor_key)
                            && (step.target_type == "*" || neighbor.node_type == step.target_type)
                        {
                            next_level.insert(neighbor_key.clone());
                            next_map.insert(neighbor_key, neighbor);
                        }
                    }
                }
            }

            for (k, v) in next_map {
                visited.insert(k.clone());
                node_map.insert(k, v);
            }
            current = next_level;

            if current.is_empty() {
                break;
            }
        }

        // Apply max_depth
        if let Some(max_depth) = parsed.max_depth {
            if max_depth > parsed.pattern.len() {
                let remaining = max_depth - parsed.pattern.len();
                let last_rel = parsed.pattern.last().map(|s| s.rel_type.as_str());
                let last_dir = parsed.pattern.last().map(|s| s.direction).unwrap_or(Direction::Out);

                for _ in 0..remaining {
                    let mut next_level: HashSet<String> = HashSet::new();
                    let mut next_map: HashMap<String, NodeId> = HashMap::new();

                    for key in &current {
                        if let Some(node_id) = node_map.get(key) {
                            let neighbors = self.graph.neighbors(
                                &node_id.as_ref(),
                                last_rel,
                                last_dir,
                            );
                            for neighbor in neighbors {
                                let neighbor_key = neighbor.to_key();
                                if !visited.contains(&neighbor_key) {
                                    next_level.insert(neighbor_key.clone());
                                    next_map.insert(neighbor_key, neighbor);
                                }
                            }
                        }
                    }

                    for (k, v) in next_map {
                        visited.insert(k.clone());
                        current.insert(k.clone());
                        node_map.insert(k, v);
                    }

                    if next_level.is_empty() {
                        break;
                    }
                }
            }
        }

        let mut result: Vec<NodeId> = current.iter()
            .filter_map(|k| node_map.get(k).cloned())
            .collect();

        let total = result.len();

        if let Some(limit) = parsed.limit {
            result.truncate(limit);
        }

        let data: Vec<QueryData> = result.into_iter()
            .map(QueryData::NodeRef)
            .collect();

        Ok((data, total))
    }

    fn execute_path(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let source = parsed.source.as_ref().ok_or_else(|| {
            GraphError::ParseError("PATH requires source node".into())
        })?;
        let target = parsed.target.as_ref().ok_or_else(|| {
            GraphError::ParseError("PATH requires target node".into())
        })?;

        let path = self.graph.shortest_path(
            &source.as_ref(),
            &target.as_ref(),
            parsed.via.as_deref(),
            parsed.max_hops,
            Direction::Out,
        );

        if let Some(path) = path {
            let length = path.length();
            let edges: Vec<EdgeData> = path.edges.iter().map(|e| EdgeData {
                rel_type: e.rel_type.clone(),
                source: e.source.clone(),
                target: e.target.clone(),
            }).collect();

            let data = vec![QueryData::Path {
                nodes: path.nodes,
                edges,
                length,
            }];
            Ok((data, 1))
        } else {
            Ok((vec![], 0))
        }
    }

    fn execute_count(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let node_type = parsed.node_type.as_deref();
        let condition_groups = &parsed.condition_groups;

        let mut nodes: Vec<&Node> = if let Some(nt) = node_type {
            self.graph.nodes_of_type(nt).collect()
        } else {
            self.graph.nodes().collect()
        };

        if !condition_groups.is_empty() {
            nodes.retain(|n| self.matches_conditions(&n.properties, condition_groups));
        }

        let count = nodes.len();
        Ok((vec![QueryData::Count(count)], count))
    }

    fn execute_aggregation(&self, parsed: &ParsedQuery) -> Result<(Vec<QueryData>, usize)> {
        let node_type = parsed.node_type.as_deref();
        let prop = parsed.property.as_ref().ok_or_else(|| {
            GraphError::ParseError("Aggregation requires property".into())
        })?;
        let condition_groups = &parsed.condition_groups;

        let mut nodes: Vec<&Node> = if let Some(nt) = node_type {
            self.graph.nodes_of_type(nt).collect()
        } else {
            self.graph.nodes().collect()
        };

        if !condition_groups.is_empty() {
            nodes.retain(|n| self.matches_conditions(&n.properties, condition_groups));
        }

        // Extract numeric values
        let values: Vec<f64> = nodes.iter()
            .filter_map(|n| n.properties.get(prop))
            .filter_map(Condition::prop_f64)
            .collect();

        if values.is_empty() {
            return Ok((vec![QueryData::Aggregate(None)], 0));
        }

        let result = match parsed.query_type.as_str() {
            "SUM" => values.iter().sum(),
            "AVG" => values.iter().sum::<f64>() / values.len() as f64,
            "MIN" => values.iter().cloned().fold(f64::INFINITY, f64::min),
            "MAX" => values.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
            _ => return Ok((vec![QueryData::Aggregate(None)], 0)),
        };

        Ok((vec![QueryData::Aggregate(Some(result))], values.len()))
    }

    /// A row matches when every condition of at least one OR-group matches.
    /// An empty group list matches everything.
    fn matches_conditions(
        &self,
        properties: &HashMap<String, PropValue>,
        condition_groups: &[Vec<Condition>],
    ) -> bool {
        condition_groups.is_empty()
            || condition_groups
                .iter()
                .any(|group| group.iter().all(|c| c.evaluate(properties)))
    }
}

// =============================================================================
// Fluent Query Builder
// =============================================================================

/// Fluent API for building node queries
pub struct QueryBuilder<'a> {
    engine: &'a QueryEngine<'a>,
    node_type: String,
    conditions: Vec<Condition>,
    order_by: Option<String>,
    order_dir: SortOrder,
    limit: Option<usize>,
    offset: usize,
    fields: Option<Vec<String>>,
}

impl<'a> QueryBuilder<'a> {
    pub fn new(engine: &'a QueryEngine<'a>, node_type: impl Into<String>) -> Self {
        Self {
            engine,
            node_type: node_type.into(),
            conditions: Vec::new(),
            order_by: None,
            order_dir: SortOrder::Asc,
            limit: None,
            offset: 0,
            fields: None,
        }
    }

    /// Add a WHERE condition
    pub fn where_cond(mut self, field: impl Into<String>, op: &str, value: impl Into<String>) -> Self {
        let operator = match op {
            "=" | "==" => Operator::Eq,
            "!=" | "<>" => Operator::Ne,
            ">" => Operator::Gt,
            ">=" => Operator::Ge,
            "<" => Operator::Lt,
            "<=" => Operator::Le,
            _ => Operator::Eq,
        };
        self.conditions.push(Condition::new(field, operator, Value::String(value.into())));
        self
    }

    /// Add numeric WHERE condition
    pub fn where_num(mut self, field: impl Into<String>, op: &str, value: i64) -> Self {
        let operator = match op {
            "=" | "==" => Operator::Eq,
            "!=" | "<>" => Operator::Ne,
            ">" => Operator::Gt,
            ">=" => Operator::Ge,
            "<" => Operator::Lt,
            "<=" => Operator::Le,
            _ => Operator::Eq,
        };
        self.conditions.push(Condition::new(field, operator, Value::Int(value)));
        self
    }

    /// Set ORDER BY clause
    pub fn order_by(mut self, field: impl Into<String>, direction: &str) -> Self {
        self.order_by = Some(field.into());
        self.order_dir = if direction.eq_ignore_ascii_case("DESC") {
            SortOrder::Desc
        } else {
            SortOrder::Asc
        };
        self
    }

    /// Set LIMIT
    pub fn limit(mut self, n: usize) -> Self {
        self.limit = Some(n);
        self
    }

    /// Set OFFSET
    pub fn offset(mut self, n: usize) -> Self {
        self.offset = n;
        self
    }

    /// Set fields to return
    pub fn return_fields(mut self, fields: Vec<&str>) -> Self {
        self.fields = Some(fields.into_iter().map(String::from).collect());
        self
    }

    /// Execute the built query
    pub fn execute(self) -> Result<QueryResult> {
        let condition_groups = if self.conditions.is_empty() {
            Vec::new()
        } else {
            vec![self.conditions]
        };
        let parsed = ParsedQuery {
            query_type: "NODES".into(),
            node_type: Some(self.node_type.clone()),
            condition_groups,
            order_by: self.order_by,
            order_dir: self.order_dir,
            limit: self.limit,
            offset: self.offset,
            return_fields: self.fields,
            ..Default::default()
        };

        let start_time = Instant::now();
        let (data, total) = self.engine.execute_nodes(&parsed)?;
        let execution_time = start_time.elapsed().as_secs_f64() * 1000.0;

        Ok(QueryResult {
            count: data.len(),
            data,
            total_count: total,
            execution_time_ms: execution_time,
            query: format!("NODES {}", self.node_type),
            query_type: "NODES".into(),
        })
    }

    /// Execute count query
    pub fn count(self) -> Result<usize> {
        let condition_groups = if self.conditions.is_empty() {
            Vec::new()
        } else {
            vec![self.conditions]
        };
        let parsed = ParsedQuery {
            query_type: "COUNT".into(),
            node_type: Some(self.node_type),
            condition_groups,
            ..Default::default()
        };

        let (data, _) = self.engine.execute_count(&parsed)?;
        match data.first() {
            Some(QueryData::Count(n)) => Ok(*n),
            _ => Ok(0),
        }
    }
}

impl<'a> QueryEngine<'a> {
    /// Start a fluent query for nodes of a given type
    pub fn match_nodes(&'a self, node_type: impl Into<String>) -> QueryBuilder<'a> {
        QueryBuilder::new(self, node_type)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_graph() -> ISONGraph {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![("name", "Alice"), ("age", "30"), ("city", "NYC")]).unwrap();
        graph.add_node("person", "2", props![("name", "Bob"), ("age", "25"), ("city", "LA")]).unwrap();
        graph.add_node("person", "3", props![("name", "Charlie"), ("age", "35"), ("city", "NYC")]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![("since", "2020")]).unwrap();
        graph.add_edge("KNOWS", ("person", "2"), ("person", "3"), props![("since", "2021")]).unwrap();
        graph
    }

    #[test]
    fn test_parse_nodes_query() {
        let mut parser = ISONQLParser::new();
        let result = parser.parse("NODES person").unwrap();
        assert_eq!(result.query_type, "NODES");
        assert_eq!(result.node_type, Some("person".into()));
    }

    #[test]
    fn test_parse_nodes_with_where() {
        let mut parser = ISONQLParser::new();
        let result = parser.parse("NODES person WHERE age > 25").unwrap();
        assert_eq!(result.condition_groups.len(), 1);
        assert_eq!(result.condition_groups[0].len(), 1);
        assert_eq!(result.condition_groups[0][0].field, "age");
    }

    #[test]
    fn test_parse_where_or_groups() {
        let mut parser = ISONQLParser::new();
        // AND binds tighter than OR: (city=NYC AND age>30) OR (city=LA)
        let result = parser
            .parse("NODES person WHERE city = NYC AND age > 30 OR city = LA")
            .unwrap();
        assert_eq!(result.condition_groups.len(), 2);
        assert_eq!(result.condition_groups[0].len(), 2);
        assert_eq!(result.condition_groups[0][0].field, "city");
        assert_eq!(result.condition_groups[0][1].field, "age");
        assert_eq!(result.condition_groups[1].len(), 1);
        assert_eq!(result.condition_groups[1][0].field, "city");
    }

    #[test]
    fn test_execute_nodes() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("NODES person").unwrap();
        assert_eq!(result.count, 3);
    }

    #[test]
    fn test_execute_nodes_with_where() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("NODES person WHERE age > 25").unwrap();
        assert_eq!(result.count, 2);
    }

    #[test]
    fn test_execute_nodes_with_or() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        // Alice (NYC), Charlie (NYC) OR Bob (LA) -> all three
        let result = engine
            .execute("NODES person WHERE city = NYC OR city = LA")
            .unwrap();
        assert_eq!(result.count, 3);
    }

    #[test]
    fn test_execute_or_with_and_precedence() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        // (city=NYC AND age>30) -> Charlie; OR city=LA -> Bob => 2
        let result = engine
            .execute("NODES person WHERE city = NYC AND age > 30 OR city = LA")
            .unwrap();
        assert_eq!(result.count, 2);
        // No match on either side
        let result = engine
            .execute("NODES person WHERE city = SF OR age > 100")
            .unwrap();
        assert_eq!(result.count, 0);
    }

    #[test]
    fn test_execute_count_with_or() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine
            .execute("COUNT person WHERE age < 26 OR age > 34")
            .unwrap();
        match result.first() {
            Some(QueryData::Count(n)) => assert_eq!(*n, 2), // Bob (25), Charlie (35)
            _ => panic!("Expected count result"),
        }
    }

    #[test]
    fn test_execute_edges() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("EDGES KNOWS").unwrap();
        assert_eq!(result.count, 2);
    }

    #[test]
    fn test_execute_count() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("COUNT person").unwrap();
        match result.first() {
            Some(QueryData::Count(n)) => assert_eq!(*n, 3),
            _ => panic!("Expected count result"),
        }
    }

    #[test]
    fn test_execute_traverse() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("TRAVERSE person:1 -> KNOWS -> person").unwrap();
        assert!(result.count >= 1);
    }

    #[test]
    fn test_execute_path() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.execute("PATH person:1 TO person:3 VIA KNOWS").unwrap();
        assert_eq!(result.count, 1);
    }

    #[test]
    fn test_fluent_query() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        let result = engine.match_nodes("person")
            .where_num("age", ">", 25)
            .order_by("age", "ASC")
            .limit(2)
            .execute()
            .unwrap();
        assert!(result.count <= 2);
    }

    #[test]
    fn test_condition_evaluation() {
        let mut props: HashMap<String, PropValue> = HashMap::new();
        props.insert("age".into(), PropValue::String("30".to_string()));
        props.insert("name".into(), PropValue::String("Alice".to_string()));

        let cond = Condition::new("age", Operator::Gt, Value::Int(25));
        assert!(cond.evaluate(&props));

        let cond = Condition::new("name", Operator::Eq, Value::String("Alice".into()));
        assert!(cond.evaluate(&props));

        let cond = Condition::new("name", Operator::Contains, Value::String("lic".into()));
        assert!(cond.evaluate(&props));
    }

    #[test]
    fn test_exists_postfix_and_not_in() {
        let graph = create_test_graph();
        let mut extra = graph;
        extra.add_node("person", "4", props![("name", "Dave")]).unwrap();
        let engine = QueryEngine::new(&extra);

        let r = engine.execute("NODES person WHERE city EXISTS").unwrap();
        assert_eq!(r.count, 3);

        let r = engine.execute("NODES person WHERE city NOT EXISTS").unwrap();
        assert_eq!(r.count, 1);

        let r = engine.execute("NODES person WHERE city NOT IN ('NYC')").unwrap();
        assert_eq!(r.count, 1);
    }

    #[test]
    fn test_unknown_operator_errors() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        assert!(engine.execute("NODES person WHERE name LIKE 'A'").is_err());
    }

    #[test]
    fn test_unclosed_list_errors() {
        let graph = create_test_graph();
        let engine = QueryEngine::new(&graph);
        assert!(engine.execute("NODES person WHERE city IN ('NYC', 'LA'").is_err());
    }
}
