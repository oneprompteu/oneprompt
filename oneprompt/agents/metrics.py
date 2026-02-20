"""Token usage and timing callback for LangChain agents."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

try:
    from oneprompt_sdk.types import RunMetrics
except ImportError:
    _sdk_path = Path(__file__).resolve().parent.parent.parent / "packages" / "oneprompt-sdk"
    if _sdk_path.exists() and str(_sdk_path) not in sys.path:
        sys.path.insert(0, str(_sdk_path))
    from oneprompt_sdk.types import RunMetrics

__all__ = ["UsageCallback", "RunMetrics"]


class UsageCallback(BaseCallbackHandler):
    """Accumulates LLM token usage and timing across all calls in an agent run."""

    def __init__(self) -> None:
        super().__init__()
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._total_tokens: int = 0
        self._reasoning_tokens: Optional[int] = None
        self._cached_tokens: Optional[int] = None
        self._llm_calls: int = 0
        self._start: float = time.perf_counter()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self._llm_calls += 1
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                usage: Optional[dict] = getattr(msg, "usage_metadata", None)
                if not usage:
                    continue
                self._input_tokens += usage.get("input_tokens", 0)
                self._output_tokens += usage.get("output_tokens", 0)
                self._total_tokens += usage.get("total_tokens", 0)
                out_details = usage.get("output_token_details") or {}
                rt = out_details.get("reasoning", 0)
                if rt:
                    self._reasoning_tokens = (self._reasoning_tokens or 0) + rt
                in_details = usage.get("input_token_details") or {}
                ct = in_details.get("cache_read", 0)
                if ct:
                    self._cached_tokens = (self._cached_tokens or 0) + ct

    def to_metrics(self) -> RunMetrics:
        """Return accumulated metrics with elapsed time since callback was created."""
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        return RunMetrics(
            duration_ms=round(elapsed_ms, 1),
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._total_tokens,
            reasoning_tokens=self._reasoning_tokens,
            cached_tokens=self._cached_tokens,
            llm_calls=self._llm_calls,
        )
