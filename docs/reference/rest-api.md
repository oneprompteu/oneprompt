# REST API

The ThinkingProducts local API server provides HTTP endpoints for integration with non-Python applications, frontends, or microservices.

## Starting the API

```bash
tp api
```

Options:

```bash
tp api --host 0.0.0.0 --port 8000     # Custom host/port
tp api --no-reload                      # Disable auto-reload
```

!!! warning "Prerequisite"
    The MCP services must be running (`tp start`) before starting the API.

---

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions` | List sessions |
| `POST` | `/agents/data` | Run natural language data queries |
| `POST` | `/agents/python` | Run Python analysis |
| `POST` | `/agents/chart` | Generate chart visualizations |
| `GET` | `/runs/{run_id}/artifacts/{artifact_id}` | Download an artifact |

---

## Health Check

**`GET /health`**

Verify the API is running.

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "ok"
}
```

---

## Sessions

Sessions group related runs and artifacts. A default session is created automatically when you make your first request without specifying a `session_id`.

### Create a session

**`POST /sessions`**

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "Q1 Analysis"}'
```

**Response:**

```json
{
  "session_id": "abc123def456",
  "name": "Q1 Analysis",
  "created_at": "2026-02-10T10:30:00+00:00",
  "status": "active"
}
```

### List sessions

**`GET /sessions`**

```bash
curl http://localhost:8000/sessions
```

**Response:**

```json
{
  "sessions": [
    {
      "session_id": "abc123def456",
      "name": "Q1 Analysis",
      "created_at": "2026-02-10T10:30:00+00:00",
      "status": "active"
    }
  ]
}
```

---

## Data Agent

Query your PostgreSQL database using natural language.

**`POST /agents/data`**

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | ✅ | Natural language question about your data |
| `session_id` | `string` | ❌ | Session ID. Uses default session if omitted |

### Example

```bash
curl -X POST http://localhost:8000/agents/data \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me the top 10 products by total revenue"}'
```

### Response

```json
{
  "run_id": "7c2978d9eb4e4536",
  "session_id": "default_local_user",
  "ok": true,
  "summary": "Top 10 products by revenue",
  "artifacts": [
    {
      "id": "cfd705a3ce20",
      "type": "data",
      "name": "top_products.csv",
      "url": "/runs/7c2978d9eb4e4536/artifacts/cfd705a3ce20"
    },
    {
      "id": "161b4c90aaf1",
      "type": "data",
      "name": "top_products.json",
      "url": "/runs/7c2978d9eb4e4536/artifacts/161b4c90aaf1"
    }
  ],
  "result": {
    "ok": true,
    "intent": "export",
    "columns": ["product_name", "total_revenue"],
    "preview": [
      {"product_name": "Widget Pro", "total_revenue": "45230.00"}
    ],
    "row_count": 10,
    "format": "json"
  }
}
```

The agent automatically generates CSV and JSON files, and returns a preview of the first rows.

---

## Python Agent

Run Python code for data analysis in a sandboxed environment.

**`POST /agents/python`**

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instruction` | `string` | ✅ | What analysis to perform |
| `data_artifact_id` | `string` | ❌ | Artifact ID from a previous run |
| `output_name` | `string` | ❌ | Output filename (default: `result.csv`) |
| `session_id` | `string` | ❌ | Session ID |

### Example

```bash
curl -X POST http://localhost:8000/agents/python \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Calculate mean, median, and standard deviation of revenue",
    "data_artifact_id": "cfd705a3ce20"
  }'
```

### Response

```json
{
  "run_id": "8d3089e0fa12",
  "session_id": "default_local_user",
  "ok": true,
  "summary": "Statistical analysis completed",
  "artifacts": [
    {
      "id": "9f1234ab5678",
      "type": "result",
      "name": "result.csv",
      "url": "/runs/8d3089e0fa12/artifacts/9f1234ab5678"
    }
  ],
  "result": {
    "ok": true,
    "summary": "Descriptive statistics calculated successfully"
  }
}
```

---

## Chart Agent

Generate interactive AntV (G2Plot) chart visualizations.

**`POST /agents/chart`**

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | `string` | ✅ | Description of the chart to generate |
| `data_artifact_id` | `string` | ❌ | Artifact ID with the data to visualize |
| `data_preview` | `string` | ❌ | Inline data preview (CSV-like text) |
| `session_id` | `string` | ❌ | Session ID |

### Example

```bash
curl -X POST http://localhost:8000/agents/chart \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Bar chart of products by revenue",
    "data_artifact_id": "cfd705a3ce20"
  }'
```

### Response

```json
{
  "run_id": "9e4190f1bc34",
  "session_id": "default_local_user",
  "ok": true,
  "summary": "Chart generated",
  "artifacts": [
    {
      "id": "a0345bcd9012",
      "type": "chart",
      "name": "bar_chart.html",
      "url": "/runs/9e4190f1bc34/artifacts/a0345bcd9012"
    }
  ],
  "result": {
    "ok": true,
    "name": "bar_chart.html"
  }
}
```

The generated chart is an interactive HTML file using AntV G2Plot.

---

## Artifacts

Download files generated by agent runs.

**`GET /runs/{run_id}/artifacts/{artifact_id}`**

```bash
curl http://localhost:8000/runs/7c2978d9eb4e4536/artifacts/cfd705a3ce20 \
  -o top_products.csv
```

The response streams the file content. The `Content-Type` header matches the file type.

---

## Response Format

All agent endpoints return a consistent response structure:

```json
{
  "run_id": "string",
  "session_id": "string",
  "ok": true,
  "summary": "Human-readable description of the result",
  "artifacts": [
    {
      "id": "string",
      "type": "data | result | chart",
      "name": "filename.ext",
      "url": "/runs/{run_id}/artifacts/{artifact_id}"
    }
  ],
  "result": { }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | Unique execution identifier |
| `session_id` | `string` | Session this run belongs to |
| `ok` | `boolean` | Whether the operation succeeded |
| `summary` | `string \| null` | Human-readable summary |
| `artifacts` | `array` | List of generated files |
| `result` | `object` | Agent-specific result details |

---

## Error Codes

| HTTP Status | Meaning |
|-------------|---------|
| `200` | Success |
| `400` | Bad request (missing required fields) |
| `404` | Artifact or session not found |
| `500` | Internal server error (agent failure) |

Error responses include details:

```json
{
  "detail": "query field is required"
}
```

---

## Chaining via API

You can pipe results between agents using artifact IDs:

```bash
# 1. Query data
DATA=$(curl -s -X POST http://localhost:8000/agents/data \
  -H "Content-Type: application/json" \
  -d '{"query": "Monthly revenue for 2025"}')

ARTIFACT_ID=$(echo $DATA | jq -r '.artifacts[0].id')

# 2. Analyze with Python
ANALYSIS=$(curl -s -X POST http://localhost:8000/agents/python \
  -H "Content-Type: application/json" \
  -d "{\"instruction\": \"Calculate growth rate\", \"data_artifact_id\": \"$ARTIFACT_ID\"}")

RESULT_ID=$(echo $ANALYSIS | jq -r '.artifacts[0].id')

# 3. Generate chart
curl -X POST http://localhost:8000/agents/chart \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Line chart of revenue with growth\", \"data_artifact_id\": \"$RESULT_ID\"}"
```
