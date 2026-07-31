# ISONGraph Schema Generator

Automatically generate ISONGraph schemas from JSON graph data.

## Features

- **Type Inference**: Automatically detect field types
- **Constraint Detection**: Infer min/max values, string lengths
- **Enum Detection**: Detect enum-like fields
- **Pattern Recognition**: Detect email, URL, date patterns
- **Multi-Format Output**: Python, TypeScript, JSON, ISON

## Installation

```bash
pip install ison-schema-generator
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
from ison_graph.schema import StringField, IntField

person_type = NodeType("person")
    .field("id", StringField().required())
    .field("name", StringField().required().max_length(50))
    .field("age", IntField().min(0).max(150))
    .field("email", StringField().pattern("email"))

company_type = NodeType("company")
    .field("id", StringField().required())
    .field("name", StringField().required())
    .field("size", StringField().enum(["small", "medium", "large"]))

works_at_type = EdgeType("WORKS_AT")
    .from_node("person")
    .to_node("company")
    .field("role", StringField())

schema = GraphSchema("organization")
    .node_type(person_type)
    .node_type(company_type)
    .edge_type(works_at_type)
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
