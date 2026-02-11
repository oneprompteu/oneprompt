"""
Secure Python MCP Server for data analysis.

This package provides a sandboxed Python execution environment with
data science libraries pre-installed and security validations.
"""

from .server import mcp

__all__ = ["mcp"]
