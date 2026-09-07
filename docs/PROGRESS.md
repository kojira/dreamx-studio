# Implementation checkpoint

Issue #1, approved design v1. Branch feat/dreamx-studio-v1.

## Done
- Documentation baseline and workflow rules.
- Pure safety policy: admission thresholds, host/worker emergency thresholds, guardian heartbeat handling, fail-closed telemetry, exact container ID validation.
- Guard-loop primitive handles job-specific emergency kill, sensor failure, 60-minute timeout and kill failure without reporting false success. Not yet wired to a deployed independent supervisor.
- SQLite single-active job transaction/index, idempotency, transitions and explicit restart recovery; session/origin/CSRF primitives; exact-job Docker ownership and limits validation.
- 21 unittest cases pass: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v`.
- Dedicated CUDA13 ARM64 Docker runtime built on target; upstream pinned requirements install and pip check pass. Tiny BF16 SDPA on GB10 passes; PyTorch reports capability support range warning (12.1 hardware versus advertised maximum12.0), so full model compatibility is not established.
- Non-root probe needed USER/HOME/cache environment because host UID is absent from container passwd; no root workaround used. Dockerfile includes correction; currently built image needs rebuild with it (probe supplied equivalent env explicitly).
- Upstream inference.py --help imports successfully. No weights loaded.
- Base weights download running in dedicated container, 8GiB RAM/no swap/2CPU, no GPU. 16 files / 43,177,935,990 bytes at HF revision 10fb869a92dd45659f38fdc2bb74c8ef0ba7bf7c. Refiner excluded. Need confirm exit/size verification before using.

## Not yet done / safe next actions
1. Implement independent host guardian and job-scoped lifecycle controller, exercise kill and stale heartbeat on harmless bounded workers.
2. API/auth/upload validation/SQLite lifecycle and tests.
3. React frontend, frontend tests/build.
4. Dedicated runtime compatibility probe on approved target; no inference until safety evidence exists.
5. Model file size preflight/download and staged measured smoke/usable generation, then user verification.

No model inference executed. Runtime/weights progress above. Pure policy tests are NOT proof that host SSH is protected under GPU load. Two earlier delegated sessions stopped due to extension session replacement before implementation; parent is now implementing directly. User requested a minimal trial UI rather than production polish; retain safety gates and containerization, prioritize usable generation. Keep checkpoint current across heartbeat recovery. Do not create PR before explicit user test approval.
