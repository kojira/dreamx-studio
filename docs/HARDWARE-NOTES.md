# GB10 validation notes

## Upstream reports
A search of upstream GitHub issues, Hugging Face discussions and NVIDIA forums found no specific published DreamX-Creator-on-GB10 memory/runtime report. This is a search result, not proof that nobody has run it.

- https://github.com/AMAP-ML/DreamX-Creator/issues
- https://huggingface.co/GD-ML/DreamX-Creator/discussions
- https://forums.developer.nvidia.com/c/accelerated-computing/dgx-spark-gb10/719

Related, not identical, GEMM error reports:
- https://github.com/pytorch/pytorch/issues/174949
- https://github.com/vllm-project/vllm/issues/35028

Do not extrapolate a fix from other hardware or replace host drivers without approval.

## Observed here
Pinned torch2.10.0+cu130/torchvision0.25.0+cu130/torchaudio2.10.0+cu130 ARM64 wheels installed successfully. Tiny BF16 SDPA passed. Torch reports capability12.1 hardware versus maximum12.0 in its warning; this warning alone is not a measured model failure.

The initial container mixed `/opt/venv/lib/python3.12/site-packages/nvidia/cu13/lib/libcublas.so.13` (package13.1.0.3) with `/usr/local/cuda-13.0/targets/sbsa-linux/lib/libcublasLt.so.13.0.0.19`. BF16 `F.linear` on tensors[512,4096] and[4096,4096] reproduced CUBLAS_STATUS_INVALID_VALUE without model weights.

Prioritizing the installed PyTorch dependency directory in LD_LIBRARY_PATH caused BOTH cuBLAS libraries to load from the matching packaged directory, and the exact BF16 linear probe passed. No dependency versions or host driver changed. Runtime Dockerfile encodes the matching library priority; future compatibility probe includes GEMM, not SDPA alone.

## Memory evidence
128MiB GPU allocation caused approximately72MiB cgroup increase; allocator interactions can confound this measurement. Complete GPU cgroup accounting is NOT verified.

Initial64GiB-capped smoke stopped during model loading near56GiB cgroup usage, with host MemAvailable >=86.8GiB in sampled evidence. OOMKilled=false. SSH responses sampled around0.35–0.48s. No video generated. Failed-state reconciliation required a fix for competing exact-job kill attempts between guardian and runner; kill is now idempotent only after fresh stopped-state verification.

User then allowed restoring worker80GiB/cgroup guard72GiB, while retaining host reserve48GiB,100ms monitor and projected stop. The next attempt loaded the model but hit the cuBLAS mixed-library failure described above. No output success claim is made for either attempt.

## Deployment boundary
Dedicated runtime/UI containers only. Independent host guardian has passed a real harmless-container runner-heartbeat-loss test. Low-host-memory injection also killed only its exact harmless test container. No actual host OOM testing or unrelated service restarts. All GPU smoke tests remain behind admission/guardian checks.
