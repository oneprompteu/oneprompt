"""
LLM factory — creates the right LangChain chat model based on provider.

Supported providers: google, openai, anthropic.
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def create_llm(temperature: float = 0) -> BaseChatModel:
    """
    Create a LangChain chat model from environment variables.

    Reads LLM_PROVIDER, LLM_API_KEY, and LLM_MODEL from the environment.

    Args:
        temperature: Sampling temperature (default: 0 for deterministic output).

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the provider is unsupported or the API key is missing.
    """
    provider = os.environ.get("LLM_PROVIDER", "google").lower().strip()
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")

    if not api_key:
        raise ValueError("LLM_API_KEY environment variable is required")

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model or "gemini-2.5-flash-preview-05-20",
            google_api_key=api_key,
            temperature=temperature,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "gpt-4o",
            api_key=api_key,
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or "claude-sonnet-4-20250514",
            api_key=api_key,
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM provider: {provider}. Use google, openai, or anthropic."
    )
