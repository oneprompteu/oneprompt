# Installation

## Requirements

- **Python 3.12** or higher
- **oneprompt API key** for cloud mode (`ONEPROMPT_API_KEY`)
- **Docker** — only required for local/full mode ([Get Docker](https://docs.docker.com/get-docker/))

## Install the SDK

### Cloud-only (recommended for SaaS)

```bash
pip install oneprompt-sdk
```

Use `import oneprompt_sdk as op` and call the hosted API directly.

### Full local stack

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
| `oneprompt` | Full Python SDK package |
| `op` | CLI tool for project management |
| Docker images | Built automatically on first `op start` |

## Next steps

Once installed, follow the [Quick Start](quickstart.md) guide to initialize a project and run your first query.
