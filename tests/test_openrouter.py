import json

import httpx
import pytest

from backend.config import settings
from backend.services.cost_analyzer import CostScenarioRegistry
from backend.services.decider_client import DeciderClient
from backend.services.narrator import OpenRouterNarrator


def _completion():
    return {"choices": [{"message": {"content": json.dumps({
        "title": "Spend review", "executive_summary": "Spend increased in the supplied sample.",
        "observed_facts": ["Daily spend increased."], "decider_action_audit": "Decision remains request_approval.",
        "likely_investigation_areas": ["Review workload changes."], "safe_recommendations": ["Check the deployment history."],
        "assumptions_and_limitations": ["Synthetic data."], "follow_up_checklist": ["Recheck tomorrow."],
    })}}]}


@pytest.mark.asyncio
async def test_openrouter_report_uses_bounded_backend_request_and_validates_response(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "server-secret-test")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setattr(settings, "OPENROUTER_HTTP_REFERER", "https://sentinel.example")
    calls = []

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, *, headers, json):
            calls.append((url, headers, json))
            return httpx.Response(200, json=_completion(), request=httpx.Request("POST", url))

    monkeypatch.setattr("backend.services.narrator.httpx.AsyncClient", lambda **kwargs: Client())
    anomaly = CostScenarioRegistry.generate_scenario_anomaly("compute_spike")
    anomaly.owner = "owner@example.com"
    trace = await DeciderClient(provider="mock").decide(anomaly)
    report = await OpenRouterNarrator().generate_report(anomaly, trace)

    assert report.provider == "openrouter"
    assert report.is_simulated is False
    assert report.executive_summary == "Spend increased in the supplied sample."
    url, headers, request = calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer server-secret-test"
    assert headers["HTTP-Referer"] == "https://sentinel.example"
    assert request["max_tokens"] == 900
    assert "response_format" in request
    assert "models" not in request  # No model-level fallback can switch to a paid model.
    assert "owner@example.com" not in json.dumps(request)
    assert "API_KEY" not in json.dumps(request)


@pytest.mark.asyncio
async def test_openrouter_bad_upstream_response_falls_back_truthfully(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "server-secret-test")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "openrouter/free")

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs):
            return httpx.Response(429, json={"error": {"message": "private upstream detail"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("backend.services.narrator.httpx.AsyncClient", lambda **kwargs: Client())
    anomaly = CostScenarioRegistry.generate_scenario_anomaly("compute_spike")
    trace = await DeciderClient(provider="mock").decide(anomaly)
    report = await OpenRouterNarrator().generate_report(anomaly, trace)

    assert report.provider == "grounded-template-fallback"
    assert report.is_simulated is True
