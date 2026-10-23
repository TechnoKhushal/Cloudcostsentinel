"""Check a deployed public demo's health, scenarios route, and browser CORS policy."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str) -> tuple[int, dict | list]:
    with urlopen(url, timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend_origin", help="Backend origin, for example https://service.onrender.com")
    parser.add_argument("--frontend-origin", required=True, help="Exact deployed frontend origin")
    args = parser.parse_args()
    origin = args.backend_origin.rstrip("/")

    try:
        status_code, live = request_json(f"{origin}/api/health/live")
        assert status_code == 200 and live.get("status") == "ok", f"liveness failed: {live}"

        status_code, health = request_json(f"{origin}/api/health")
        assert status_code == 200 and health.get("environment") == "demo", f"unexpected environment: {health}"
        assert health.get("auth", {}).get("mode") == "explicit_demo", "demo auth mode is not explicit_demo"
        providers = health.get("providers", {})
        assert providers.get("decider", {}).get("state") == "simulated", "Decider is not reported as simulated"
        assert providers.get("bedrock", {}).get("state") == "simulated", "Bedrock is not reported as simulated"
        assert not providers.get("cost_explorer", {}).get("enabled"), "Cost Explorer must be disabled in demo"

        status_code, ready = request_json(f"{origin}/api/health/ready")
        assert status_code == 200 and ready.get("status") == "ready", f"readiness failed: {ready}"
        assert ready.get("checks", {}).get("database") == "connected", "demo database is not ready"

        status_code, scenarios = request_json(f"{origin}/api/demo/scenarios")
        assert status_code == 200 and isinstance(scenarios, list) and scenarios, "scenarios route returned no scenarios"

        preflight = Request(
            f"{origin}/api/demo/scenarios",
            method="OPTIONS",
            headers={
                "Origin": args.frontend_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        with urlopen(preflight, timeout=30) as response:
            assert response.status == 200, f"CORS preflight returned {response.status}"
            assert response.headers.get("Access-Control-Allow-Origin") == args.frontend_origin
            assert "GET" in response.headers.get("Access-Control-Allow-Methods", "")
            allowed_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()
            assert "authorization" in allowed_headers and "content-type" in allowed_headers

        rejected = Request(
            f"{origin}/api/demo/scenarios",
            method="OPTIONS",
            headers={
                "Origin": "https://unapproved.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )
        try:
            with urlopen(rejected, timeout=30) as response:
                assert "Access-Control-Allow-Origin" not in response.headers
        except HTTPError as error:
            assert "Access-Control-Allow-Origin" not in error.headers

    except (AssertionError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"Deployment smoke check failed: {error}", file=sys.stderr)
        return 1

    print("Deployment smoke check passed: demo health, readiness, scenarios, and CORS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
