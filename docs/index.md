# oneprompt

**AI agents for data querying, analysis, and chart generation.**

Connect your Gemini API key and PostgreSQL database — query data in natural language, run Python analysis, and generate interactive charts in minutes.

---

## What is oneprompt?

oneprompt is a Python SDK that turns natural language into SQL queries, Python analysis scripts, and interactive charts. It uses Google Gemini as the LLM backbone and runs tool execution in isolated Docker containers via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

```python
import oneprompt as op

client = op.Client()

# Ask a question about your data
result = client.query("What are the top 10 products by revenue?")
print(result.summary)
print(result.preview)

# Generate a chart
chart = client.chart("Bar chart of top products", data_from=result)
chart.artifacts[0].download("./output/")   # save locally

# Run Python analysis
stats = client.analyze("Calculate month-over-month growth", data_from=result)
print(stats.summary)
```

---

## Key Features

- 🗣️ **Natural language queries** — Ask questions about your PostgreSQL database in plain English
- 📊 **Interactive charts** — Generate AntV (G2Plot) visualizations as HTML files
- 🐍 **Python analysis** — Run data analysis in a sandboxed environment
- 🔗 **Agent chaining** — Pipe results from one agent to another (`query → analyze → chart`)
- 🐳 **Docker-based isolation** — All code execution runs in secure containers
- 🖥️ **REST API** — Integrate with any language via HTTP endpoints
- ⚡ **CLI tooling** — Scaffold, start, stop, and manage everything from the terminal

---

## How It Works

```
┌─────────────────────────────────────────────┐
│  Your App / SDK Client / REST API           │
├─────────────────────────────────────────────┤
│  AI Agents (Gemini + LangChain)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │   Data   │ │  Python  │ │  Chart   │    │
│  │  Agent   │ │  Agent   │ │  Agent   │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘    │
├───────┼─────────────┼────────────┼──────────┤
│  MCP Servers (Docker)                       │
│  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐    │
│  │ Postgres │ │  Python  │ │  Chart   │    │
│  │   MCP    │ │   MCP    │ │   MCP    │    │
│  └──────────┘ └──────────┘ └──────────┘    │
├─────────────────────────────────────────────┤
│  Artifact Store (generated file storage)    │
└─────────────────────────────────────────────┘
```

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install the SDK and run your first query in 5 minutes.

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-book-open-variant:{ .lg .middle } **Guides**

    ---

    Learn how to configure your project, document your schema, and chain agents.

    [:octicons-arrow-right-24: Guides](guides/configuration.md)

-   :material-api:{ .lg .middle } **API Reference**

    ---

    Complete reference for the Python SDK, REST API, and CLI.

    [:octicons-arrow-right-24: Reference](reference/client.md)

-   :material-cog:{ .lg .middle } **Architecture**

    ---

    Understand how components, MCP servers, and data flow work together.

    [:octicons-arrow-right-24: Architecture](architecture/overview.md)

</div>
