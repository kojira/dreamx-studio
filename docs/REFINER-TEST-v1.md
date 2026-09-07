# Refiner standalone test v1

## Authorization and scope
User explicitly instructed testing the Refiner before UI design and using the previously generated clip. This is an operator-only compatibility/output test, not approval for frontend integration. Issue#1 tracks this scope. Original input and generated base output remain untouched.

## CPU prerequisite stage
Pinned upstream/model revisions remain those already deployed. Existing runtime lacks peft and ftfy. Install peft0.17.1 and ftfy6.3.1 into a NEW, isolated directory (CPU import test identified missing ftfy dependency; add wcwidth0.2.13 to that same isolated directory), without dependency upgrades or modifications to the generator image/environment. Import-check compatibility before GPU work. If transitive dependencies are missing or imports fail, record specifics and resolve the test environment explicitly; do not silently upgrade torch, CUDA, transformers or host drivers.

## GPU test contract
Use successful880 H264/AAC clip (1248x704,69frames,24fps), read-only. First test official default2x refinement (2496x1408), preserving all69frames and audio. Exact1080p formatting/UI are subsequent work, not part of this test. Standard latent upsampler, BF16, KV9, sigma0.6251, default Triton window attention; no FP8/LightVAE, no speculative backend substitution. Pin seed42 and upstream default refinement prompt; avoid publishing prompts/filenames derived from private input.

Before launch, atomically reserve the shared inference slot so a UI generation cannot race the test. Do not stop a user's active job. Use a dedicated host test supervisor/control directory with the same independent host guardian and child heartbeat/go handshake. The existing UI/runner must not be restarted or have its control state overwritten. Operator test cancellation targets only the exact labeled test container; UI cancellation is not claimed to control this separate test.

Admission96GiB available and150GiB free disk. Container80GiB/no swap, cgroup stop72GiB, host actual available below24GiB,100ms sampling, guardian/runner stale >2seconds fail closed,180minutes from original start. Check GPU utilization alongside true progress. No cancellation merely for slowness; seek a user decision before120minutes if necessary. No automatic retries.

Output goes to a new private per-test directory, with read-only weights/source clip and no network/GPU model concurrency. Retain logs, resource samples, exact image and argv, source checksum, and ffprobe evidence. Only release the shared slot after confirming exact worker exit. Supervisor failure must leave reservation locked until reconciliation; do not falsely report success.

## Recorded first-trial result

Failed at the upstream missing-FlashAttention assertion (exit1, OOMKilled=false), not a manual interruption or memory-guard event. Container runtime117.695seconds;229 resource samples, minimum host availability31.870GiB, maximum cgroup65.954GiB, no sampled guard reason. This does NOT establish that later refinement/decoding stages fit in memory. Preserve all safety limits on any approved retry. The proposed compatibility remedy is in `REFINER-TEST-v1.1-sdpa.md`; approval is outstanding, no patch or retry has been performed.

## Acceptance
Verify valid playable video,2496x1408 dimensions,69frames/24fps, duration within one frame of source, audio retained and source checksum unchanged. Record elapsed time, minimum sampled host available RAM and maximum cgroup usage, exit/OOM status. A valid output does not establish visual improvement; provide result for user evaluation. Any output/frame/audio mismatch is a test failure, not something to silently trim or conceal.
