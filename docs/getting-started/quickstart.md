# Quick Start

Get up and running with oneprompt in 5 minutes.

!!! tip "Cloud-only setup"
    For SaaS/cloud usage without Docker, install `oneprompt-sdk` and use `import oneprompt_sdk as op`.
    Use `oneprompt` + `op start` only for local/self-hosted MCP workflows.

## 1. Initialize a project

```bash
op init
```

When prompted, choose `0`/`local` for this local quickstart flow.

This creates the following files in your current directory (local mode):

| File | Purpose |
|------|---------|
| `.env` | Configuration — API key and database URL |
| `DATABASE.md` | Schema documentation template |
| `docker-compose.yml` | Docker stack for MCP servers |
| `example.py` | Ready-to-run example script |

## 2. Configure credentials

Edit `.env` with your API key and database connection:

```env
LLM_PROVIDER=google
LLM_API_KEY=your-llm-api-key
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
```

!!! tip "Get your API key"
    Get a free Gemini API key at [Google AI Studio](https://aistudio.google.com/apikey).

## 3. Document your schema

Edit `DATABASE.md` to describe your tables, columns, and relationships. The more detail you provide, the better the AI will write SQL queries.

```markdown
# Database Schema

## Tables

### products
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | text | Product name |
| price | numeric | Unit price in USD |
| category | text | Product category |

### orders
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| product_id | integer | FK → products.id |
| quantity | integer | Units ordered |
| total | numeric | Order total |
| created_at | timestamp | Order date |

## Relationships
- products.id → orders.product_id (one product, many orders)
```

See the [Schema Documentation Guide](../guides/schema-docs.md) for the full recommended format.

## 4. Start services

```bash
op start
```

This builds and launches 4 Docker containers:

| Service | Port | Description |
|---------|------|-------------|
| Artifact Store | 3336 | Generated file storage (CSV, JSON, HTML) |
| PostgreSQL MCP | 3333 | SQL query execution |
| Chart MCP | 3334 | AntV chart generation |
| Python MCP | 3335 | Sandboxed Python execution |

!!! note "First run"
    The first `op start` builds Docker images, which may take a few minutes. Subsequent starts are much faster.

## 5. Run your first query

```python
import oneprompt as op

client = op.Client()  # Reads from .env automatically

# Query your database
result = client.query("What are the top 10 products by revenue?")
print(result.summary)
print(result.preview)
```

Or run the generated example:

```bash
python example.py
```

## 6. Generate a chart

```python
# Use the query result as input
chart = client.chart("Bar chart of top products", data_from=result)
print(chart.summary)

# Download the chart HTML and open it in your browser
for art in chart.artifacts:
    art.download("./output/")
```

## 7. Run Python analysis

```python
analysis = client.analyze("Calculate descriptive statistics", data_from=result)
print(analysis.summary)

# Read or download output artifacts
for art in analysis.artifacts:
    print(art.read_text())
    art.download("./output/")
```

## What's next?

- [Configuration](../guides/configuration.md) — Customize settings, ports, and model
- [Schema Documentation](../guides/schema-docs.md) — Write better schema docs for more accurate queries
- [Chaining Agents](../guides/chaining.md) — Pipe results between query, analyze, and chart
- [Client Reference](../reference/client.md) — Full API reference for the Python SDK
