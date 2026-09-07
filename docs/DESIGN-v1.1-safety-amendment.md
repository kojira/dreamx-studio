# v1.1 safety amendment — requires user approval before model inference

Issue #1. v1 remains the implemented base; this amendment replaces its memory accounting acceptance gate only. It is NOT approved yet.

## Observed limitation
A bounded 128MiB GPU allocation increased cgroup memory.current by approximately72MiB. Concurrent allocator effects mean this is not a precise measure of uncharged GPU memory, but full accounting is not verified. Therefore Docker memory limits cannot be asserted to protect host RAM. No model weights have been loaded.

## Proposed revised safety contract
- Treat Docker/cgroup limits as a secondary CPU-memory guard, not a GPU RAM ceiling.
- Keep independent host guardian outside inference cgroup and actual MemAvailable as the primary signal.
- Raise host emergency threshold from32GiB to48GiB; stop the exact worker immediately on first below-threshold sample. Baseline admission remains96GiB.
- Sample host RAM every100ms; also stop when its measured one-second consumption rate projects availability below48GiB within the next two seconds. No artificial host-OOM test.
- Lower worker memory and memory+swap caps from80GiB to64GiB; cgroup stop threshold from72GiB to56GiB. If this prevents loading, stop and report; do not automatically raise budgets.
- Verified stale guardian/runner heartbeat abort remains. External SSH probe remains additional observation, not the only stop path.
- Run only fixed 220-token/21-frame/4-step smoke case first; evaluate peak and minimum available memory before enabling69-frame trial. No 2K, parallel work or automatic retries.
- This reduces risk but cannot guarantee SSH survival: a rapid unaccounted GPU allocation can race polling and termination. Explicit user acceptance of this residual risk is required.

## Unchanged
Preserve all other containers, datasets and drivers. No privileged containers or destructive cleanup. Simple browser trial UI is sufficient; postpone polish. Containerized API/UI plus isolated per-job inference. Secure local SSH-forwarded access. No public ingress.

## Gate
Before any model inference: approval of this amendment, revised unit tests, real harmless heartbeat/kill tests, cgroup limit verification and fresh host resource check. If rejected, remain read-only/non-inference and discuss alternatives rather than running unprotected.
