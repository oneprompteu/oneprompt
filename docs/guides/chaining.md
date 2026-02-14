# Chaining Agents

One of the most powerful features of oneprompt is the ability to chain agents together. The output of one agent becomes the input for the next, enabling complex data workflows.

## How Chaining Works

Every agent method (`query`, `analyze`, `chart`) returns an `AgentResult`. You can pass this result to the next agent using the `data_from` parameter:

```python
import oneprompt as op

client = op.Client()

# Step 1: Query data
data = client.query("Revenue by month for 2025")

# Step 2: Pass the result to the next agent
chart = client.chart("Line chart of revenue trend", data_from=data)
```

Under the hood, the SDK:

1. Fetches the JSON artifact from the first result's Artifact Store URL
2. Injects the data inline into the next agent's prompt
3. The next agent processes it with full context

---

## Common Patterns

### Query → Chart

Generate a visualization directly from query results:

```python
data = client.query("Top 10 customers by total spend")
chart = client.chart("Horizontal bar chart of customer spending", data_from=data)
chart.artifacts[0].download("./output/")
```

### Query → Analyze

Run statistical analysis on queried data:

```python
data = client.query("All transactions this quarter")
stats = client.analyze("Calculate descriptive statistics per category", data_from=data)
print(stats.summary)
```

### Query → Analyze → Chart

The full pipeline — query data, process it, then visualize:

```python
# 1. Get raw data
data = client.query("Daily active users for the last 90 days")

# 2. Analyze it
trend = client.analyze("Calculate 7-day moving average", data_from=data)

# 3. Visualize the result
chart = client.chart(
    "Line chart with original and smoothed data",
    data_from=trend
)
```

### Analyze → Chart

If you already have processed data, skip straight to charting:

```python
data = client.query("Monthly revenue by region")
analysis = client.analyze("Pivot data: months as rows, regions as columns", data_from=data)
chart = client.chart("Grouped bar chart of regional revenue", data_from=analysis)
```

---

## Multiple Charts from One Query

You can reuse a single query result to generate multiple visualizations:

```python
data = client.query("Sales by product category and month")

bar = client.chart("Bar chart of total sales per category", data_from=data)
line = client.chart("Line chart of monthly sales trends", data_from=data)
pie = client.chart("Pie chart of category distribution", data_from=data)
```

---

## How Data Flows Between Agents

When you pass `data_from`, the SDK looks for data in this order:

1. **JSON artifact** — Fetches the first `.json` artifact from the Artifact Store on demand
2. **Preview data** — Falls back to `result.preview` (first rows returned by the query)

This means the full dataset (not just the preview) is passed when a JSON artifact is available.

---

## REST API Chaining

You can achieve the same chaining via the REST API using artifact IDs:

```bash
# 1. Query data
DATA=$(curl -s -X POST http://localhost:8000/agents/data \
  -H "Content-Type: application/json" \
  -d '{"query": "Monthly revenue for 2025"}')

ARTIFACT_ID=$(echo $DATA | jq -r '.artifacts[0].id')

# 2. Analyze
ANALYSIS=$(curl -s -X POST http://localhost:8000/agents/python \
  -H "Content-Type: application/json" \
  -d "{\"instruction\": \"Calculate growth rate\", \"data_artifact_id\": \"$ARTIFACT_ID\"}")

RESULT_ID=$(echo $ANALYSIS | jq -r '.artifacts[0].id')

# 3. Chart
curl -X POST http://localhost:8000/agents/chart \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Line chart of revenue with growth\", \"data_artifact_id\": \"$RESULT_ID\"}"
```

See the [REST API Reference](../reference/rest-api.md) for full endpoint documentation.
