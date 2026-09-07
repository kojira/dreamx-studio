# Implementation checkpoint

Issue #1, approved design v1. Branch feat/dreamx-studio-v1.

## Done
- Documentation baseline and workflow rules.
- Pure safety policy: admission thresholds, host/worker emergency thresholds, guardian heartbeat handling, fail-closed telemetry, exact container ID validation.
- Four unittest cases (including boundary subcases) pass: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v`.

## Not yet done / safe next actions
1. Implement independent host guardian and job-scoped lifecycle controller, exercise kill and stale heartbeat on harmless bounded workers.
2. API/auth/upload validation/SQLite lifecycle and tests.
3. React frontend, frontend tests/build.
4. Dedicated runtime compatibility probe on approved target; no inference until safety evidence exists.
5. Model file size preflight/download and staged measured smoke/usable generation, then user verification.

No runtime installed, weights downloaded or inference executed. Pure policy tests are NOT proof that host SSH is protected under GPU load. Two earlier delegated sessions stopped due to extension session replacement before implementation; parent is now implementing directly. Keep checkpoint current across heartbeat recovery. Do not create PR before explicit user test approval.
