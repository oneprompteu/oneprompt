# AgentResult

Every SDK method (`query`, `chart`, `analyze`) returns an `AgentResult` object containing the operation's output, metadata, and generated files.

```python
result = client.query("Top 10 products by revenue")

print(result.ok)          # True
print(result.summary)     # "Top 10 products by revenue"
print(result.preview)     # [{"product_name": "Widget Pro", ...}, ...]
print(result.artifacts)   # [ArtifactRef(...), ...]
```

---

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `ok` | `bool` | Whether the operation succeeded |
| `run_id` | `str` | Unique identifier for this execution |
| `session_id` | `str` | Session this execution belongs to |
| `summary` | `str \| None` | Human-readable summary of the result |
| `data` | `dict` | Full agent response data |
| `artifacts` | `list[ArtifactRef]` | Generated files (CSV, JSON, HTML) |
| `error` | `str \| None` | Error message if `ok` is `False` |

### Convenience Properties

| Property | Type | Description |
|----------|------|-------------|
| `preview` | `list[dict]` | Preview rows from data queries. Shortcut for `data["preview"]` |
| `columns` | `list[str]` | Column names from data queries. Shortcut for `data["columns"]` |

---

## Usage Examples

### Checking success

```python
result = client.query("Revenue by month")

if result.ok:
    print(result.summary)
    for row in result.preview:
        print(row)
else:
    print(f"Error: {result.error}")
```

### Accessing preview data

```python
result = client.query("Top 5 customers")

# Column names
print(result.columns)  # ["name", "total_spend"]

# Data rows
for row in result.preview:
    print(f"{row['name']}: ${row['total_spend']}")
```

### Working with artifacts

```python
result = client.query("Monthly revenue")

for artifact in result.artifacts:
    print(f"File: {artifact.name}")
    print(f"Type: {artifact.type}")
    print(f"Path: {artifact.path}")

# Read artifact content
csv_text = result.artifacts[0].read_text()
```

### Error handling

```python
result = client.query("Revenue from nonexistent_table")

if not result.ok:
    print(f"Failed: {result.error}")
    # "Failed: Query failed: relation 'nonexistent_table' does not exist"
```

### Chaining results

```python
data = client.query("Sales by category")
chart = client.chart("Pie chart of category distribution", data_from=data)
```

See [Chaining Agents](../guides/chaining.md) for more patterns.

---

## Full Agent Response Data

The `data` property contains the complete agent response. Its structure varies by agent type:

### Data Agent

```python
result.data = {
    "ok": True,
    "intent": "export",
    "columns": ["name", "revenue"],
    "preview": [{"name": "Widget", "revenue": "1000.00"}],
    "row_count": 10,
    "format": "json",
    "artifacts": [...]
}
```

### Chart Agent

```python
result.data = {
    "ok": True,
    "name": "bar_chart.html",
    "artifacts": [...]
}
```

### Python Agent

```python
result.data = {
    "ok": True,
    "summary": "Analysis completed successfully",
    "artifacts": [...]
}
```
