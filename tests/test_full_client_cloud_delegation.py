from __future__ import annotations

import uuid

from oneprompt import Client, Config
from oneprompt.client import AgentResult, ArtifactRef


class DummyCloudClient:
    def __init__(
        self,
        oneprompt_api_key: str | None = None,
        oneprompt_api_url: str | None = None,
    ) -> None:
        self.oneprompt_api_key = oneprompt_api_key
        self.oneprompt_api_url = oneprompt_api_url
        self.calls: list[tuple[str, dict[str, object]]] = []

    def query(
        self,
        question: str,
        session_id: str | None = None,
        dataset_id: str | None = None,
        database_url: str | None = None,
        schema_docs: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            (
                "query",
                {
                    "question": question,
                    "session_id": session_id,
                    "dataset_id": dataset_id,
                    "database_url": database_url,
                    "schema_docs": schema_docs,
                },
            )
        )
        return AgentResult(ok=True, run_id=uuid.uuid4().hex, session_id="cloud")

    def chart(
        self,
        question: str,
        data_from: AgentResult | None = None,
        data_preview: str | None = None,
        session_id: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            (
                "chart",
                {
                    "question": question,
                    "session_id": session_id,
                    "data_preview": data_preview,
                    "data_from": data_from,
                },
            )
        )
        return AgentResult(ok=True, run_id=uuid.uuid4().hex, session_id="cloud")

    def analyze(
        self,
        instruction: str,
        data_from: AgentResult | None = None,
        output_name: str = "result.csv",
        session_id: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            (
                "analyze",
                {
                    "instruction": instruction,
                    "output_name": output_name,
                    "session_id": session_id,
                    "data_from": data_from,
                },
            )
        )
        return AgentResult(ok=True, run_id=uuid.uuid4().hex, session_id="cloud")


def test_full_client_delegates_to_cloud_sdk(monkeypatch) -> None:
    monkeypatch.setattr("oneprompt.client.CloudClient", DummyCloudClient)

    client = Client(oneprompt_api_key="op_key_123", oneprompt_api_url="https://api.oneprompt.eu")

    query = client.query("q", dataset_id="ds_1")
    chart = client.chart("c", data_from=AgentResult(ok=True, run_id="r", session_id="s"))
    analysis = client.analyze("a")

    assert query.ok is True
    assert chart.ok is True
    assert analysis.ok is True
    assert client._cloud_client is not None
    assert [name for name, _ in client._cloud_client.calls] == ["query", "chart", "analyze"]


def test_local_mode_still_initializes_without_cloud_client() -> None:
    config = Config(
        llm_api_key="llm_key",
        llm_provider="google",
        database_url="postgresql://user:pass@localhost:5432/db",
    )

    client = Client(config=config)

    assert client._is_cloud_mode is False
    assert client._cloud_client is None


def test_cloud_mode_does_not_require_llm_api_key() -> None:
    cloud_config = Config(oneprompt_api_key="op_key_123")
    assert cloud_config.validate() == []


def test_local_artifactref_type_comes_from_shared_sdk() -> None:
    artifact = ArtifactRef(id="a1", name="file.json")
    assert artifact.id == "a1"
