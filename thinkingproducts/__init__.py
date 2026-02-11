"""
ThinkingProducts — AI agents for data querying, analysis, and visualization.

Quick start:
    >>> import thinkingproducts as tp
    >>> client = tp.Client(gemini_api_key="your-key", database_url="postgresql://...")
    >>> result = client.query("Show me total sales by month")
    >>> print(result.summary)
"""

from thinkingproducts._version import __version__
from thinkingproducts.client import Client
from thinkingproducts.config import Config

__all__ = ["Client", "Config", "__version__"]
