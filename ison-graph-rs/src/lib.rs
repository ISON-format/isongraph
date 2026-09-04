//! ISONGraph - A Token-Efficient Graph Store for Rust
//!
//! A property graph implementation with ISON persistence.
//! Supports multi-hop traversal, path finding, and fluent API.
//!
//! # Example
//!
//! ```rust
//! use ison_graph::{ISONGraph, NodeRef, Direction, props};
//!
//! let mut graph = ISONGraph::new("social");
//! // Properties keep their type: 30 is a number, "30" would be a string,
//! // and the two serialize differently.
//! graph.add_node("person", "1", props![("name", "Alice"), ("age", 30i64)]).unwrap();
//! graph.add_node("person", "2", props![("name", "Bob"), ("age", 25i64)]).unwrap();
//! graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![("since", 2020i64)]).unwrap();
//!
//! let friends = graph.neighbors(&("person", "1"), Some("KNOWS"), Direction::Out);
//! let fof = graph.multi_hop(&("person", "1"), Some("KNOWS"), 2, Direction::Out);
//! ```

use std::collections::{HashMap, HashSet, VecDeque};
use std::fs;
use std::path::Path as StdPath;
use std::sync::OnceLock;
use ison_rs::{
    dumps_canonical, dumps_canonical_isonl, loads, loads_isonl,
    Block as IsonBlock, Document as IsonDocument, Reference as IsonReference,
};

/// Converts a Rust primitive into an ISON property value.
///
/// `ison_rs::Value` has no `From` impls and the orphan rule stops this crate
/// adding them, so the conversions live here. This is sugar only - the value
/// stored is always `ison_rs::Value`, never a parallel model.
pub trait IntoValue {
    fn into_value(self) -> Value;
}

impl IntoValue for Value {
    fn into_value(self) -> Value { self }
}
impl IntoValue for &str {
    fn into_value(self) -> Value { Value::String(self.to_string()) }
}
impl IntoValue for String {
    fn into_value(self) -> Value { Value::String(self) }
}
impl IntoValue for i64 {
    fn into_value(self) -> Value { Value::Int(self) }
}
impl IntoValue for i32 {
    fn into_value(self) -> Value { Value::Int(self as i64) }
}
impl IntoValue for f64 {
    fn into_value(self) -> Value { Value::Float(self) }
}
impl IntoValue for bool {
    fn into_value(self) -> Value { Value::Bool(self) }
}

/// Build a property list with mixed value types.
///
/// A `Vec` is homogeneous, so a literal mixing an int and a string cannot be
/// written directly; this converts each value before collecting, which is
/// what makes `props![("staff", 42), ("name", "Acme")]` compile.
#[macro_export]
macro_rules! props {
    () => { ::std::vec::Vec::<(&str, $crate::Value)>::new() };
    ($(($k:expr, $v:expr)),* $(,)?) => {
        ::std::vec![$(($k, $crate::IntoValue::into_value($v))),*]
    };
}

/// Render a property value as text - the form every value had before
/// properties carried types. Query string operators and schema validation
/// use it so their behaviour is unchanged by typing the storage.
pub fn value_to_text(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::Bool(b) => b.to_string(),
        Value::Int(i) => i.to_string(),
        Value::Float(f) => f.to_string(),
        Value::String(s) => s.clone(),
        Value::Reference(r) => r.to_ison(),
    }
}

/// Property values are ISON values, re-exported so callers do not need a
/// direct ison-rs dependency. Storing anything else would mean a second
/// value model beside the parser's, which is what made this port emit every
/// value as a quoted string and disagree with the typed ports.
pub use ison_rs::Value;
use ison_rs::Value as IsonValue;
use thiserror::Error;
use regex::Regex;

#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};

/// Version of the library
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

// Query module (ISONQL)
pub mod query;

// Schema validation module
pub mod schema;

// =============================================================================
// Types
// =============================================================================

/// Node reference: (type, id)
pub type NodeRef<'a> = (&'a str, &'a str);

/// Owned node reference
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub struct NodeId {
    pub node_type: String,
    pub id: String,
}

impl NodeId {
    pub fn new(node_type: impl Into<String>, id: impl Into<String>) -> Self {
        Self {
            node_type: node_type.into(),
            id: id.into(),
        }
    }

    pub fn as_ref(&self) -> NodeRef<'_> {
        (&self.node_type, &self.id)
    }

    pub fn to_key(&self) -> String {
        format!("{}:{}", self.node_type, self.id)
    }

    pub fn to_ison_ref(&self) -> String {
        format!(":{}:{}", self.node_type, self.id)
    }
}

impl From<(&str, &str)> for NodeId {
    fn from(tuple: (&str, &str)) -> Self {
        NodeId::new(tuple.0, tuple.1)
    }
}

/// Traversal direction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub enum Direction {
    Out,
    In,
    Both,
}

// =============================================================================
// Data Structures
// =============================================================================

/// Represents a graph node with properties
#[derive(Debug, Clone)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub struct Node {
    pub node_type: String,
    pub id: String,
    pub properties: HashMap<String, Value>,
}

impl Node {
    pub fn new(node_type: impl Into<String>, id: impl Into<String>) -> Self {
        Self {
            node_type: node_type.into(),
            id: id.into(),
            properties: HashMap::new(),
        }
    }

    pub fn with_properties(mut self, props: Vec<(&str, Value)>) -> Self {
        for (k, v) in props {
            self.properties.insert(k.to_string(), v);
        }
        self
    }

    pub fn node_id(&self) -> NodeId {
        NodeId::new(&self.node_type, &self.id)
    }

    pub fn to_key(&self) -> String {
        format!("{}:{}", self.node_type, self.id)
    }
}

/// Represents a graph edge with properties
#[derive(Debug, Clone)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub struct Edge {
    pub rel_type: String,
    pub source: NodeId,
    pub target: NodeId,
    pub properties: HashMap<String, Value>,
}

impl Edge {
    pub fn new(rel_type: impl Into<String>, source: NodeId, target: NodeId) -> Self {
        Self {
            rel_type: rel_type.into(),
            source,
            target,
            properties: HashMap::new(),
        }
    }

    pub fn with_properties(mut self, props: Vec<(&str, Value)>) -> Self {
        for (k, v) in props {
            self.properties.insert(k.to_string(), v);
        }
        self
    }

    pub fn to_key(&self) -> String {
        format!(
            "{}:{}:{}",
            self.rel_type,
            self.source.to_key(),
            self.target.to_key()
        )
    }
}

/// Represents a path through the graph
#[derive(Debug, Clone)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub struct Path {
    pub nodes: Vec<NodeId>,
    pub edges: Vec<Edge>,
}

impl Path {
    pub fn new(nodes: Vec<NodeId>, edges: Vec<Edge>) -> Self {
        Self { nodes, edges }
    }

    /// Number of hops in the path
    pub fn length(&self) -> usize {
        self.edges.len()
    }

    /// Starting node
    pub fn start(&self) -> Option<&NodeId> {
        self.nodes.first()
    }

    /// Ending node
    pub fn end(&self) -> Option<&NodeId> {
        self.nodes.last()
    }
}

// =============================================================================
// Errors
// =============================================================================

#[derive(Error, Debug)]
pub enum GraphError {
    #[error("Node not found: :{0}:{1}")]
    NodeNotFound(String, String),

    #[error("Edge not found: {0} -> {1}")]
    EdgeNotFound(String, String),

    #[error("Duplicate node: :{0}:{1}")]
    DuplicateNode(String, String),

    #[error("Duplicate edge: {0}")]
    DuplicateEdge(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("{0}")]
    InvalidIdentifier(String),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, GraphError>;

// =============================================================================
// ISONGraph - Main Graph Structure
// =============================================================================

/// In-memory property graph store with ISON persistence.
///
/// Features:
/// - Property graph model (nodes and edges with properties)
/// - Multiple node types and relationship types
/// - O(1) node lookup by (type, id)
/// - Multi-hop traversal
/// - Shortest path finding (BFS)
/// - All paths finding (DFS)
/// - ISON/ISONL persistence
#[derive(Debug)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "serde", serde(try_from = "GraphData"))]
pub struct ISONGraph {
    /// Graph name
    pub name: String,

    /// Whether edges are directed
    pub directed: bool,

    /// Node storage: type -> id -> Node
    nodes: HashMap<String, HashMap<String, Node>>,

    /// Edge storage: rel_type -> Vec<Edge>
    edges: HashMap<String, Vec<Edge>>,

    /// Index: outgoing edges per node (node_key -> edges).
    /// Derived from `edges`; not serialized, rebuilt on deserialization.
    #[cfg_attr(feature = "serde", serde(skip))]
    out_edges: HashMap<String, Vec<Edge>>,

    /// Index: incoming edges per node (node_key -> edges).
    /// Derived from `edges`; not serialized, rebuilt on deserialization.
    #[cfg_attr(feature = "serde", serde(skip))]
    in_edges: HashMap<String, Vec<Edge>>,

    /// Edge uniqueness set.
    /// Derived from `edges`; not serialized, rebuilt on deserialization.
    #[cfg_attr(feature = "serde", serde(skip))]
    edge_set: HashSet<String>,
}

/// Serde shadow struct: the persisted form of [`ISONGraph`] without the
/// derived indexes. Indexes are rebuilt after deserialization.
#[cfg(feature = "serde")]
#[derive(Deserialize)]
struct GraphData {
    name: String,
    directed: bool,
    nodes: HashMap<String, HashMap<String, Node>>,
    edges: HashMap<String, Vec<Edge>>,
}

#[cfg(feature = "serde")]
impl TryFrom<GraphData> for ISONGraph {
    type Error = GraphError;

    /// Deserialization bypasses `add_node`/`add_edge` (it reconstructs the
    /// index maps directly from untrusted JSON), so the ':' / '|'
    /// identifier guard has to be re-applied here explicitly - otherwise a
    /// crafted or corrupted payload could smuggle in identifiers that
    /// `add_node`/`add_edge` would have rejected, and the graph would only
    /// fail later, confusingly, on to_ison()/to_isonl().
    fn try_from(data: GraphData) -> Result<Self> {
        for (node_type, type_nodes) in &data.nodes {
            ISONGraph::check_identifier("Node type", node_type)?;
            for node_id in type_nodes.keys() {
                ISONGraph::check_identifier("Node id", node_id)?;
            }
        }
        for (rel_type, edges) in &data.edges {
            ISONGraph::check_identifier("Relationship type", rel_type)?;
            for edge in edges {
                ISONGraph::check_identifier("Node type", &edge.source.node_type)?;
                ISONGraph::check_identifier("Node id", &edge.source.id)?;
                ISONGraph::check_identifier("Node type", &edge.target.node_type)?;
                ISONGraph::check_identifier("Node id", &edge.target.id)?;
            }
        }

        let mut graph = ISONGraph {
            name: data.name,
            directed: data.directed,
            nodes: data.nodes,
            edges: data.edges,
            out_edges: HashMap::new(),
            in_edges: HashMap::new(),
            edge_set: HashSet::new(),
        };
        graph.rebuild_indexes();
        Ok(graph)
    }
}

impl Default for ISONGraph {
    fn default() -> Self {
        Self::new("graph")
    }
}

impl ISONGraph {
    /// Create a new graph
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            directed: true,
            nodes: HashMap::new(),
            edges: HashMap::new(),
            out_edges: HashMap::new(),
            in_edges: HashMap::new(),
            edge_set: HashSet::new(),
        }
    }

    /// Create an undirected graph
    pub fn undirected(name: impl Into<String>) -> Self {
        let mut graph = Self::new(name);
        graph.directed = false;
        graph
    }

    /// Rebuild the derived indexes (`out_edges`, `in_edges`, `edge_set`)
    /// from the canonical `edges` storage.
    #[cfg(feature = "serde")]
    fn rebuild_indexes(&mut self) {
        self.out_edges.clear();
        self.in_edges.clear();
        self.edge_set.clear();

        for edges in self.edges.values() {
            for edge in edges {
                let edge_key = edge.to_key();
                if !self.edge_set.insert(edge_key) {
                    continue;
                }
                self.out_edges
                    .entry(edge.source.to_key())
                    .or_default()
                    .push(edge.clone());
                self.in_edges
                    .entry(edge.target.to_key())
                    .or_default()
                    .push(edge.clone());
            }
        }
    }

    // =========================================================================
    // Node Operations
    // =========================================================================

    /// Add a node to the graph.
    ///
    /// Node keys are formed as `type:id`, so neither the type nor the id may
    /// contain `':'` (it would make keys ambiguous).
    /// Reject ':' or '|' in a node type, node id, or relationship type. Both
    /// are structurally significant to the wire format (':' delimits
    /// `:type:id` references, '|' delimits ISONL columns); allowing them
    /// here would build a graph that fails on to_ison()/to_isonl()
    /// round-trip instead of at construction.
    fn check_identifier(kind: &str, value: &str) -> Result<()> {
        // Types become block names, which ISONL additionally cannot quote;
        // ids only have to survive a reference, which has no quoting at all.
        let is_type = kind.to_lowercase().contains("type");
        let bad = value.is_empty()
            || value.chars().any(|ch| {
                ch.is_whitespace()
                    || ch == ':'
                    || ch == '|'
                    || (is_type && (ch == '"' || ch == '\\'))
            });
        if bad {
            return Err(GraphError::InvalidIdentifier(format!(
                "{} {:?} is not representable: it must not be empty or contain \
                 whitespace, ':' or '|'{}",
                kind,
                value,
                if is_type { ", '\"' or '\\'" } else { "" }
            )));
        }
        Ok(())
    }

    /// Reject property names that cannot survive a serialization round trip.
    ///
    /// Property names become ISON field names, and the format quotes values
    /// but not names: a space splits the field in two, ':' has the remainder
    /// eaten as a type annotation, '.' is a dot path, and a leading '#' turns
    /// the header into a comment and loses the whole block.
    fn check_property_names<'a, I>(kind: &str, names: I) -> Result<()>
    where
        I: IntoIterator<Item = &'a str>,
    {
        for name in names {
            let bad = name.is_empty()
                || name.starts_with('#')
                || name.chars().any(|ch| {
                    ch.is_whitespace()
                        || ch == ':'
                        || ch == '|'
                        || ch == '"'
                        || ch == '\\'
                        || ch == '.'
                });
            if bad {
                return Err(GraphError::InvalidIdentifier(format!(
                    "{} name {:?} cannot be encoded: property names must not be \
                     empty, start with '#', or contain whitespace, ':', '|', \
                     '\"', '\\' or '.'",
                    kind, name
                )));
            }
        }
        Ok(())
    }

    pub fn add_node(
        &mut self,
        node_type: &str,
        node_id: &str,
        properties: Vec<(&str, Value)>,
    ) -> Result<&Node> {
        Self::check_identifier("Node type", node_type)?;
        Self::check_identifier("Node id", node_id)?;
        Self::check_property_names("Node property", properties.iter().map(|(k, _)| *k))?;

        let type_nodes = self.nodes.entry(node_type.to_string()).or_default();

        if type_nodes.contains_key(node_id) {
            return Err(GraphError::DuplicateNode(
                node_type.to_string(),
                node_id.to_string(),
            ));
        }

        let node = Node::new(node_type, node_id).with_properties(properties);
        type_nodes.insert(node_id.to_string(), node);
        Ok(type_nodes.get(node_id).unwrap())
    }

    /// Get a node by type and ID
    pub fn get_node(&self, node_type: &str, node_id: &str) -> Result<&Node> {
        self.nodes
            .get(node_type)
            .and_then(|m| m.get(node_id))
            .ok_or_else(|| GraphError::NodeNotFound(node_type.to_string(), node_id.to_string()))
    }

    /// Get a node by NodeId
    pub fn get_node_by_id(&self, node_id: &NodeId) -> Result<&Node> {
        self.get_node(&node_id.node_type, &node_id.id)
    }

    /// Check if node exists
    pub fn has_node(&self, node_type: &str, node_id: &str) -> bool {
        self.nodes
            .get(node_type)
            .map(|m| m.contains_key(node_id))
            .unwrap_or(false)
    }

    /// Remove a node and all its edges
    pub fn remove_node(&mut self, node_type: &str, node_id: &str) -> Result<()> {
        if !self.has_node(node_type, node_id) {
            return Err(GraphError::NodeNotFound(
                node_type.to_string(),
                node_id.to_string(),
            ));
        }

        let node_key = format!("{}:{}", node_type, node_id);

        // Collect edges to remove
        let out_edges: Vec<Edge> = self.out_edges.get(&node_key).cloned().unwrap_or_default();
        let in_edges: Vec<Edge> = self.in_edges.get(&node_key).cloned().unwrap_or_default();

        for edge in out_edges.iter().chain(in_edges.iter()) {
            self.remove_edge_internal(edge);
        }

        // Remove node
        if let Some(type_nodes) = self.nodes.get_mut(node_type) {
            type_nodes.remove(node_id);
            if type_nodes.is_empty() {
                self.nodes.remove(node_type);
            }
        }

        Ok(())
    }

    /// Update node properties
    pub fn update_node(
        &mut self,
        node_type: &str,
        node_id: &str,
        properties: Vec<(&str, Value)>,
    ) -> Result<()> {
        let node = self
            .nodes
            .get_mut(node_type)
            .and_then(|m| m.get_mut(node_id))
            .ok_or_else(|| GraphError::NodeNotFound(node_type.to_string(), node_id.to_string()))?;

        for (k, v) in properties {
            node.properties.insert(k.to_string(), v);
        }
        Ok(())
    }

    /// Iterate over all nodes
    pub fn nodes(&self) -> impl Iterator<Item = &Node> {
        self.nodes.values().flat_map(|m| m.values())
    }

    /// Iterate over nodes of a specific type
    pub fn nodes_of_type(&self, node_type: &str) -> impl Iterator<Item = &Node> {
        self.nodes
            .get(node_type)
            .into_iter()
            .flat_map(|m| m.values())
    }

    /// Count all nodes
    pub fn node_count(&self) -> usize {
        self.nodes.values().map(|m| m.len()).sum()
    }

    /// Count nodes of a specific type
    pub fn node_count_of_type(&self, node_type: &str) -> usize {
        self.nodes.get(node_type).map(|m| m.len()).unwrap_or(0)
    }

    /// Get all node types
    pub fn node_types(&self) -> Vec<&String> {
        self.nodes.keys().collect()
    }

    // =========================================================================
    // Edge Operations
    // =========================================================================

    /// Add an edge to the graph
    pub fn add_edge(
        &mut self,
        rel_type: &str,
        source: (&str, &str),
        target: (&str, &str),
        properties: Vec<(&str, Value)>,
    ) -> Result<()> {
        Self::check_identifier("Relationship type", rel_type)?;
        Self::check_property_names("Edge property", properties.iter().map(|(k, _)| *k))?;

        // Validate nodes exist
        if !self.has_node(source.0, source.1) {
            return Err(GraphError::NodeNotFound(
                source.0.to_string(),
                source.1.to_string(),
            ));
        }
        if !self.has_node(target.0, target.1) {
            return Err(GraphError::NodeNotFound(
                target.0.to_string(),
                target.1.to_string(),
            ));
        }

        let source_id = NodeId::new(source.0, source.1);
        let target_id = NodeId::new(target.0, target.1);
        let edge = Edge::new(rel_type, source_id.clone(), target_id.clone()).with_properties(properties.clone());
        let edge_key = edge.to_key();

        if self.edge_set.contains(&edge_key) {
            return Err(GraphError::DuplicateEdge(edge_key));
        }

        // Add to storage
        self.edges
            .entry(rel_type.to_string())
            .or_default()
            .push(edge.clone());

        let source_key = source_id.to_key();
        let target_key = target_id.to_key();

        self.out_edges
            .entry(source_key.clone())
            .or_default()
            .push(edge.clone());
        self.in_edges
            .entry(target_key.clone())
            .or_default()
            .push(edge.clone());

        self.edge_set.insert(edge_key);

        // For undirected graphs, add reverse edge
        if !self.directed {
            let reverse_edge = Edge::new(rel_type, target_id.clone(), source_id.clone())
                .with_properties(properties);
            let reverse_key = reverse_edge.to_key();

            if !self.edge_set.contains(&reverse_key) {
                self.edges
                    .entry(rel_type.to_string())
                    .or_default()
                    .push(reverse_edge.clone());
                self.out_edges
                    .entry(target_key)
                    .or_default()
                    .push(reverse_edge.clone());
                self.in_edges
                    .entry(source_key)
                    .or_default()
                    .push(reverse_edge);
                self.edge_set.insert(reverse_key);
            }
        }

        Ok(())
    }

    fn remove_edge_internal(&mut self, edge: &Edge) {
        let edge_key = edge.to_key();
        if !self.edge_set.contains(&edge_key) {
            return;
        }

        self.edge_set.remove(&edge_key);

        // Remove from edges
        if let Some(rel_edges) = self.edges.get_mut(&edge.rel_type) {
            rel_edges.retain(|e| e.to_key() != edge_key);
        }

        // Remove from out_edges
        let source_key = edge.source.to_key();
        if let Some(out) = self.out_edges.get_mut(&source_key) {
            out.retain(|e| e.to_key() != edge_key);
        }

        // Remove from in_edges
        let target_key = edge.target.to_key();
        if let Some(in_e) = self.in_edges.get_mut(&target_key) {
            in_e.retain(|e| e.to_key() != edge_key);
        }
    }

    /// Remove an edge
    pub fn remove_edge(
        &mut self,
        rel_type: &str,
        source: (&str, &str),
        target: (&str, &str),
    ) -> Result<()> {
        let source_id = NodeId::new(source.0, source.1);
        let target_id = NodeId::new(target.0, target.1);
        let edge = Edge::new(rel_type, source_id, target_id);
        let edge_key = edge.to_key();

        if !self.edge_set.contains(&edge_key) {
            return Err(GraphError::EdgeNotFound(
                format!("{}:{}", source.0, source.1),
                format!("{}:{}", target.0, target.1),
            ));
        }

        self.remove_edge_internal(&edge);
        Ok(())
    }

    /// Check if edge exists
    pub fn has_edge(&self, rel_type: &str, source: (&str, &str), target: (&str, &str)) -> bool {
        let source_id = NodeId::new(source.0, source.1);
        let target_id = NodeId::new(target.0, target.1);
        let edge = Edge::new(rel_type, source_id, target_id);
        self.edge_set.contains(&edge.to_key())
    }

    /// Count all edges
    pub fn edge_count(&self) -> usize {
        self.edge_set.len()
    }

    /// Count edges of a specific type
    pub fn edge_count_of_type(&self, rel_type: &str) -> usize {
        self.edges.get(rel_type).map(|v| v.len()).unwrap_or(0)
    }

    /// Get all edge types
    pub fn edge_types(&self) -> Vec<&String> {
        self.edges.keys().collect()
    }

    /// Get all edges of a specific type
    pub fn edges_of_type(&self, rel_type: &str) -> impl Iterator<Item = &Edge> {
        self.edges.get(rel_type).into_iter().flatten()
    }

    /// Check if the graph has a cycle for edges of a specific type
    pub fn has_cycle(&self, rel_type: Option<&str>) -> bool {
        // Iterative DFS-based cycle detection
        let mut visited = HashSet::new();

        for node_types in self.nodes.values() {
            for node in node_types.values() {
                let node_key = format!("{}:{}", node.node_type, node.id);
                if !visited.contains(&node_key)
                    && self.has_cycle_from(&node_key, &mut visited, rel_type)
                {
                    return true;
                }
            }
        }
        false
    }

    /// Outgoing `(target_key, rel_type)` pairs for cycle detection.
    ///
    /// For undirected graphs, the single auto-reverse of the edge used to
    /// enter this node (`skip`) is excluded, so a lone undirected edge does
    /// not read as a cycle. Only one matching reverse edge is skipped:
    /// a genuine parallel edge back to the parent still counts.
    fn cycle_successors(
        &self,
        node_key: &str,
        rel_type: Option<&str>,
        skip: Option<(&str, &str)>,
    ) -> Vec<(String, String)> {
        let mut result = Vec::new();
        let mut skip_remaining = if self.directed { None } else { skip };

        if let Some(edges) = self.out_edges.get(node_key) {
            for edge in edges {
                if rel_type.is_some() && rel_type != Some(edge.rel_type.as_str()) {
                    continue;
                }
                let target_key = edge.target.to_key();
                if let Some((skip_rel, skip_key)) = skip_remaining {
                    if edge.rel_type == skip_rel && target_key == skip_key {
                        skip_remaining = None;
                        continue;
                    }
                }
                result.push((target_key, edge.rel_type.clone()));
            }
        }
        result
    }

    fn has_cycle_from(
        &self,
        start_key: &str,
        visited: &mut HashSet<String>,
        rel_type: Option<&str>,
    ) -> bool {
        struct Frame {
            key: String,
            successors: Vec<(String, String)>,
            idx: usize,
        }

        let mut rec_stack: HashSet<String> = HashSet::new();
        visited.insert(start_key.to_string());
        rec_stack.insert(start_key.to_string());

        let mut stack = vec![Frame {
            key: start_key.to_string(),
            successors: self.cycle_successors(start_key, rel_type, None),
            idx: 0,
        }];

        while !stack.is_empty() {
            let next = {
                let frame = stack.last_mut().unwrap();
                if frame.idx < frame.successors.len() {
                    let (target_key, edge_rel) = frame.successors[frame.idx].clone();
                    frame.idx += 1;
                    Some((target_key, edge_rel, frame.key.clone()))
                } else {
                    None
                }
            };

            match next {
                Some((target_key, edge_rel, from_key)) => {
                    if !visited.contains(&target_key) {
                        visited.insert(target_key.clone());
                        rec_stack.insert(target_key.clone());
                        let successors =
                            self.cycle_successors(&target_key, rel_type, Some((&edge_rel, &from_key)));
                        stack.push(Frame {
                            key: target_key,
                            successors,
                            idx: 0,
                        });
                    } else if rec_stack.contains(&target_key) {
                        return true;
                    }
                }
                None => {
                    let frame = stack.pop().unwrap();
                    rec_stack.remove(&frame.key);
                }
            }
        }

        false
    }

    // =========================================================================
    // Traversal Operations
    // =========================================================================

    /// Get neighboring nodes.
    ///
    /// Results are deduplicated while preserving first-occurrence order:
    /// a node connected through multiple edges (e.g. the forward and
    /// auto-reverse edges of an undirected graph with `Direction::Both`)
    /// appears only once.
    pub fn neighbors(
        &self,
        node_ref: &NodeRef,
        rel_type: Option<&str>,
        direction: Direction,
    ) -> Vec<NodeId> {
        let mut neighbors = Vec::new();
        let mut seen: HashSet<String> = HashSet::new();
        let node_key = format!("{}:{}", node_ref.0, node_ref.1);

        if direction == Direction::Out || direction == Direction::Both {
            if let Some(edges) = self.out_edges.get(&node_key) {
                for edge in edges {
                    if (rel_type.is_none() || rel_type == Some(&edge.rel_type))
                        && seen.insert(edge.target.to_key())
                    {
                        neighbors.push(edge.target.clone());
                    }
                }
            }
        }

        if direction == Direction::In || direction == Direction::Both {
            if let Some(edges) = self.in_edges.get(&node_key) {
                for edge in edges {
                    if (rel_type.is_none() || rel_type == Some(&edge.rel_type))
                        && seen.insert(edge.source.to_key())
                    {
                        neighbors.push(edge.source.clone());
                    }
                }
            }
        }

        neighbors
    }

    /// Get nodes N hops away
    pub fn multi_hop(
        &self,
        start: &NodeRef,
        rel_type: Option<&str>,
        hops: usize,
        direction: Direction,
    ) -> Vec<NodeId> {
        if hops == 0 {
            return vec![NodeId::new(start.0, start.1)];
        }

        let start_key = format!("{}:{}", start.0, start.1);
        let mut current: HashSet<String> = HashSet::new();
        current.insert(start_key.clone());

        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start_key);

        let mut ref_map: HashMap<String, NodeId> = HashMap::new();
        ref_map.insert(
            format!("{}:{}", start.0, start.1),
            NodeId::new(start.0, start.1),
        );

        for _ in 0..hops {
            let mut next_level: HashSet<String> = HashSet::new();

            for key in &current {
                if let Some(node_id) = ref_map.get(key) {
                    let neighbors = self.neighbors(&node_id.as_ref(), rel_type, direction);
                    for neighbor in neighbors {
                        let neighbor_key = neighbor.to_key();
                        if !visited.contains(&neighbor_key) {
                            next_level.insert(neighbor_key.clone());
                            ref_map.insert(neighbor_key.clone(), neighbor);
                        }
                    }
                }
            }

            for key in &next_level {
                visited.insert(key.clone());
            }
            current = next_level;
        }

        current
            .iter()
            .filter_map(|key| ref_map.get(key).cloned())
            .collect()
    }

    /// Get nodes within a range of hops
    pub fn multi_hop_range(
        &self,
        start: &NodeRef,
        rel_type: Option<&str>,
        min_hops: usize,
        max_hops: usize,
        direction: Direction,
    ) -> Vec<NodeId> {
        let start_key = format!("{}:{}", start.0, start.1);
        let mut result: HashSet<String> = HashSet::new();
        let mut current: HashSet<String> = HashSet::new();
        current.insert(start_key.clone());

        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start_key);

        let mut ref_map: HashMap<String, NodeId> = HashMap::new();
        ref_map.insert(
            format!("{}:{}", start.0, start.1),
            NodeId::new(start.0, start.1),
        );

        for hop in 1..=max_hops {
            let mut next_level: HashSet<String> = HashSet::new();

            for key in &current {
                if let Some(node_id) = ref_map.get(key) {
                    let neighbors = self.neighbors(&node_id.as_ref(), rel_type, direction);
                    for neighbor in neighbors {
                        let neighbor_key = neighbor.to_key();
                        if !visited.contains(&neighbor_key) {
                            next_level.insert(neighbor_key.clone());
                            ref_map.insert(neighbor_key.clone(), neighbor);
                            if hop >= min_hops {
                                result.insert(neighbor_key);
                            }
                        }
                    }
                }
            }

            for key in &next_level {
                visited.insert(key.clone());
            }
            current = next_level;

            if current.is_empty() {
                break;
            }
        }

        result
            .iter()
            .filter_map(|key| ref_map.get(key).cloned())
            .collect()
    }

    // =========================================================================
    // Path Finding
    // =========================================================================

    /// Find shortest path between two nodes using BFS
    pub fn shortest_path(
        &self,
        start: &NodeRef,
        end: &NodeRef,
        rel_type: Option<&str>,
        max_hops: usize,
        direction: Direction,
    ) -> Option<Path> {
        let start_id = NodeId::new(start.0, start.1);
        let end_id = NodeId::new(end.0, end.1);

        if start_id == end_id {
            return Some(Path::new(vec![start_id], vec![]));
        }

        let end_key = end_id.to_key();
        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start_id.to_key());

        let mut queue: VecDeque<(NodeId, Vec<NodeId>, Vec<Edge>)> = VecDeque::new();
        queue.push_back((start_id.clone(), vec![start_id], vec![]));

        while let Some((current, path_nodes, path_edges)) = queue.pop_front() {
            if path_nodes.len() > max_hops.saturating_add(1) {
                continue;
            }

            let current_key = current.to_key();

            if direction != Direction::In {
                if let Some(edges) = self.out_edges.get(&current_key) {
                    for edge in edges {
                        if rel_type.is_some() && rel_type != Some(&edge.rel_type) {
                            continue;
                        }

                        let target_key = edge.target.to_key();
                        if target_key == end_key {
                            let mut nodes = path_nodes.clone();
                            nodes.push(edge.target.clone());
                            let mut edges = path_edges.clone();
                            edges.push(edge.clone());
                            return Some(Path::new(nodes, edges));
                        }

                        if !visited.contains(&target_key) {
                            visited.insert(target_key);
                            let mut nodes = path_nodes.clone();
                            nodes.push(edge.target.clone());
                            let mut edges = path_edges.clone();
                            edges.push(edge.clone());
                            queue.push_back((edge.target.clone(), nodes, edges));
                        }
                    }
                }
            }

            if direction == Direction::In || direction == Direction::Both {
                if let Some(edges) = self.in_edges.get(&current_key) {
                    for edge in edges {
                        if rel_type.is_some() && rel_type != Some(&edge.rel_type) {
                            continue;
                        }

                        let source_key = edge.source.to_key();
                        if source_key == end_key {
                            let mut nodes = path_nodes.clone();
                            nodes.push(edge.source.clone());
                            let mut edges = path_edges.clone();
                            edges.push(edge.clone());
                            return Some(Path::new(nodes, edges));
                        }

                        if !visited.contains(&source_key) {
                            visited.insert(source_key);
                            let mut nodes = path_nodes.clone();
                            nodes.push(edge.source.clone());
                            let mut edges = path_edges.clone();
                            edges.push(edge.clone());
                            queue.push_back((edge.source.clone(), nodes, edges));
                        }
                    }
                }
            }
        }

        None
    }

    /// Check if a path exists between two nodes in the given direction
    pub fn path_exists(
        &self,
        start: &NodeRef,
        end: &NodeRef,
        rel_type: Option<&str>,
        max_hops: usize,
        direction: Direction,
    ) -> bool {
        self.shortest_path(start, end, rel_type, max_hops, direction)
            .is_some()
    }

    // =========================================================================
    // Graph Analysis
    // =========================================================================

    /// Count incoming edges for a node
    pub fn in_degree(&self, node_ref: &NodeRef) -> usize {
        let key = format!("{}:{}", node_ref.0, node_ref.1);
        self.in_edges.get(&key).map(|v| v.len()).unwrap_or(0)
    }

    /// Count outgoing edges for a node
    pub fn out_degree(&self, node_ref: &NodeRef) -> usize {
        let key = format!("{}:{}", node_ref.0, node_ref.1);
        self.out_edges.get(&key).map(|v| v.len()).unwrap_or(0)
    }

    /// Total degree for a node
    pub fn degree(&self, node_ref: &NodeRef) -> usize {
        self.in_degree(node_ref) + self.out_degree(node_ref)
    }

    /// Check if graph is connected
    pub fn is_connected(&self) -> bool {
        let all_nodes: Vec<_> = self.nodes().collect();
        if all_nodes.is_empty() {
            return true;
        }

        let start = &all_nodes[0];
        let start_key = start.to_key();
        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start_key.clone());

        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(start_key);

        while let Some(current_key) = queue.pop_front() {
            // Get node from key
            let parts: Vec<&str> = current_key.split(':').collect();
            if parts.len() == 2 {
                let neighbors = self.neighbors(&(parts[0], parts[1]), None, Direction::Both);
                for neighbor in neighbors {
                    let neighbor_key = neighbor.to_key();
                    if !visited.contains(&neighbor_key) {
                        visited.insert(neighbor_key.clone());
                        queue.push_back(neighbor_key);
                    }
                }
            }
        }

        visited.len() == all_nodes.len()
    }

    // =========================================================================
    // Serialization
    // =========================================================================

    /// Serialize graph to ISON format.
    ///
    /// Serialization is canonical: node type blocks, node rows within a
    /// block, edge type blocks, and edge rows within a block are all sorted
    /// (ordinal string comparison), independent of insertion order. The
    /// same logical graph always serializes to the same bytes, regardless
    /// of construction history.
    /// Build the ISON Document this graph serializes to.
    ///
    /// ISONGraph decides *what* to emit - which blocks, which rows, which
    /// columns - and hands every byte-level decision to ison-rs's canonical
    /// writer: quoting, escaping, delimiters, column layout, and the final
    /// block and row order.
    ///
    /// This used to be hand-rolled here, which meant ISON syntax had two
    /// implementations per language that had to agree forever. They did not:
    /// the id column was written unquoted, so a node id containing a space
    /// produced output that would not reparse.
    fn document(&self) -> IsonDocument {
        let mut doc = IsonDocument::new();

        let mut node_types: Vec<_> = self.nodes.keys().collect();
        node_types.sort();
        for node_type in node_types {
            let type_nodes = &self.nodes[node_type];
            if type_nodes.is_empty() {
                continue;
            }

            let mut prop_keys: Vec<&String> = type_nodes
                .values()
                .flat_map(|n| n.properties.keys())
                .collect::<HashSet<_>>()
                .into_iter()
                .collect();
            prop_keys.sort();

            let mut block = IsonBlock::new("nodes", node_type.as_str());
            block.fields = std::iter::once("id".to_string())
                .chain(prop_keys.iter().map(|k| (*k).clone()))
                .collect();

            for node in type_nodes.values() {
                let mut row: HashMap<String, IsonValue> = HashMap::new();
                row.insert("id".to_string(), IsonValue::String(node.id.clone()));
                for key in &prop_keys {
                    let value = match node.properties.get(*key) {
                        Some(v) => v.clone(),
                        None => IsonValue::Null,
                    };
                    row.insert((*key).clone(), value);
                }
                block.rows.push(row);
            }
            doc.blocks.push(block);
        }

        let mut edge_types: Vec<_> = self.edges.keys().collect();
        edge_types.sort();
        for rel_type in edge_types {
            let edges = &self.edges[rel_type];
            if edges.is_empty() {
                continue;
            }

            let mut prop_keys: Vec<&String> = edges
                .iter()
                .flat_map(|e| e.properties.keys())
                .collect::<HashSet<_>>()
                .into_iter()
                .collect();
            prop_keys.sort();

            let mut block = IsonBlock::new("edges", rel_type.as_str());
            block.fields = ["source".to_string(), "target".to_string()]
                .into_iter()
                .chain(prop_keys.iter().map(|k| (*k).clone()))
                .collect();

            for edge in edges {
                let mut row: HashMap<String, IsonValue> = HashMap::new();
                row.insert(
                    "source".to_string(),
                    IsonValue::Reference(IsonReference::with_type(
                        edge.source.id.clone(),
                        edge.source.node_type.clone(),
                    )),
                );
                row.insert(
                    "target".to_string(),
                    IsonValue::Reference(IsonReference::with_type(
                        edge.target.id.clone(),
                        edge.target.node_type.clone(),
                    )),
                );
                for key in &prop_keys {
                    let value = match edge.properties.get(*key) {
                        Some(v) => v.clone(),
                        None => IsonValue::Null,
                    };
                    row.insert((*key).clone(), value);
                }
                block.rows.push(row);
            }
            doc.blocks.push(block);
        }

        doc
    }

    /// Serialize graph to canonical ISON (ISONCS).
    ///
    /// Output is canonical: the same logical graph always serializes to the
    /// same bytes regardless of construction order. Block, row and column
    /// order are the canonical writer's, not ISONGraph's.
    pub fn to_ison(&self) -> String {
        dumps_canonical(&self.document()).unwrap_or_default()
    }

    /// Serialize graph to canonical ISONL. Row order matches [`to_ison`].
    pub fn to_isonl(&self) -> String {
        dumps_canonical_isonl(&self.document()).unwrap_or_default()
    }


    /// Node ids are identifiers rather than values, so they are always text.
    /// Property values keep whatever type the parser produced.
    fn id_text(value: &IsonValue) -> Option<String> {
        match value {
            IsonValue::Null => None,
            IsonValue::Bool(b) => Some(b.to_string()),
            IsonValue::Int(i) => Some(i.to_string()),
            IsonValue::Float(f) => Some(f.to_string()),
            IsonValue::String(s) => Some(s.clone()),
            IsonValue::Reference(r) => Some(r.to_ison()),
        }
    }

    fn build_from_document(doc: &IsonDocument, name: &str) -> Result<Self> {
        let mut graph = ISONGraph::new(name);

        for block in &doc.blocks {
            if block.kind != "nodes" && block.kind != "edges" {
                return Err(GraphError::ParseError(format!(
                    "unknown block kind {:?} (expected 'nodes' or 'edges')",
                    block.kind
                )));
            }
        }

        // Nodes first regardless of block order - the canonical writer sorts
        // blocks by name, which puts 'edges' ahead of 'nodes'.
        for block in &doc.blocks {
            if block.kind != "nodes" {
                continue;
            }
            for row in &block.rows {
                // The id is an identifier, not a property, so it stays text;
                // everything else keeps the type the parser gave it.
                let id = row
                    .get("id")
                    .and_then(Self::id_text)
                    .ok_or_else(|| GraphError::ParseError("row has no id".into()))?;
                let props: Vec<(String, Value)> = row
                    .iter()
                    .filter(|(k, _)| k.as_str() != "id")
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                let borrowed: Vec<(&str, Value)> =
                    props.iter().map(|(k, v)| (k.as_str(), v.clone())).collect();
                graph.add_node(&block.name, &id, borrowed)?;
            }
        }

        for block in &doc.blocks {
            if block.kind != "edges" {
                continue;
            }
            for row in &block.rows {
                let (source, target) = match (row.get("source"), row.get("target")) {
                    (Some(IsonValue::Reference(s)), Some(IsonValue::Reference(t))) => (
                        (s.ref_type.clone().unwrap_or_default(), s.id.clone()),
                        (t.ref_type.clone().unwrap_or_default(), t.id.clone()),
                    ),
                    _ => {
                        return Err(GraphError::ParseError(
                            "edge row is missing a source or target reference".into(),
                        ))
                    }
                };
                let props: Vec<(String, Value)> = row
                    .iter()
                    .filter(|(k, _)| k.as_str() != "source" && k.as_str() != "target")
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                let borrowed: Vec<(&str, Value)> =
                    props.iter().map(|(k, v)| (k.as_str(), v.clone())).collect();
                graph.add_edge(
                    &block.name,
                    (&source.0, &source.1),
                    (&target.0, &target.1),
                    borrowed,
                )?;
            }
        }

        Ok(graph)
    }

    /// Parse a graph from ISON.
    pub fn from_ison(text: &str, name: Option<&str>) -> Result<Self> {
        let doc = loads(text)
            .map_err(|e| GraphError::ParseError(format!("{}", e)))?;
        Self::build_from_document(&doc, name.unwrap_or("graph"))
    }

    /// Parse a graph from ISONL.
    pub fn from_isonl(text: &str, name: Option<&str>) -> Result<Self> {
        let doc = loads_isonl(text)
            .map_err(|e| GraphError::ParseError(format!("{}", e)))?;
        Self::build_from_document(&doc, name.unwrap_or("graph"))
    }

    pub fn save<P: AsRef<StdPath>>(&self, path: P, format: Option<&str>) -> Result<()> {
        let path = path.as_ref();
        let actual_format = format.unwrap_or_else(|| {
            if path.extension().map(|e| e == "isonl").unwrap_or(false) {
                "isonl"
            } else {
                "ison"
            }
        });

        let content = if actual_format == "isonl" {
            self.to_isonl()
        } else {
            self.to_ison()
        };

        fs::write(path, content).map_err(GraphError::Io)
    }

    /// Load graph from file
    pub fn load<P: AsRef<StdPath>>(path: P, format: Option<&str>) -> Result<Self> {
        let path = path.as_ref();
        let content = fs::read_to_string(path).map_err(GraphError::Io)?;

        let actual_format = format.unwrap_or_else(|| {
            if path.extension().map(|e| e == "isonl").unwrap_or(false) {
                "isonl"
            } else {
                "ison"
            }
        });

        let graph_name = path.file_stem().and_then(|s| s.to_str()).unwrap_or("graph");

        if actual_format == "isonl" {
            Self::from_isonl(&content, Some(graph_name))
        } else {
            Self::from_ison(&content, Some(graph_name))
        }
    }

    // =========================================================================
    // Additional Edge Operations
    // =========================================================================

    /// Get an edge by its components
    pub fn get_edge(&self, rel_type: &str, source: (&str, &str), target: (&str, &str)) -> Result<&Edge> {
        let source_id = NodeId::new(source.0, source.1);
        let target_id = NodeId::new(target.0, target.1);

        if let Some(edges) = self.edges.get(rel_type) {
            for edge in edges {
                if edge.source == source_id && edge.target == target_id {
                    return Ok(edge);
                }
            }
        }

        Err(GraphError::EdgeNotFound(
            format!("{}:{}", source.0, source.1),
            format!("{}:{}", target.0, target.1),
        ))
    }

    // =========================================================================
    // Additional Graph Analysis
    // =========================================================================

    /// Get all connected components
    pub fn connected_components(&self) -> Vec<HashSet<NodeId>> {
        let mut visited: HashSet<String> = HashSet::new();
        let mut components: Vec<HashSet<NodeId>> = Vec::new();

        for node in self.nodes() {
            let node_key = node.to_key();
            if !visited.contains(&node_key) {
                let mut component: HashSet<NodeId> = HashSet::new();
                let mut queue: VecDeque<NodeId> = VecDeque::new();
                queue.push_back(node.node_id());

                while let Some(current) = queue.pop_front() {
                    let current_key = current.to_key();
                    if visited.contains(&current_key) {
                        continue;
                    }
                    visited.insert(current_key);
                    component.insert(current.clone());

                    // Get neighbors in both directions
                    let neighbors = self.neighbors(&current.as_ref(), None, Direction::Both);
                    for neighbor in neighbors {
                        if !visited.contains(&neighbor.to_key()) {
                            queue.push_back(neighbor);
                        }
                    }
                }

                components.push(component);
            }
        }

        components
    }

    /// Edges to follow from a node for path enumeration
    fn edges_to_follow(
        &self,
        node: &NodeId,
        rel_type: Option<&str>,
        direction: Direction,
    ) -> Vec<(Edge, NodeId)> {
        let node_key = node.to_key();
        let mut edges_to_follow: Vec<(Edge, NodeId)> = Vec::new();

        if direction == Direction::Out || direction == Direction::Both {
            if let Some(out_edges) = self.out_edges.get(&node_key) {
                for edge in out_edges {
                    if rel_type.is_none() || rel_type == Some(&edge.rel_type) {
                        edges_to_follow.push((edge.clone(), edge.target.clone()));
                    }
                }
            }
        }

        if direction == Direction::In || direction == Direction::Both {
            if let Some(in_edges) = self.in_edges.get(&node_key) {
                for edge in in_edges {
                    if rel_type.is_none() || rel_type == Some(&edge.rel_type) {
                        edges_to_follow.push((edge.clone(), edge.source.clone()));
                    }
                }
            }
        }

        edges_to_follow
    }

    /// Find all paths between two nodes using iterative DFS
    pub fn all_paths(
        &self,
        start: &NodeRef,
        end: &NodeRef,
        rel_type: Option<&str>,
        max_hops: usize,
        direction: Direction,
    ) -> Vec<Path> {
        let start_id = NodeId::new(start.0, start.1);
        let end_id = NodeId::new(end.0, end.1);
        let mut paths: Vec<Path> = Vec::new();

        let mut visited: HashSet<String> = HashSet::new();
        visited.insert(start_id.to_key());
        let mut path_nodes = vec![start_id.clone()];
        let mut path_edges: Vec<Edge> = Vec::new();

        if start_id == end_id {
            paths.push(Path::new(path_nodes, path_edges));
            return paths;
        }

        struct Frame {
            options: Vec<(Edge, NodeId)>,
            idx: usize,
        }

        let mut stack = vec![Frame {
            options: self.edges_to_follow(&start_id, rel_type, direction),
            idx: 0,
        }];

        while !stack.is_empty() {
            let next = {
                let frame = stack.last_mut().unwrap();
                if frame.idx < frame.options.len() {
                    let option = frame.options[frame.idx].clone();
                    frame.idx += 1;
                    Some(option)
                } else {
                    None
                }
            };

            match next {
                Some((edge, next_node)) => {
                    let next_key = next_node.to_key();
                    if visited.contains(&next_key) {
                        continue;
                    }

                    visited.insert(next_key.clone());
                    path_nodes.push(next_node.clone());
                    path_edges.push(edge);

                    if path_nodes.len() > max_hops.saturating_add(1) {
                        // Too deep: backtrack immediately
                        path_nodes.pop();
                        path_edges.pop();
                        visited.remove(&next_key);
                        continue;
                    }

                    if next_node == end_id {
                        paths.push(Path::new(path_nodes.clone(), path_edges.clone()));
                        path_nodes.pop();
                        path_edges.pop();
                        visited.remove(&next_key);
                        continue;
                    }

                    stack.push(Frame {
                        options: self.edges_to_follow(&next_node, rel_type, direction),
                        idx: 0,
                    });
                }
                None => {
                    stack.pop();
                    // Backtrack the path entry owned by the popped frame
                    // (the root frame owns the start node, which stays).
                    if !stack.is_empty() {
                        if let Some(popped) = path_nodes.pop() {
                            path_edges.pop();
                            visited.remove(&popped.to_key());
                        }
                    }
                }
            }
        }

        paths
    }

    // =========================================================================
    // Pattern-based Traversal
    // =========================================================================

    /// Traverse graph following a pattern of relationship types
    pub fn traverse(
        &self,
        start: &NodeRef,
        pattern: &[(String, Direction)],
        filter_fn: Option<&dyn Fn(&Node) -> bool>,
    ) -> Vec<NodeId> {
        let start_id = NodeId::new(start.0, start.1);
        let mut current: HashSet<String> = HashSet::new();
        current.insert(start_id.to_key());

        let mut ref_map: HashMap<String, NodeId> = HashMap::new();
        ref_map.insert(start_id.to_key(), start_id);

        for (rel_type, direction) in pattern {
            let mut next_level: HashSet<String> = HashSet::new();

            for key in &current {
                if let Some(node_id) = ref_map.get(key) {
                    let neighbors = self.neighbors(&node_id.as_ref(), Some(rel_type), *direction);
                    for neighbor in neighbors {
                        let neighbor_key = neighbor.to_key();

                        let should_include = match filter_fn {
                            None => true,
                            Some(f) => {
                                if let Ok(node) = self.get_node_by_id(&neighbor) {
                                    f(node)
                                } else {
                                    false
                                }
                            }
                        };

                        if should_include {
                            next_level.insert(neighbor_key.clone());
                            ref_map.insert(neighbor_key, neighbor);
                        }
                    }
                }
            }

            current = next_level;
            if current.is_empty() {
                break;
            }
        }

        current
            .iter()
            .filter_map(|key| ref_map.get(key).cloned())
            .collect()
    }

    // =========================================================================
    // Query Pattern Syntax
    // =========================================================================

    /// Execute a simple pattern query
    ///
    /// Pattern syntax:
    ///   :type:id -[:REL]-> *           (single hop)
    ///   :type:id -[:REL*N]-> *         (N hops)
    ///   :type:id -[:REL*1..3]-> *      (1-3 hops range)
    pub fn query(&self, pattern: &str) -> Result<Vec<NodeId>> {
        static HOP_REGEX: OnceLock<Regex> = OnceLock::new();
        static RANGE_REGEX: OnceLock<Regex> = OnceLock::new();
        static SIMPLE_REGEX: OnceLock<Regex> = OnceLock::new();

        let p = pattern.trim();

        // Match: :type:id -[:REL*N]-> *
        let hop_regex = HOP_REGEX.get_or_init(|| {
            Regex::new(r"^:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*$").unwrap()
        });
        if let Some(caps) = hop_regex.captures(p) {
            let node_type = caps.get(1).unwrap().as_str();
            let node_id = caps.get(2).unwrap().as_str();
            let rel_type = caps.get(3).unwrap().as_str();
            let hops: usize = caps.get(4).unwrap().as_str().parse().unwrap_or(1);
            return Ok(self.multi_hop(&(node_type, node_id), Some(rel_type), hops, Direction::Out));
        }

        // Match: :type:id -[:REL*N..M]-> *
        let range_regex = RANGE_REGEX.get_or_init(|| {
            Regex::new(r"^:(\w+):(\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*$").unwrap()
        });
        if let Some(caps) = range_regex.captures(p) {
            let node_type = caps.get(1).unwrap().as_str();
            let node_id = caps.get(2).unwrap().as_str();
            let rel_type = caps.get(3).unwrap().as_str();
            let min_hops: usize = caps.get(4).unwrap().as_str().parse().unwrap_or(1);
            let max_hops: usize = caps.get(5).unwrap().as_str().parse().unwrap_or(3);
            return Ok(self.multi_hop_range(
                &(node_type, node_id),
                Some(rel_type),
                min_hops,
                max_hops,
                Direction::Out,
            ));
        }

        // Match: :type:id -[:REL]-> *
        let simple_regex = SIMPLE_REGEX
            .get_or_init(|| Regex::new(r"^:(\w+):(\w+)\s*-\[:(\w+)\]->\s*\*$").unwrap());
        if let Some(caps) = simple_regex.captures(p) {
            let node_type = caps.get(1).unwrap().as_str();
            let node_id = caps.get(2).unwrap().as_str();
            let rel_type = caps.get(3).unwrap().as_str();
            return Ok(self.neighbors(&(node_type, node_id), Some(rel_type), Direction::Out));
        }

        Err(GraphError::ParseError(format!("Invalid query pattern: {}", pattern)))
    }

    // =========================================================================
    // Fluent API Entry Point
    // =========================================================================

    /// Start a fluent traversal from a node
    pub fn start(&self, node_ref: &NodeRef) -> GraphTraversal<'_> {
        GraphTraversal::new(self, NodeId::new(node_ref.0, node_ref.1))
    }
}

// =============================================================================
// Fluent Traversal API
// =============================================================================

/// Fluent API for graph traversal
pub struct GraphTraversal<'a> {
    graph: &'a ISONGraph,
    current: HashSet<String>,
    visited: HashSet<String>,
    ref_map: HashMap<String, NodeId>,
}

impl<'a> GraphTraversal<'a> {
    pub fn new(graph: &'a ISONGraph, start: NodeId) -> Self {
        let start_key = start.to_key();
        let mut current = HashSet::new();
        current.insert(start_key.clone());

        let mut visited = HashSet::new();
        visited.insert(start_key.clone());

        let mut ref_map = HashMap::new();
        ref_map.insert(start_key, start);

        Self {
            graph,
            current,
            visited,
            ref_map,
        }
    }

    /// Traverse one hop following edges
    pub fn hop(mut self, rel_type: Option<&str>, direction: Direction) -> Self {
        let mut next_level: HashSet<String> = HashSet::new();

        for key in &self.current {
            if let Some(node_id) = self.ref_map.get(key) {
                let neighbors = self.graph.neighbors(&node_id.as_ref(), rel_type, direction);
                for neighbor in neighbors {
                    let neighbor_key = neighbor.to_key();
                    if !self.visited.contains(&neighbor_key) {
                        next_level.insert(neighbor_key.clone());
                        self.ref_map.insert(neighbor_key, neighbor);
                    }
                }
            }
        }

        for key in &next_level {
            self.visited.insert(key.clone());
        }
        self.current = next_level;
        self
    }

    /// Traverse N hops
    pub fn hops(mut self, n: usize, rel_type: Option<&str>, direction: Direction) -> Self {
        for _ in 0..n {
            self = self.hop(rel_type, direction);
        }
        self
    }

    /// Filter current nodes
    pub fn filter<F>(mut self, f: F) -> Self
    where
        F: Fn(&Node) -> bool,
    {
        let filtered: HashSet<String> = self
            .current
            .iter()
            .filter(|key| {
                if let Some(node_id) = self.ref_map.get(*key) {
                    if let Ok(node) = self.graph.get_node_by_id(node_id) {
                        return f(node);
                    }
                }
                false
            })
            .cloned()
            .collect();
        self.current = filtered;
        self
    }

    /// Return current nodes as NodeId vector
    pub fn collect(self) -> Vec<NodeId> {
        self.current
            .iter()
            .filter_map(|key| self.ref_map.get(key).cloned())
            .collect()
    }

    /// Return current nodes as Node objects
    pub fn collect_nodes(self) -> Vec<Node> {
        self.current
            .iter()
            .filter_map(|key| {
                self.ref_map
                    .get(key)
                    .and_then(|id| self.graph.get_node_by_id(id).ok().cloned())
            })
            .collect()
    }

    /// Count current nodes
    pub fn count(&self) -> usize {
        self.current.len()
    }

    /// Get first node or None
    pub fn first(&self) -> Option<NodeId> {
        self.current
            .iter()
            .next()
            .and_then(|key| self.ref_map.get(key).cloned())
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add_and_get_node() {
        let mut graph = ISONGraph::new("test");
        graph
            .add_node("person", "1", props![("name", "Alice"), ("age", "30")])
            .unwrap();

        let node = graph.get_node("person", "1").unwrap();
        assert_eq!(node.node_type, "person");
        assert_eq!(node.id, "1");
        assert_eq!(crate::value_to_text(node.properties.get("name").unwrap()), "Alice");
    }

    #[test]
    fn test_duplicate_node() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        assert!(graph.add_node("person", "1", props![]).is_err());
    }

    #[test]
    fn test_add_node_rejects_colon() {
        let mut graph = ISONGraph::new("test");
        assert!(matches!(
            graph.add_node("per:son", "1", props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert!(matches!(
            graph.add_node("person", "1:2", props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert_eq!(graph.node_count(), 0);
    }

    // ':' and '|' are structurally significant to the wire format ('type:id'
    // references, ISONL columns); allowing them in a node type, node id, or
    // relationship type builds a graph that fails on to_ison()/to_isonl()
    // round-trip instead of failing loudly at construction.
    #[test]
    fn test_add_node_rejects_pipe() {
        let mut graph = ISONGraph::new("test");
        assert!(matches!(
            graph.add_node("per|son", "1", props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert!(matches!(
            graph.add_node("person", "1|2", props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert_eq!(graph.node_count(), 0);
    }

    #[test]
    fn test_add_edge_rejects_colon_and_pipe_in_rel_type() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        assert!(matches!(
            graph.add_edge("KN:OWS", ("person", "1"), ("person", "2"), props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert!(matches!(
            graph.add_edge("KN|OWS", ("person", "1"), ("person", "2"), props![]),
            Err(GraphError::InvalidIdentifier(_))
        ));
        assert_eq!(graph.edge_count(), 0);
    }

    #[test]
    fn test_unrepresentable_identifiers_are_rejected() {
        // Whitespace and empty used to be accepted and then blow up on round
        // trip: ':a b:1' splits mid-reference, and an id column holding 'a b'
        // reparses as two values. Rejected at construction instead.
        for bad in ["a b", "a\tb", "a\nb", ""] {
            let mut graph = ISONGraph::new("test");
            assert!(graph.add_node(bad, "1", props![]).is_err(), "type {:?}", bad);
            assert!(graph.add_node("p", bad, props![]).is_err(), "id {:?}", bad);
        }

        // ISONL cannot quote a block name, so types are stricter than ids.
        for bad in ["a\"b", "a\\b"] {
            let mut graph = ISONGraph::new("test");
            assert!(graph.add_node(bad, "1", props![]).is_err(), "type {:?}", bad);
            assert!(graph.add_node("p", bad, props![]).is_ok(), "id {:?}", bad);
        }
    }

    #[test]
    fn test_valid_identifiers_still_allowed() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("a-type", "an-id-1", props![]).unwrap();
        graph.add_node("b.c", "#2", props![]).unwrap();
        graph
            .add_edge("SHARES_BORDER_WITH", ("a-type", "an-id-1"), ("b.c", "#2"), props![])
            .unwrap();
        assert_eq!(graph.edge_count(), 1);

        let restored = ISONGraph::from_ison(&graph.to_ison(), None).unwrap();
        assert_eq!(restored.node_count(), 2);
        assert_eq!(restored.edge_count(), 1);
    }

    #[test]
    fn test_no_longer_crashes_on_ison_roundtrip() {
        // Previously: add_node("a:b", "1") succeeded, then to_ison() ->
        // from_ison() raised NodeNotFound - the actual bug this closes.
        let mut graph = ISONGraph::new("test");
        assert!(graph.add_node("a:b", "1", props![]).is_err());
    }

    #[test]
    fn test_no_longer_crashes_on_isonl_roundtrip() {
        let mut graph = ISONGraph::new("test");
        assert!(graph.add_node("rel|type", "1", props![]).is_err());
    }

    #[cfg(feature = "serde")]
    #[test]
    fn test_serde_deserialize_rejects_bad_identifiers() {
        // Deserialization bypasses add_node/add_edge entirely (it rebuilds
        // the index maps directly from the payload), so a crafted or
        // corrupted JSON blob could smuggle in a ':' or '|' identifier that
        // the public API would have rejected - verify the TryFrom impl
        // re-applies the same guard.
        let bad = r#"{"name":"t","directed":true,"nodes":{"a:b":{"1":{"node_type":"a:b","id":"1","properties":{}}}},"edges":{}}"#;
        let result: std::result::Result<ISONGraph, _> = serde_json::from_str(bad);
        assert!(result.is_err());

        let good = r#"{"name":"t","directed":true,"nodes":{"a":{"1":{"node_type":"a","id":"1","properties":{}}}},"edges":{}}"#;
        let graph: ISONGraph = serde_json::from_str(good).unwrap();
        assert_eq!(graph.node_count(), 1);
    }

    #[test]
    fn test_add_and_has_edge() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        assert!(graph.has_edge("KNOWS", ("person", "1"), ("person", "2")));
        assert!(!graph.has_edge("KNOWS", ("person", "2"), ("person", "1")));
    }

    #[test]
    fn test_neighbors() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "3"), props![])
            .unwrap();

        let friends = graph.neighbors(&("person", "1"), Some("KNOWS"), Direction::Out);
        assert_eq!(friends.len(), 2);
    }

    #[test]
    fn test_multi_hop() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();
        graph
            .add_edge("KNOWS", ("person", "2"), ("person", "3"), props![])
            .unwrap();

        let two_hops = graph.multi_hop(&("person", "1"), Some("KNOWS"), 2, Direction::Out);
        assert_eq!(two_hops.len(), 1);
        assert_eq!(two_hops[0].id, "3");
    }

    #[test]
    fn test_shortest_path() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();
        graph
            .add_edge("KNOWS", ("person", "2"), ("person", "3"), props![])
            .unwrap();

        let path = graph
            .shortest_path(&("person", "1"), &("person", "3"), Some("KNOWS"), 10, Direction::Out)
            .unwrap();
        assert_eq!(path.length(), 2);
        assert_eq!(path.nodes.len(), 3);
    }

    #[test]
    fn test_node_count() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("company", "100", props![]).unwrap();

        assert_eq!(graph.node_count(), 3);
        assert_eq!(graph.node_count_of_type("person"), 2);
        assert_eq!(graph.node_count_of_type("company"), 1);
    }

    #[test]
    fn test_to_ison() {
        let mut graph = ISONGraph::new("test");
        graph
            .add_node("person", "1", props![("name", "Alice")])
            .unwrap();
        graph
            .add_node("person", "2", props![("name", "Bob")])
            .unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        let ison = graph.to_ison();
        assert!(ison.contains("nodes.person"));
        assert!(ison.contains("edges.KNOWS"));
        assert!(ison.contains("Alice"));
    }

    fn special_values_graph() -> ISONGraph {
        let mut graph = ISONGraph::new("test");
        graph
            .add_node(
                "person",
                "1",
                props![
                    ("name", "Alice Smith"),
                    ("bio", "a|b"),
                    ("note", "line1\nline2"),
                    ("empty", ""),
                ],
            )
            .unwrap();
        graph
            .add_node(
                "person",
                "2",
                props![
                    ("name", "Bob"),
                    ("bio", "he said \"hi\""),
                    ("note", "x"),
                    ("empty", "y"),
                ],
            )
            .unwrap();
        graph
            .add_edge(
                "KNOWS",
                ("person", "1"),
                ("person", "2"),
                props![("where", "New York"), ("tag", "")],
            )
            .unwrap();
        graph
    }

    fn assert_special_values(restored: &ISONGraph) {
        assert_eq!(restored.node_count(), 2);
        assert_eq!(restored.edge_count(), 1);
        let n1 = restored.get_node("person", "1").unwrap();
        assert_eq!(crate::value_to_text(n1.properties.get("name").unwrap()), "Alice Smith");
        assert_eq!(crate::value_to_text(n1.properties.get("bio").unwrap()), "a|b");
        assert_eq!(crate::value_to_text(n1.properties.get("note").unwrap()), "line1\nline2");
        assert_eq!(crate::value_to_text(n1.properties.get("empty").unwrap()), "");
        let n2 = restored.get_node("person", "2").unwrap();
        assert_eq!(crate::value_to_text(n2.properties.get("bio").unwrap()), "he said \"hi\"");
        let e = restored
            .get_edge("KNOWS", ("person", "1"), ("person", "2"))
            .unwrap();
        assert_eq!(crate::value_to_text(e.properties.get("where").unwrap()), "New York");
        assert_eq!(crate::value_to_text(e.properties.get("tag").unwrap()), "");
    }

    #[test]
    fn test_ison_round_trip_special_values() {
        let graph = special_values_graph();
        let restored = ISONGraph::from_ison(&graph.to_ison(), Some("test")).unwrap();
        assert_special_values(&restored);
    }

    #[test]
    fn test_isonl_round_trip_special_values() {
        let graph = special_values_graph();
        let restored = ISONGraph::from_isonl(&graph.to_isonl(), Some("test")).unwrap();
        assert_special_values(&restored);
    }

    #[test]
    fn test_is_connected() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        assert!(graph.is_connected());

        graph.add_node("person", "3", props![]).unwrap();
        assert!(!graph.is_connected());
    }

    // =========================================================================
    // Deserialization Tests
    // =========================================================================

    #[test]
    fn test_from_ison() {
        let ison_text = r#"
nodes.person
id name age
alice Alice 30
bob Bob 25

edges.KNOWS
source target since
:person:alice :person:bob 2020
"#;

        let graph = ISONGraph::from_ison(ison_text, Some("test")).unwrap();
        assert_eq!(graph.node_count(), 2);
        assert_eq!(graph.edge_count(), 1);
        assert!(graph.has_node("person", "alice"));
        assert!(graph.has_node("person", "bob"));
        assert!(graph.has_edge("KNOWS", ("person", "alice"), ("person", "bob")));
    }

    #[test]
    fn test_from_isonl() {
        let isonl_text = "nodes.person|id name age|alice Alice 30\n\
            nodes.person|id name age|bob Bob 25\n\
            edges.KNOWS|source target since|:person:alice :person:bob 2020\n";

        let graph = ISONGraph::from_isonl(isonl_text, Some("test")).unwrap();
        assert_eq!(graph.node_count(), 2);
        assert_eq!(graph.edge_count(), 1);
        assert!(graph.has_node("person", "alice"));
        assert!(graph.has_edge("KNOWS", ("person", "alice"), ("person", "bob")));
    }

    #[test]
    fn test_from_ison_malformed_errors() {
        // Row with 3 values against 2 fields
        let bad_row = "nodes.person\nid name\nalice Alice Extra";
        assert!(matches!(
            ISONGraph::from_ison(bad_row, None),
            Err(GraphError::ParseError(_))
        ));

        // Header without '.'
        let bad_header = "people\nid name\nalice Alice";
        assert!(matches!(
            ISONGraph::from_ison(bad_header, None),
            Err(GraphError::ParseError(_))
        ));

        // Unknown block kind
        let bad_kind = "vertices.person\nid name\nalice Alice";
        assert!(matches!(
            ISONGraph::from_ison(bad_kind, None),
            Err(GraphError::ParseError(_))
        ));
    }

    #[test]
    fn test_from_isonl_malformed_errors() {
        // Missing values section
        assert!(matches!(
            ISONGraph::from_isonl("nodes.person|id name", None),
            Err(GraphError::ParseError(_))
        ));
        // A short row is padded with null by the shared ISON parser rather
        // than rejected - every port behaves this way now that emission and
        // parsing both go through it, so this is no longer an error here.
        let padded = ISONGraph::from_isonl("nodes.person|id name|alice", None).unwrap();
        assert_eq!(padded.node_count(), 1);
        // Header without '.'
        assert!(matches!(
            ISONGraph::from_isonl("nodesperson|id|alice", None),
            Err(GraphError::ParseError(_))
        ));
    }

    // =========================================================================
    // Additional Analysis Tests
    // =========================================================================

    #[test]
    fn test_connected_components() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph.add_node("person", "4", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "3"), ("person", "4"), props![]).unwrap();

        let components = graph.connected_components();
        assert_eq!(components.len(), 2);
    }

    #[test]
    fn test_all_paths() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "2"), ("person", "3"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "3"), props![]).unwrap();

        let paths = graph.all_paths(&("person", "1"), &("person", "3"), None, 5, Direction::Out);
        assert_eq!(paths.len(), 2); // Direct path and via person 2
    }

    #[test]
    fn test_get_edge() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![("since", "2020")]).unwrap();

        let edge = graph.get_edge("KNOWS", ("person", "1"), ("person", "2")).unwrap();
        assert_eq!(edge.rel_type, "KNOWS");
        assert_eq!(crate::value_to_text(edge.properties.get("since").unwrap()), "2020");
    }

    // =========================================================================
    // Pattern Query Tests
    // =========================================================================

    #[test]
    fn test_query_pattern() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "2"), ("person", "3"), props![]).unwrap();

        let result = graph.query(":person:1 -[:KNOWS]-> *").unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "2");

        let result2 = graph.query(":person:1 -[:KNOWS*2]-> *").unwrap();
        assert_eq!(result2.len(), 1);
        assert_eq!(result2[0].id, "3");
    }

    // =========================================================================
    // Fluent API Tests
    // =========================================================================

    #[test]
    fn test_start_method() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![("name", "Alice")]).unwrap();
        graph.add_node("person", "2", props![("name", "Bob")]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();

        let result = graph.start(&("person", "1"))
            .hop(Some("KNOWS"), Direction::Out)
            .collect();

        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "2");
    }

    #[test]
    fn test_fluent_collect_nodes() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![("name", "Alice")]).unwrap();
        graph.add_node("person", "2", props![("name", "Bob")]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();

        let nodes = graph.start(&("person", "1"))
            .hop(Some("KNOWS"), Direction::Out)
            .collect_nodes();

        assert_eq!(nodes.len(), 1);
        assert_eq!(crate::value_to_text(nodes[0].properties.get("name").unwrap()), "Bob");
    }

    #[test]
    fn test_fluent_filter() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![("name", "Alice")]).unwrap();
        graph.add_node("person", "2", props![("name", "Bob")]).unwrap();
        graph.add_node("person", "3", props![("name", "Charlie")]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "3"), props![]).unwrap();

        let result = graph.start(&("person", "1"))
            .hop(Some("KNOWS"), Direction::Out)
            .filter(|n| n.properties.get("name").map(|v| crate::value_to_text(v) == "Bob").unwrap_or(false))
            .collect();

        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "2");
    }

    // =========================================================================
    // Cycle / Direction / Dedup Tests
    // =========================================================================

    #[test]
    fn test_undirected_single_edge_no_cycle() {
        let mut graph = ISONGraph::undirected("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();
        // A single undirected edge must not be reported as a cycle
        assert!(!graph.has_cycle(None));

        // A chain of two undirected edges is still acyclic
        graph.add_node("person", "3", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "2"), ("person", "3"), props![])
            .unwrap();
        assert!(!graph.has_cycle(None));

        // Closing the triangle creates a real cycle
        graph
            .add_edge("KNOWS", ("person", "3"), ("person", "1"), props![])
            .unwrap();
        assert!(graph.has_cycle(None));
    }

    #[test]
    fn test_directed_cycle_detection() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("t", "a", props![]).unwrap();
        graph.add_node("t", "b", props![]).unwrap();
        graph.add_edge("R", ("t", "a"), ("t", "b"), props![]).unwrap();
        assert!(!graph.has_cycle(None));
        graph.add_edge("R", ("t", "b"), ("t", "a"), props![]).unwrap();
        assert!(graph.has_cycle(None));
        // Filtering on a rel type with no cycle
        assert!(!graph.has_cycle(Some("OTHER")));
    }

    #[test]
    fn test_neighbors_both_undirected_dedup() {
        let mut graph = ISONGraph::undirected("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        let neighbors = graph.neighbors(&("person", "1"), None, Direction::Both);
        assert_eq!(neighbors.len(), 1);
        assert_eq!(neighbors[0].id, "2");
    }

    #[test]
    fn test_path_exists_direction() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        assert!(graph.path_exists(&("person", "1"), &("person", "2"), None, 5, Direction::Out));
        assert!(!graph.path_exists(&("person", "2"), &("person", "1"), None, 5, Direction::Out));
        assert!(graph.path_exists(&("person", "2"), &("person", "1"), None, 5, Direction::In));
        assert!(graph.path_exists(&("person", "2"), &("person", "1"), None, 5, Direction::Both));
    }

    #[test]
    fn test_max_hops_usize_max_no_overflow() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![])
            .unwrap();

        assert!(graph.path_exists(
            &("person", "1"),
            &("person", "2"),
            None,
            usize::MAX,
            Direction::Out
        ));
        let paths = graph.all_paths(&("person", "1"), &("person", "2"), None, usize::MAX, Direction::Out);
        assert_eq!(paths.len(), 1);
    }

    #[test]
    fn test_all_paths_start_equals_end() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        let paths = graph.all_paths(&("person", "1"), &("person", "1"), None, 5, Direction::Out);
        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0].length(), 0);
    }

    // =========================================================================
    // Serde Tests
    // =========================================================================

    #[cfg(feature = "serde")]
    #[test]
    fn test_serde_round_trip() {
        let mut graph = ISONGraph::new("test");
        graph
            .add_node("person", "1", props![("name", "Alice")])
            .unwrap();
        graph
            .add_node("person", "2", props![("name", "Bob")])
            .unwrap();
        graph
            .add_edge("KNOWS", ("person", "1"), ("person", "2"), props![("since", "2020")])
            .unwrap();

        let json = serde_json::to_string(&graph).unwrap();
        // Internal indexes must not be serialized (every edge only once)
        assert!(!json.contains("out_edges"));
        assert!(!json.contains("in_edges"));
        assert!(!json.contains("edge_set"));

        let restored: ISONGraph = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.name, "test");
        assert_eq!(restored.node_count(), 2);
        assert_eq!(restored.edge_count(), 1);
        assert!(restored.has_edge("KNOWS", ("person", "1"), ("person", "2")));

        // Indexes are rebuilt: traversal works on the deserialized graph
        let neighbors = restored.neighbors(&("person", "1"), Some("KNOWS"), Direction::Out);
        assert_eq!(neighbors.len(), 1);
        assert_eq!(neighbors[0].id, "2");
        assert_eq!(restored.in_degree(&("person", "2")), 1);
    }

    #[test]
    fn test_fluent_hops() {
        let mut graph = ISONGraph::new("test");
        graph.add_node("person", "1", props![]).unwrap();
        graph.add_node("person", "2", props![]).unwrap();
        graph.add_node("person", "3", props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "1"), ("person", "2"), props![]).unwrap();
        graph.add_edge("KNOWS", ("person", "2"), ("person", "3"), props![]).unwrap();

        let count = graph.start(&("person", "1"))
            .hops(2, Some("KNOWS"), Direction::Out)
            .count();

        assert_eq!(count, 1);
    }

    // =========================================================================
    // Canonical Serialization
    //
    // to_ison()/to_isonl() must be byte-identical for the same logical graph
    // regardless of insertion order (node type blocks, node rows, edge type
    // blocks, and edge rows are all sorted, ordinal string comparison). The
    // golden fixture below is shared verbatim across every ISONGraph
    // language port's test suite (Python, JS, TS, Rust, C++, C#) as the
    // cross-language byte-identity contract - if it changes here, it must
    // change everywhere.
    // =========================================================================

    const CANONICAL_GOLDEN_ISON: &str = r#"edges.KNOWS
since source target weight
"2020" :person:1 :person:2 1.75
"2021" :person:10 :person:1 0.5

edges.WORKS_AT
role source target
"Lead Engineer" :person:1 :company:acme

edges.WORKS_ON
hours source target
3 :person:10 :project:p1
5 :person:2 :project:p1

nodes.company
id listed name staff
acme false "Acme Corp" 42

nodes.person
id active age name score
"1" true "30" Alice 9.5
"10" false "22" Jax -2.25
"2" null "25" Bob null

nodes.project
id budget name tag
p1 1250 Alpha a|b"#;

    const CANONICAL_GOLDEN_ISONL: &str = r#"edges.KNOWS|since source target weight|"2020" :person:1 :person:2 1.75
edges.KNOWS|since source target weight|"2021" :person:10 :person:1 0.5
edges.WORKS_AT|role source target|"Lead Engineer" :person:1 :company:acme
edges.WORKS_ON|hours source target|3 :person:10 :project:p1
edges.WORKS_ON|hours source target|5 :person:2 :project:p1
nodes.company|id listed name staff|acme false "Acme Corp" 42
nodes.person|id active age name score|"1" true "30" Alice 9.5
nodes.person|id active age name score|"10" false "22" Jax -2.25
nodes.person|id active age name score|"2" null "25" Bob null
nodes.project|id budget name tag|p1 1250 Alpha "a\|b""#;

    #[allow(clippy::type_complexity)]
    fn build_canonical_fixture(order: usize) -> ISONGraph {
        let mut g = ISONGraph::new("fixture");
        // Mixed types on purpose: the string ids and string ages pin that a
        // value which would reparse as a number stays quoted, while the int,
        // float and bool pin that a real number does not. No integral float
        // appears - JavaScript cannot originate one, so a shared fixture must
        // not ask for it.
        let nodes: Vec<(&str, &str, Vec<(&str, Value)>)> = vec![
            ("company", "acme", props![("name", "Acme Corp"), ("staff", 42i64), ("listed", false)]),
            ("person", "1", props![("name", "Alice"), ("age", "30"), ("score", 9.5f64), ("active", true)]),
            ("person", "10", props![("name", "Jax"), ("age", "22"), ("score", -2.25f64), ("active", false)]),
            ("person", "2", props![("name", "Bob"), ("age", "25")]),
            ("project", "p1", props![("name", "Alpha"), ("tag", "a|b"), ("budget", 1250i64)]),
        ];
        let edges: Vec<(&str, (&str, &str), (&str, &str), Vec<(&str, Value)>)> = vec![
            ("KNOWS", ("person", "10"), ("person", "1"), props![("since", "2021"), ("weight", 0.5f64)]),
            ("KNOWS", ("person", "1"), ("person", "2"), props![("since", "2020"), ("weight", 1.75f64)]),
            ("WORKS_AT", ("person", "1"), ("company", "acme"), props![("role", "Lead Engineer")]),
            ("WORKS_ON", ("person", "2"), ("project", "p1"), props![("hours", 5i64)]),
            ("WORKS_ON", ("person", "10"), ("project", "p1"), props![("hours", 3i64)]),
        ];
        let mut n = nodes;
        let mut e = edges;
        if order != 0 {
            n.reverse();
            e.reverse();
        }
        for (t, i, props) in n {
            g.add_node(t, i, props).unwrap();
        }
        for (rel, s, t, props) in e {
            g.add_edge(rel, s, t, props).unwrap();
        }
        g
    }

    #[test]
    fn test_to_ison_independent_of_insertion_order() {
        assert_eq!(build_canonical_fixture(0).to_ison(), build_canonical_fixture(1).to_ison());
    }

    #[test]
    fn test_to_isonl_independent_of_insertion_order() {
        assert_eq!(build_canonical_fixture(0).to_isonl(), build_canonical_fixture(1).to_isonl());
    }

    #[test]
    fn test_to_ison_matches_golden_fixture() {
        assert_eq!(build_canonical_fixture(0).to_ison(), CANONICAL_GOLDEN_ISON);
        assert_eq!(build_canonical_fixture(1).to_ison(), CANONICAL_GOLDEN_ISON);
    }

    #[test]
    fn test_to_isonl_matches_golden_fixture() {
        assert_eq!(build_canonical_fixture(0).to_isonl(), CANONICAL_GOLDEN_ISONL);
        assert_eq!(build_canonical_fixture(1).to_isonl(), CANONICAL_GOLDEN_ISONL);
    }

    #[test]
    fn test_ordinal_not_numeric_sort() {
        // "1" < "10" < "2" ordinally.
        let ison = build_canonical_fixture(0).to_ison();
        let person_block = ison.split("nodes.person
").nth(1).unwrap().split("

").next().unwrap();
        // Ids are quoted because the fixture uses string ids - the canonical
        // writer quotes a string that would otherwise reparse as a number, so
        // the round trip stays lossless. Strip that to read the order.
        let ids: Vec<&str> = person_block
            .lines()
            .skip(1)
            .map(|l| l.split(' ').next().unwrap().trim_matches('"'))
            .collect();
        assert_eq!(ids, vec!["1", "10", "2"]);
    }

    #[test]
    fn test_roundtrip_preserves_canonical_form() {
        let g = build_canonical_fixture(0);
        let reloaded = ISONGraph::from_ison(&g.to_ison(), None).unwrap();
        assert_eq!(reloaded.to_ison(), g.to_ison());
    }
}
