from __future__ import annotations

import uuid

import oneprompt_sdk as op
import pytest


@pytest.mark.asyncio
async def test_query_with_dataset_id_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = op.Client(oneprompt_api_key="op_test_key")

    captured: dict[str, object] = {}

    async def fake_cloud_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload
        return {
            "ok": True,
            "run_id": uuid.uuid4().hex,
            "session_id": "sess_1",
            "summary": "ok",
            "result": {"preview": [{"a": 1}], "columns": ["a"]},
            "artifacts": [
                {"id": "art_1", "name": "result.json", "url": "/artifacts/file.json"},
            ],
        }

    monkeypatch.setattr(client, "_cloud_post", fake_cloud_post)

    result = await client._query_async("top products", dataset_id="ds_123")

    assert result.ok is True
    assert captured["path"] == "/agents/data"
    assert captured["payload"] == {"query": "top products", "dataset_id": "ds_123"}


@pytest.mark.asyncio
async def test_query_with_ephemeral_dataset_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = op.Client(oneprompt_api_key="op_test_key")

    captured: dict[str, object] = {}

    async def fake_cloud_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload
        return {
            "ok": True,
            "run_id": uuid.uuid4().hex,
            "session_id": "sess_1",
            "summary": "ok",
            "result": {},
            "artifacts": [],
        }

    monkeypatch.setattr(client, "_cloud_post", fake_cloud_post)

    result = await client._query_async(
        "top products",
        database_url="postgresql://user:pass@host:5432/db",
        schema_docs="# docs",
    )

    assert result.ok is True
    assert captured["path"] == "/agents/data"
    assert captured["payload"] == {
        "query": "top products",
        "ephemeral_dataset": {
            "dsn": "postgresql://user:pass@host:5432/db",
            "schema_docs": "# docs",
        },
    }


@pytest.mark.asyncio
async def test_query_rejects_dataset_and_database_url_together() -> None:
    client = op.Client(oneprompt_api_key="op_test_key")

    result = await client._query_async(
        "top products",
        dataset_id="ds_123",
        database_url="postgresql://user:pass@host:5432/db",
    )

    assert result.ok is False
    assert result.error == "Cloud query requires either dataset_id or database_url, not both."


@pytest.mark.asyncio
async def test_chart_and_analyze_reuse_data_artifact_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = op.Client(oneprompt_api_key="op_test_key")
    data_from = op.AgentResult(
        ok=True,
        run_id=uuid.uuid4().hex,
        session_id="sess_2",
        data={"preview": [{"x": 1}]},
        artifacts=[
            op.ArtifactRef(id="art_data_1", name="data.json", url="/artifacts/data.json"),
        ],
    )

    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_cloud_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((path, payload))
        return {
            "ok": True,
            "run_id": uuid.uuid4().hex,
            "session_id": payload.get("session_id", "sess_2"),
            "summary": "ok",
            "result": {},
            "artifacts": [],
        }

    monkeypatch.setattr(client, "_cloud_post", fake_cloud_post)

    chart_result = await client._chart_async("plot", data_from=data_from)
    analysis_result = await client._analyze_async("analyze", data_from=data_from)

    assert chart_result.ok is True
    assert analysis_result.ok is True
    assert calls[0][0] == "/agents/chart"
    assert calls[0][1]["data_artifact_id"] == "art_data_1"
    assert calls[1][0] == "/agents/python"
    assert calls[1][1]["data_artifact_id"] == "art_data_1"
