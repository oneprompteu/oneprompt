# Client

The `Client` class is the main entry point for the ThinkingProducts SDK. It orchestrates AI agents, manages sessions, and handles artifact downloads.

```python
import thinkingproducts as tp

client = tp.Client()
```

---

## Constructor

```python
Client(
    gemini_api_key: str = None,
    database_url: str = None,
    schema_docs: str = None,
    schema_docs_path: str = None,
    config: Config = None,
    **kwargs
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `gemini_api_key` | `str` | `None` | Google Gemini API key. Falls back to `GOOGLE_API_KEY` env var |
| `database_url` | `str` | `None` | PostgreSQL connection string. Falls back to `DATABASE_URL` env var |
| `schema_docs` | `str` | `None` | Inline database schema documentation string |
| `schema_docs_path` | `str` | `None` | Path to a `DATABASE.md` file with schema docs |
| `config` | `Config` | `None` | Full `Config` object (overrides all individual params) |
| `**kwargs` | | | Additional config parameters passed to `Config` |

### Initialization Options

```python
import thinkingproducts as tp

# Option A: Read from .env (recommended)
client = tp.Client()

# Option B: Pass credentials directly
client = tp.Client(
    gemini_api_key="your-key",
    database_url="postgresql://user:pass@localhost:5432/mydb",
)

# Option C: With schema docs
client = tp.Client(
    gemini_api_key="your-key",
    database_url="postgresql://user:pass@localhost:5432/mydb",
    schema_docs_path="./DATABASE.md",
)

# Option D: Full Config object
from thinkingproducts import Config

config = Config(
    gemini_api_key="your-key",
    database_url="postgresql://...",
    gemini_model="gemini-3-flash-preview",
    data_dir="./my_data",
)
client = tp.Client(config=config)
```

### Validation

The client validates required settings on initialization:

```python
client = tp.Client()
# ValueError: Configuration errors:
#   - gemini_api_key is required (env: GOOGLE_API_KEY)
#   - database_url is required (env: DATABASE_URL)
```

---

## Methods

### `query()`

Query your PostgreSQL database using natural language.

```python
query(
    question: str,
    session_id: str = None,
) -> AgentResult
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | `str` | ✅ | Natural language question about your data |
| `session_id` | `str` | ❌ | Session ID for grouping related runs. Auto-created if omitted |

#### Returns

[`AgentResult`](agent-result.md) with:

- `summary` — Human-readable description of the query result
- `preview` — First rows of data as a list of dicts
- `columns` — Column names from the result set
- `artifacts` — CSV and JSON files with the full result

#### Example

```python
result = client.query("What are the top 10 products by revenue?")

print(result.ok)        # True
print(result.summary)   # "Top 10 products by revenue"
print(result.columns)   # ["product_name", "total_revenue"]
print(result.preview)   # [{"product_name": "Widget Pro", "total_revenue": "45230.00"}, ...]

# Access the generated files
for artifact in result.artifacts:
    print(f"{artifact.name} → {artifact.path}")
    # top_products.csv → tp_data/out/default_local_user/abc123/top_products.csv
    # top_products.json → tp_data/out/default_local_user/abc123/top_products.json
```

#### How It Works

1. The client creates a session (if needed) and generates a unique `run_id`
2. The Data Agent connects to the PostgreSQL MCP server
3. Your `DATABASE.md` schema is passed as context to Gemini
4. Gemini generates and executes a SQL query
5. Results are exported to CSV and JSON, stored in the Artifact Store
6. Artifacts are downloaded locally to `tp_data/out/`

---

### `chart()`

Generate an interactive chart visualization using AntV G2Plot.

```python
chart(
    question: str,
    data_from: AgentResult = None,
    data_preview: str = None,
    session_id: str = None,
) -> AgentResult
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | `str` | ✅ | Description of the chart you want |
| `data_from` | `AgentResult` | ❌ | Previous result to use as data source |
| `data_preview` | `str` | ❌ | Raw data preview text (alternative to `data_from`) |
| `session_id` | `str` | ❌ | Session ID |

#### Returns

[`AgentResult`](agent-result.md) with:

- `summary` — Description of the generated chart
- `artifacts` — HTML file containing the interactive chart

#### Example

```python
# From a previous query
data = client.query("Revenue by month for 2025")
chart = client.chart("Line chart of monthly revenue", data_from=data)

print(chart.ok)                     # True
print(chart.artifacts[0].name)      # "line_chart.html"
print(chart.artifacts[0].path)      # "tp_data/out/.../line_chart.html"

# With inline data
chart = client.chart(
    "Bar chart of sales",
    data_preview="product,sales\nWidgets,100\nGadgets,250\nDoodads,75"
)
```

#### Supported Chart Types

The Chart Agent can generate: bar, line, pie, scatter, area, column, grouped bar, stacked bar, dual-axis, and more. Just describe what you want and the agent will pick the right type.

#### How It Works

1. Data from `data_from` is read from the local JSON artifact (or `data_preview` is used)
2. The Chart Agent connects to the Chart MCP server
3. Gemini generates the chart configuration
4. The MCP server creates an interactive HTML file with AntV G2Plot
5. The HTML file is downloaded locally

---

### `analyze()`

Run Python analysis code in a sandboxed environment.

```python
analyze(
    instruction: str,
    data_from: AgentResult = None,
    output_name: str = "result.csv",
    session_id: str = None,
) -> AgentResult
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `instruction` | `str` | ✅ | Description of the analysis to perform |
| `data_from` | `AgentResult` | ❌ | Previous result to use as input data |
| `output_name` | `str` | ❌ | Name for the output file (default: `result.csv`) |
| `session_id` | `str` | ❌ | Session ID |

#### Returns

[`AgentResult`](agent-result.md) with:

- `summary` — Description of the analysis performed
- `artifacts` — Output files from the analysis

#### Example

```python
data = client.query("All transactions this year")

# Descriptive statistics
stats = client.analyze(
    "Calculate mean, median, and standard deviation of order totals",
    data_from=data,
)
print(stats.summary)

# Custom output name
pivot = client.analyze(
    "Pivot table: months as rows, categories as columns, values = revenue",
    data_from=data,
    output_name="pivot_table.csv",
)
print(pivot.artifacts[0].path)
```

#### Sandbox Environment

Python code runs in a secure Docker container with:

- Read-only filesystem
- Limited memory (2GB) and CPU (2 cores)
- No network access
- Pre-installed libraries: pandas, numpy, scipy, and standard library

---

## Properties

### `config`

Access the current configuration:

```python
client.config  # → Config object
client.config.gemini_model     # "gemini-3-flash-preview"
client.config.database_url     # "postgresql://..."
client.config.data_dir         # "./tp_data"
```

See [Config](config.md) for the full reference.
