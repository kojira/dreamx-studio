# Refiner test v1.2 — memory-mapped checkpoint load

PAUSED, NOT IMPLEMENTED. After the user's objection to the residual72GiB stop, first resolve the memory-policy inconsistency rather than substituting a loader optimization for that decision. No mmap patch or retry has been performed. This document is a retained candidate, not an approved next action.

The v1.1 GPU primitive test passed, but full trial stopped during SR-DiT checkpoint loading: WORKER_MEMORY_GUARD, exit137, OOMKilled=false, ~55.34GiB actual host availability at abort. Keep72GiB cgroup guard,80GiB/no-swap cap,24GiB host threshold and180minute timeout unchanged.

In an isolated, read-only mounted copy of pinned inference_sr.py, change only `torch.load(args.checkpoint_path, map_location="cpu", weights_only=False)` to include `mmap=True`. Source SHA256 must match17410e170dc6c42d098668478da226fa48a98678ab1e628202988cf204d2415d. The verified checkpoint has ZIP header504b0304, the format required by torch.load mmap. Existing state-dict validation, strict load and deletion of temporary references remain unchanged. This defers loading checkpoint tensor storage until accessed rather than eagerly duplicating it in anonymous RAM; no parameter-value or dtype change. It is not a guarantee of fitting later stages.

Keep the approved v1.1 dense-attention fallback. No change to Triton/window geometry or models. CPU tiny-fixture test must show identical state-dict tensors with and without mmap. One new trial identity/output; preserve earlier failures. GPU smoke still runs within the guarded job. Same source,69frames/24fps,2x target, seed42, default refiner settings and output checks. No automatic retries or policy changes on another failure.
