# v1.6 — actual available-memory guard

User requested usable operation after the parent explicitly proposed removing prediction and stopping only below24GiB host availability. Latest instruction: 「早くまともに使えるようにして」. This revision implements that instruction. It supersedes the unapproved v1.5 proposal; no further prediction tuning.

## Exact change
Remove projected-consumption stopping entirely. Sample actual host MemAvailable every100ms and stop the exact worker if below24GiB (24GiB itself is allowed). Retain worker80GiB/no-swap cap, cgroup72GiB stop,96GiB admission, one active job, heartbeat/telemetry fail-closed handling and one-hour timeout. No driver, model, dependency or resolution changes. Rapid GPU allocations can still race monitoring;24GiB is a stop threshold, not a guaranteed retained minimum.

## Verification/deployment
Test24GiB boundary and that large but above-threshold availability changes do not trigger prediction. Verify idle before guardian replacement; start/verify new independent guardian before stopping old to avoid a protection gap. Retry the same880 input/prompt/resolved-seed comparison with SSH observation; no automatic further relaxation. Preserve UI, data, images and other containers. Record actual result and memory measurements, not a promise of improved quality.
