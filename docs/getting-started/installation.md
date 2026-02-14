# Installation

## Requirements

- **Python 3.12** or higher
- **Docker** — must be installed and running ([Get Docker](https://docs.docker.com/get-docker/))
- **Google Gemini API key** — free at [Google AI Studio](https://aistudio.google.com/apikey)
- **PostgreSQL database** — any accessible PostgreSQL instance

## Install the SDK

```bash
pip install oneprompt
```

This installs the `oneprompt` Python package and the `op` CLI tool.

### Verify installation

```bash
op --version
```

## What gets installed

| Component | Description |
|-----------|-------------|
| `oneprompt` | Python SDK package |
| `tp` | CLI tool for project management |
| Docker images | Built automatically on first `op start` |

## Next steps

Once installed, follow the [Quick Start](quickstart.md) guide to initialize a project and run your first query.
