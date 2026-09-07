# v1.5 — predictive guard persistence (approval requested)

Not approved; no guard behavior change or automatic retry until user confirms.

## Evidence
Approved880-token same-input/prompt/resolved-seed trial stopped with PROJECTED_MEMORY_GUARD. Exit137, OOMKilled=false. At recorded abort host available68.346GiB, cgroup19.367GiB. Sampled peak cgroup32.955GiB/min host available68.773GiB. No completed880 video. This does not prove880 fits; it shows the prediction gate stopped before absolute48GiB threshold.

## Proposed bounded change
Keep100ms sampling, existing one-second consumption-rate window and two-second projection. A projected breach must remain continuously true for at least1.0 second before requesting a kill. Reset that timer as soon as projected breach clears, when job changes or when idle. Use monotonic time; do not count sample number as elapsed time.

Host available below48GiB still requests an immediate kill on the first sample, independently of the predictive timer. Cgroup72GiB threshold, worker80GiB/no swap cap, heartbeat failure, one-job lock, admission96GiB and timeout remain unchanged. No dependency, driver, model or UI range changes.

## Tradeoff / validation
This tolerates transient allocations but delays predictive intervention by up to1 second; absolute/heartbeat guards still act immediately. SSH survival is not guaranteed. Tests must show short projected bursts do not kill, sustained >=1s breach does, and absolute shortage overrides the timer immediately. Deploy only without an active user job and with overlapping verified guardian health. Retry the same880 comparison only after approval and fresh preflight, one job, independent SSH probe; no further automatic relaxation.
