# Repository audit and repair log

Audit date: 2026-10-26

Repository: `TechnoKhushal/Cloudcostsentinel`
Starting revision: `43df07d23ea2c5262d34079926454d2db59b78c2` (`main`)

## Findings and work

| Severity | Finding and evidence | Repair | Regression evidence | Status |
| --- | --- | --- | --- | --- |
| P2 | Deployment guides still named `codex/repair-vercel-render-connectivity` as the Render branch after it had been merged and deleted. `git branch -a` and `git ls-remote --heads origin` show only `main`; the branch guidance was stale in `docs/DEMO_DEPLOYMENT.md` and `docs/DEPLOYMENT_VERCEL_RENDER.md`. | Updated both guides to `main` and documented that Render dashboard configuration cannot be inspected from this checkout. | Rechecked repository branch inventory and searched both guides for branch instructions. | Fixed |
| P2 | The container frontend builder used Node 20 while CI uses Node 24; the README described a broad Node 20+ range. Vite 8's lockfile engine requirement is `^20.19.0 || >=22.12.0`, so versions below that are incompatible. | Aligned Docker and the documented quickstart with Node 24, matching CI. | `npm ci`, 20 frontend tests, lint, and production build pass on Node 24. | Fixed |
| P2 | The audit lacked a current production-readiness record despite deployment dashboard revisions, persistent storage, and production authentication being unverified. | Added [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) with current evidence, exact demo configuration, and remaining release gates. | Live HTTP and browser observations recorded there; unavailable dashboard facts are marked unverified. | Fixed (documentation) |
| P2 | Live Vercel response had `X-Frame-Options: DENY` and `nosniff`, but no Content Security Policy. | Added a restrictive CSP allowing same-origin frontend assets and only the configured Render API for connections. | Verify the deployed CSP header and browser console after Vercel redeploy. | Fixed (deployment verification pending) |
| P1 | Dependency audits flagged `mcp==2.1.1` (`CVE-2026-59951`) and the clean venv's `setuptools==65.5.0` against multiple advisories, including `GHSA-xmj3-9gf7-h52w`. | Constrained MCP to the patched compatible 1.x line (`mcp>=1.30.0,<2.0.0`), required `setuptools>=84.1.0`, and added `pip-audit -r requirements.txt` to CI. | Requirements and full installed-environment pip-audit both report no known vulnerabilities after upgrade; backend and pattern suites pass with MCP 1.30.0/setuptools 84.2.1. | Fixed |
| P2 | The historical hardening log contains test results from an earlier environment that are no longer current. | Added this dated audit record; use it and `PRODUCTION_READINESS.md` for this revision's evidence. | Clean local backend/frontend commands and current GitHub Actions run recorded below. | Fixed (documentation) |
| P3 | The production Vite bundle is 626.29 kB minified and Vite reports a chunk-size advisory. It is not a build failure and the current dashboard loads in the browser. | No code split introduced during this reliability audit; track as a measured performance follow-up rather than risk changing a working page without a specific user flow benefit. | Clean Vite build and live page render succeeded. | Deferred |

## Existing controls verified

- The source includes a single-transition approval update guarded by a conditional SQLite update and checks `rowcount`; backend regression tests cover conflicts/concurrency.
- The frontend has a typed API client, bounded requests, retryable resource errors, visible simulated-provider state, approval filters, and CSV export with formula-injection protection.
- Demo startup is independent from the standalone model server. The demo path uses synthetic inputs and rejects real Cost Explorer/custom anomaly inputs.
- Repository contains no `render.yaml`; the Render setup is dashboard-managed. Vercel's frontend configuration is in `frontend/vercel.json`.
- `DATABASE_URL` is rejected because this repository uses SQLite; demo storage on `/tmp` is ephemeral.

## Verification record

- Starting tree was clean; local and fetched `origin/main` both pointed to `43df07d23ea2c5262d34079926454d2db59b78c2` before these audit changes. The only advertised remote branch was `main`.
- Current GitHub Actions run for the starting merge commit: [40364128369](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40364128369), completed successfully (backend and frontend jobs).
- Earlier runs [40003922854](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40003922854), [40019931421](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40019931421), [40020275888](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40020275888), and [40020470191](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40020470191) had failing checks; run/check metadata exposes only failed job steps and generic `Process completed with exit code 1` annotations. Raw log downloads for all four returned HTTP 403 (`Must have admin rights to Repository`). The specific failed assertions/tracebacks are therefore unavailable and are not inferred.
- Clean backend venv (`.tmp/audit-venv`, Python 3.11.9): `python -m compileall -q backend patterns scripts tests` passed; `pytest -vv tests/test_backend.py` passed 44/44; `pytest -vv patterns/threshold_aware_anomaly_response/test_pattern.py` passed 5/5; standalone pattern example exited 0 and labeled providers `mock-simulated`.
- `pip-audit -r requirements.txt --timeout 15` and `pip-audit --local --timeout 10` both passed after the MCP and setuptools constraints; both reported no known vulnerabilities.
- Clean frontend install (Node 24.21.0, npm 11.19.0): `npm ci` succeeded with 0 reported vulnerabilities; `npm test` passed 20/20; `npm run lint` passed; `npm run build` passed with a non-failing 626.29 kB minified chunk advisory.
- Docker image build was attempted because Docker is a supported path; Docker CLI exists, but the Docker Desktop Linux engine was not running (`npipe ... dockerDesktopLinuxEngine: The system cannot find the file specified`). Image build/runtime verification is unavailable until the daemon is started.
- Live checks on 2026-10-26: Render `/api/health/live` 200; `/api/health/ready` 200 (`ready`, `demo`, SQLite `connected`, mock providers `simulated`); `/api/demo/scenarios` 200; preflight from `https://cloudcostsentinel.vercel.app` 200 with matching `Access-Control-Allow-Origin`; Vercel homepage 200.
- Browser check: public Vercel dashboard rendered with API connected, synthetic demo label, five scenarios, populated analysis/report/decision and review history. Approval All + search filter returned matching rows; the browser console returned no errors or warnings.
- Local clean install/check outcomes are recorded in `PRODUCTION_READINESS.md` after completion.

## Change review

This audit changes deployment guidance, aligns the Docker frontend builder's Node version with CI, and constrains vulnerable dependencies with a new CI audit gate. No API keys, `.env` files, databases, built bundles, or dependency directories are intended for commit.
