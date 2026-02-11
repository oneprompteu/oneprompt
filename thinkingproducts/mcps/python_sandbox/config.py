"""
Configuration and constants for the Python MCP server.
"""

from __future__ import annotations

import os
from typing import Set

# ---------------------------------------------------------------------------
# Execution limits
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT: int = int(os.getenv("PYTHON_EXECUTION_TIMEOUT", "30"))
MAX_TIMEOUT: int = int(os.getenv("PYTHON_MAX_TIMEOUT", "120"))
MAX_OUTPUT_SIZE: int = int(os.getenv("PYTHON_MAX_OUTPUT_SIZE", "100000"))  # 100KB

# ---------------------------------------------------------------------------
# Artifact Store configuration
# ---------------------------------------------------------------------------

ARTIFACT_STORE_URL: str = os.getenv("ARTIFACT_STORE_URL", "")
ARTIFACT_STORE_TOKEN: str = os.getenv("ARTIFACT_STORE_TOKEN", "")

# ---------------------------------------------------------------------------
# Security: Allowed imports
# ---------------------------------------------------------------------------

ALLOWED_IMPORTS: Set[str] = {
    # Data science essentials
    "numpy", "np",
    "pandas", "pd",
    "scipy",
    "sklearn", "scikit-learn",
    "statsmodels",
    
    # Visualization (for data prep, not rendering)
    "matplotlib", "plt",
    "seaborn", "sns",
    "plotly",
    
    # Data handling
    "json",
    "csv",
    "re",
    "math",
    "statistics",
    "decimal",
    "fractions",
    "random",
    "collections",
    "itertools",
    "functools",
    "operator",
    "string",
    "textwrap",
    
    # Date/time
    "datetime",
    "time",
    "calendar",
    "dateutil",
    "pytz",
    
    # HTTP client (for artifact store communication)
    "requests",
    "httpx",
    "urllib.parse",
    
    # Type hints
    "typing",
    "typing_extensions",
    
    # Data formats
    "io",
    "base64",
    "hashlib",
    "uuid",
    "copy",
    "pprint",
    
    # Compression (read-only typically)
    "gzip",
    "zipfile",
    "tarfile",
}

# ---------------------------------------------------------------------------
# Security: Blocked imports (dangerous)
# ---------------------------------------------------------------------------

BLOCKED_IMPORTS: Set[str] = {
    # System access
    "os",
    "sys",
    "subprocess",
    "shutil",
    "pathlib",
    "glob",
    "fnmatch",
    
    # Code execution
    "importlib",
    "builtins",
    "__builtins__",
    "code",
    "codeop",
    "compile",
    "ast",
    "dis",
    "inspect",
    
    # Low-level
    "ctypes",
    "cffi",
    "ffi",
    
    # Network (except requests/httpx for artifact store)
    "socket",
    "socketserver",
    "ssl",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "telnetlib",
    "asyncio",
    "aiohttp",
    
    # Process/threading
    "multiprocessing",
    "threading",
    "concurrent",
    "_thread",
    
    # File/resource access
    "tempfile",
    "shelve",
    "dbm",
    "sqlite3",
    "pickle",
    "marshal",
    
    # Dangerous
    "eval",
    "exec",
    "pty",
    "tty",
    "termios",
    "resource",
    "gc",
    "signal",
    "atexit",
}

# ---------------------------------------------------------------------------
# Security: Blocked built-in functions
# ---------------------------------------------------------------------------

BLOCKED_BUILTINS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "__import__",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "breakpoint",
    "memoryview",
    "help",
    "exit",
    "quit",
}

# ---------------------------------------------------------------------------
# Security: Blocked attribute access patterns
# ---------------------------------------------------------------------------

BLOCKED_ATTRIBUTES: Set[str] = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__mro__",
    "__code__",
    "__globals__",
    "__builtins__",
    "__import__",
    "__dict__",
    "__getattribute__",
    "__reduce__",
    "__reduce_ex__",
}

# ---------------------------------------------------------------------------
# Dangerous code patterns (regex)
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r'\bos\s*\.\s*system\s*\(', "os.system() no está permitido"),
    (r'\bos\s*\.\s*popen\s*\(', "os.popen() no está permitido"),
    (r'\bsubprocess\s*\.', "subprocess no está permitido"),
    (r'\b__import__\s*\(', "__import__() no está permitido"),
    (r'\beval\s*\(', "eval() no está permitido"),
    (r'\bexec\s*\(', "exec() no está permitido"),
    (r'\bcompile\s*\(', "compile() no está permitido"),
    (r'\bopen\s*\([^)]*["\']\/(?!tmp)', "open() con rutas absolutas no está permitido"),
]
