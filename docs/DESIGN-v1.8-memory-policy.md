# v1.8 — align memory policy (proposal, not deployed)

## Evidence and approval boundary
User challenged the residual72GiB stop after being told host availability24GiB was the operative reserve. The v1.1 Refiner trial exited137/OOMKilled=false due to WORKER_MEMORY_GUARD while host availability was55.34GiB. This is not evidence of actual host exhaustion. The mmap candidate is paused, not implemented. This amendment changes safety policy, unlike the previously authorized limited library-compatibility fix, and requires explicit user confirmation.

## Proposed policy
- Remove the72GiB cgroup-usage-triggered kill entirely from both host_guard.sample_guard and safety.emergency. Continue recording cgroup usage as telemetry.
- Keep the host MemAvailable<24GiB stop at100ms, independent guardian,2second heartbeat fail-closed behavior, telemetry failure stop, exact-job cancellation, admission96GiB/free disk150GiB and180minute timeout.
- Raise Docker memory and memory+swap caps together from80GiB to112GiB. This is a last-resort cgroup ceiling, not a memory-reserve setting; swap remains prohibited.112GiB is above the nominal host119GiB minus24GiB reserve budget, so the primary host guard should act first for non-reclaimable allocations. Sampling and GPU accounting races mean24GiB remaining cannot be guaranteed.
- Do not claim memory.current measures unreclaimable RAM. It includes reclaimable charges; their contribution to this particular abort was not sampled, so do not invent a cache breakdown.
- No predictive stop, no additional hidden intermediate threshold, no relaxation on a further failure without review.

## Scope and validation
One shared cap constant drives Docker creation and verification in both base host_runner and refiner_test_host; docker_control and cgroup checks must agree. Update emergency/host guard tests: high cgroup usage alone does not request a kill, host availability below24GiB does, stale telemetry/heartbeats still stop. Confirm112GiB cap and zero swap from actual cgroup and Docker inspect on a harmless handshake-only container before inference. Do not stress the host to validate these thresholds; synthetic readings exercise low-memory branches.

Deploy/restart host components only after verifying no active base or operator test job. Preserve original data and known container identities. Any required socket reconciliation must identify the exact owned socket and stopped runner, with itemized dry-run before removal; no broad cleanup. Record deployed processes/commit and verify fresh guardian before permitting inference.

After approval and verification, retry Refiner once with the existing approved SDPA patch, unchanged source clip/default2x settings, new job/output identity, NO mmap modification. Record state, true GPU utilization/progress, min host available, cgroup peak and output validation. If elapsed reaches120minutes, consult well before180minute deadline. No manual stop merely because processing is slow.
