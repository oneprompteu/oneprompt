"""
oneprompt — AI agents for data querying, analysis, and visualization.

Quick start:
    >>> import oneprompt as op
    >>> client = op.Client(oneprompt_api_key="op_live_...")
    >>> result = client.query("Show me total sales by month")
    >>> print(result.summary)
"""

from oneprompt._version import __version__
from oneprompt.client import Client
from oneprompt.config import Config
from oneprompt_sdk.types import ArtifactRef, AgentResult, RunMetrics

__all__ = ["Client", "Config", "AgentResult", "ArtifactRef", "RunMetrics", "__version__"]
