# ISONGraph Schema Generator

Automatically generate ISONGraph schemas from JSON graph data.

## Features

- **Type Inference**: Automatically detect field types
- **Constraint Detection**: Infer min/max values, string lengths
- **Enum Detection**: Detect enum-like fields
- **Pattern Recognition**: Detect email, URL, date patterns
- **Multi-Format Output**: Python, TypeScript, JSON, ISON

## Installation

Not on PyPI yet. Install from a checkout of the ISONGraph repo:

```bash
git clone https://github.com/ISON-format/isongraph.git
pip install ./isongraph/schema-generator
```

## Usage

### Command Line

```bash
# Generate Python schema
python -m schema_generator graph.json -o schema.py

# Generate TypeScript schema
python -m schema_generator graph.json --format typescript -o schema.ts

# Generate JSON schema
python -m schema_generator graph.json --format json

# Analyze data without generating schema
python -m schema_generator graph.json --analyze

# Read from stdin
cat graph.json | python -m schema_generator -
```

### Python API

```python
from schema_generator import SchemaGenerator

# Sample data
data = {
    "nodes": [
        {"type": "person", "id": "1", "name": "Alice", "age": 30, "email": "alice@example.com"},
        {"type": "person", "id": "2", "name": "Bob", "age": 25, "email": "bob@example.com"},
        {"type": "company", "id": "acme", "name": "Acme Corp", "size": "large"}
    ],
    "edges": [
        {"rel_type": "WORKS_AT", "source": {"type": "person", "id": "1"},
         "target": {"type": "company", "id": "acme"}, "properties": {"role": "Engineer"}}
    ]
}

# Generate schema
generator = SchemaGenerator()
schema = generator.generate(data, name="organization")

# Output as Python code
print(generator.to_python(schema))

# Output as dictionary
print(generator.to_dict(schema))
```

### Output Formats

#### Python (ISONGraphantic)

```python
from ison_graph.schema import GraphSchema, NodeType, EdgeType
from ison_graph.schema import String, Int, Float, Bool

# Schema: organization

# Node type: company
company_type = (
    NodeType("company")
    .field("id", String().required().min(4).max(4))
    .field("name", String().required().min(9).max(9))
    .field("size", String().required().min(5).max(5))
)

# Node type: person
person_type = (
    NodeType("person")
    .field("age", Int().required().min(25).max(30))
    .field("email", String().required().min(15).max(17).pattern("email"))
    .field("id", String().required().min(1).max(1))
    .field("name", String().required().min(3).max(5))
)

# Edge type: WORKS_AT
works_at_type = (
    EdgeType("WORKS_AT")
    .from_node("person")
    .to_node("company")
    .field("role", String().required().min(8).max(8))
)

schema = (
    GraphSchema("organization")
    .node_types(company_type)
    .node_types(person_type)
    .edge_types(works_at_type)
)
```

#### TypeScript

```typescript
import { GraphSchema, NodeType, EdgeType } from "ison-graph-ts/schema";

const personType = new NodeType("person")
  .field("id", stringField().required())
  .field("name", stringField().required())
  .field("age", intField().min(0).max(150));

export const schema = new GraphSchema("organization")
  .nodeType(personType);
```

#### JSON Schema

```json
{
  "$schema": "https://isongraph.io/schema/v1",
  "name": "organization",
  "nodeTypes": {
    "person": {
      "fields": {
        "id": {"type": "string", "required": true},
        "name": {"type": "string", "required": true},
        "age": {"type": "int", "min": 0, "max": 150}
      }
    }
  }
}
```

## Options

| Option | Description |
|--------|-------------|
| `--format` | Output format: python, typescript, json, ison |
| `--name` | Schema name |
| `--no-constraints` | Don't infer min/max constraints |
| `--no-enums` | Don't detect enum fields |
| `--strict` | Make all fields required |
| `--analyze` | Show data analysis only |

## Pattern Detection

The generator automatically detects these patterns:

| Pattern | Example |
|---------|---------|
| email | user@example.com |
| url | https://example.com |
| uuid | 550e8400-e29b-41d4-a716-446655440000 |
| date | 2024-01-15 |
| datetime | 2024-01-15T10:30:00 |
| phone | +1-555-123-4567 |

## License

MIT License
