# Refiner test v1.1 — narrow missing-FlashAttention fallback

Status: proposed, awaiting explicit user approval. No patch applied, no retry launched.

## Failure and bounded remedy
Pinned upstream `video_refiner/wan/modules/sr_dit/attention.py:flash_attention` advertises FA3/FA2/PyTorch SDPA dispatch, but chooses SDPA only on CPU or head dimension>256. CUDA+head128 with no external FlashAttention reaches `assert FLASH_ATTN_2_AVAILABLE`. The observed failure is dense cross-attention, after successful model loading. `models.py` initializes context_lens=None for this path.

Proposed: in a test-only copy of this single upstream file, also select its existing SDPA branch when both external FA2 and FA3 are unavailable. For this newly handled case, reject non-default options instead of silently discarding them: q_lens/k_lens must beNone, q_scale/softmax_scale must beNone, causal=False, window_size=(-1,-1), dropout_p=0, deterministic=False. Any unsupported call fails with an explicit error for review. Preserve BF16/default dtype behavior and output shape. Leave original fallback behavior and available-FlashAttention branches unchanged.

Do not substitute the window self-attention implementation: official Triton block-grid attention remains in use. No torch/CUDA/transformers/driver changes, no extra accelerator installation. SDPA computes the same unmasked dense-attention operation but numerical equality to FlashAttention is not guaranteed. Do not claim visual equivalence before reviewing output.

## Isolation, tests, retry
Keep source/model revisions pinned; record original and patched source hashes and exact replacement. Bind only the patched attention.py read-only into a dedicated new trial container; do not alter the base generator image or running service files. Validate original source hash before patching. CPU unit tests: no FA present selects fallback; available FA preserves path; unsupported options reject; BF16 shape/finite output on a tiny tensor. On-device tiny SDPA smoke before full Refiner retry.

After approval, manually launch one new reserved trial using the same source video, standard2x settings and seeds. All shared-job locking, heartbeat/host memory/cgroup guards and180-minute budget from Refiner test v1 remain. Preserve failed-trial data; new job/output/idempotency identities, no deletion or automatic further fallback. Verify original checksum,69frames/24fps,2496x1408 output, unchanged audio stream and runtime/resource evidence.

Alternative: compile/install external FlashAttention2 into a dedicated runtime. Not selected: additional GB10/ARM64 CUDA build compatibility surface and build time, while the upstream already contains an appropriate SDPA implementation for the observed unmasked call.
