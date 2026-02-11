"""
MCP Server entry point with tool definitions.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from .config import DEFAULT_TIMEOUT
from .executor import execute_code_safely


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

mcp = FastMCP("Python Data Analysis Server")


def _safe_id(value: Optional[str]) -> Optional[str]:
    """Sanitize an ID to prevent path traversal."""
    if not value:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or None


def _get_session_id_from_context() -> str | None:
    """
    Extract session_id from the MCP request context.
    Uses FastMCP's built-in Context.session_id property.
    """
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        # FastMCP Context has session_id as a built-in property
        return _safe_id(ctx.session_id)
    except Exception as e:
        logger.debug("Error getting session_id from context: %s", e)
        return None


def _get_run_id_from_context() -> str | None:
    """
    Extract run_id from the MCP request context.
    run_id is NOT a standard FastMCP property, must read from request headers.
    """
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()

        # Try to get from request_context.request.headers (Starlette)
        request_ctx = getattr(ctx, "request_context", None)
        if request_ctx:
            request = getattr(request_ctx, "request", None)
            if request and hasattr(request, "headers"):
                for key in ("mcp-run-id", "x-run-id"):
                    val = request.headers.get(key)
                    if val:
                        return _safe_id(val)

        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool
def run_python(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Execute Python code for data analysis in a secure sandbox.
    
    Available libraries:
    - numpy (as np): Numerical computing
    - pandas (as pd): Data manipulation and analysis
    - scipy: Scientific computing
    - sklearn: Machine learning (preprocessing, cluster, linear_model, etc.)
    - statsmodels (as sm): Statistical models
    - requests: HTTP requests (for artifact store)
    - statistics, math: Mathematical functions
    - datetime, json, re, collections, itertools: Standard library utilities
    
    Available helper functions:
    - fetch_artifact(path): Get raw bytes from artifact store
    - fetch_artifact_json(path): Get JSON data as dict/list
    - fetch_artifact_csv(path): Get CSV as pandas DataFrame
    - upload_artifact(path, data, content_type): Upload bytes
    - upload_dataframe(path, df, format="csv"): Upload DataFrame as CSV or JSON
    
    Security restrictions:
    - No file system access (use artifact store instead)
    - No subprocess/os commands
    - No eval/exec/compile
    - No network access except artifact store
    - Execution timeout enforced
    
    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default: 30, max: 120)
    
    Returns:
        {
            "ok": bool,
            "output": str,  # stdout output
            "result": str,  # last expression value (if any)
            "error": {...}  # only if ok=False
        }
    
    Example:
        ```python
        # Load data from artifact store
        df = fetch_artifact_csv("data/sales.csv")
        
        # Analyze
        summary = df.groupby("category")["revenue"].agg(["sum", "mean", "count"])
        print(summary)
        
        # Upload results
        upload_dataframe("results/summary.csv", summary.reset_index())
        ```
    """
    session_id = _get_session_id_from_context()
    run_id = _get_run_id_from_context()
    return execute_code_safely(code, timeout=timeout, session_id=session_id, run_id=run_id)


@mcp.tool
def list_available_libraries() -> Dict[str, Any]:
    """
    List all available Python libraries in the sandbox.
    
    Returns information about installed libraries and their versions.
    """
    libraries: Dict[str, Any] = {}
    
    # Check each library
    lib_checks = [
        ("numpy", "np"),
        ("pandas", "pd"),
        ("scipy", None),
        ("sklearn", None),
        ("statsmodels", "sm"),
        ("requests", None),
        ("httpx", None),
    ]
    
    for lib_name, alias in lib_checks:
        try:
            module = __import__(lib_name)
            info: Dict[str, Any] = {"version": getattr(module, "__version__", "unknown")}
            if alias:
                info["alias"] = alias
            libraries[lib_name] = info
        except ImportError:
            libraries[lib_name] = {"available": False}
    
    return {
        "ok": True,
        "libraries": libraries,
        "helper_functions": [
            "fetch_artifact(path) - Get raw bytes from artifact store",
            "fetch_artifact_json(path) - Get JSON as dict/list",
            "fetch_artifact_csv(path) - Get CSV as pandas DataFrame",
            "upload_artifact(path, data, content_type) - Upload bytes",
            "upload_dataframe(path, df, format) - Upload DataFrame",
        ],
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt("python_guide")
def python_analysis_guide() -> str:
    """
    Guide for using the Python data analysis sandbox.
    """
    return """
# Python Data Analysis Sandbox

## CRITICAL: NO IMPORTS ALLOWED

⚠️ **NEVER use `import` statements**. All libraries are pre-loaded in the global namespace.

❌ WRONG:
```python
import pandas as pd  # ERROR: __import__ not found
from sklearn.linear_model import LinearRegression  # ERROR
```

✅ CORRECT:
```python
# Libraries are already available, use them directly:
df = pd.DataFrame(...)  # pd already exists
model = linear_model.LinearRegression()  # linear_model already exists
```

## Pre-loaded Libraries in Namespace

**Data Analysis:**
- `pd` / `pandas`: DataFrames, data manipulation
- `np` / `numpy`: Numerical computing, arrays
- `json`: JSON serialization
- `math`, `statistics`: Mathematical functions

**Machine Learning (sklearn modules):**
- `sklearn`: Main module
- `linear_model`: LinearRegression, Ridge, Lasso, LogisticRegression
- `tree`: DecisionTreeClassifier/Regressor
- `ensemble`: RandomForestClassifier/Regressor, GradientBoosting
- `cluster`: KMeans, DBSCAN
- `preprocessing`: StandardScaler, MinMaxScaler
- `metrics`: accuracy_score, r2_score, mean_squared_error
- `model_selection`: train_test_split, cross_val_score

**Statistics:**
- `scipy`, `scipy_stats`: Scientific computing
- `sm` / `statsmodels`: Statistical models

**Utilities:**
- `datetime`, `date`, `timedelta`: Date handling
- `collections`, `Counter`, `defaultdict`
- `itertools`, `functools`
- `re`: Regular expressions
- `random`: Random numbers
- `io`, `StringIO`, `BytesIO`
- `requests`: HTTP (internal only)

## Artifact Store Functions

```python
# Fetch data
df = fetch_artifact_csv("data/myfile.csv")  # Returns pandas DataFrame
data = fetch_artifact_json("data/myfile.json")  # Returns dict/list
raw = fetch_artifact(path)  # Returns bytes

# Upload results
upload_dataframe("results/output.csv", df, format="csv")
upload_dataframe("results/output.json", df, format="json")
upload_artifact("results/file.bin", bytes_data, "application/octet-stream")
```

## Security Restrictions

- ❌ **No `import` statements** - Libraries are pre-loaded
- ❌ No file system access (use artifact store)
- ❌ No os, subprocess, or system commands
- ❌ No eval(), exec(), or dynamic code execution
- ❌ No network access except artifact store
- ⏱️ Maximum execution time: 120 seconds
- 📏 Maximum output size: 100KB

## Example: Data Analysis Pipeline

```python
# NO IMPORTS NEEDED - Libraries are pre-loaded

# 1. Load data from artifact store
df = fetch_artifact_csv("data/sales.csv")

# 2. Clean and transform
df["date"] = pd.to_datetime(df["date"])
df["month"] = df["date"].dt.to_period("M")

# 3. Analyze
monthly_summary = df.groupby("month").agg({
    "revenue": ["sum", "mean"],
    "orders": "count"
}).round(2)

print(monthly_summary.head())

# 4. Upload results
upload_dataframe("results/monthly_summary.csv", monthly_summary.reset_index())
```

## Machine Learning Example

```python
# NO IMPORTS - sklearn modules are pre-loaded as: linear_model, tree, ensemble, etc.

# Load data
df = fetch_artifact_csv("data/customers.csv")

# Prepare features
X = df[["age", "income", "visits"]].values
y = df["churned"].values

# Split and train (model_selection and ensemble are pre-loaded)
X_train, X_test, y_train, y_test = model_selection.train_test_split(X, y, test_size=0.2)
model = ensemble.RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Evaluate (metrics is pre-loaded)
predictions = model.predict(X_test)
accuracy = metrics.accuracy_score(y_test, predictions)
print(f"Accuracy: {accuracy:.2%}")
```
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Python Data Analysis MCP Server")
    # PORT (Cloud Run) takes priority, then MCP_PYTHON_PORT, then 3335
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", os.getenv("MCP_PYTHON_PORT", "3335")))
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    
    print(f"Starting Python MCP server on {args.host}:{args.port}")
    mcp.run(
        transport="http",
        host=args.host,
        port=args.port,
        stateless_http=True,
    )
