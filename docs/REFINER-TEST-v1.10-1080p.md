# Refiner test v1.10 — requested1080p output

User requested1080p rather than2K, directed testing with the existing generated video, and authorized bounded compatibility work. After2x processing completed6/6 chunks but fell below24GiB available during subsequent work, test the requested lower resolution instead. This is still an operator test, not UI integration. No safety relaxation.

Input is exactly the previous1248x704,69frames/24fps H264/AAC clip, read-only. Use the same model, seed42, BF16, Triton window attention and approved missing-FlashAttention SDPA patch. No mmap, FP8, LightVAE, frame truncation or temporal change.

For this input only, set official SR_SCALE=1088/704. Upstream round-to32 yields1920x1088 (assert this on raw output). The learned latent upsampler is fixed2x: upstream resizes its LR input to960x544 before processing, so this is NOT a separately trained1.5x model. This may affect fidelity; success requires user visual review, not merely larger dimensions.

After worker exit, use host FFmpeg with bounded120second timeout to scale the internal output to1914x1080 with Lanczos (closest even width to1248*1080/704), center-pad black to1920x1080, SAR1. Encode libx264 CRF18/preset fast/yuv420p and stream-copy first audio track. Keep raw output separately. This approximately restores original aspect ratio after upstream's32-pixel rounding; narrow padding rather than cropping. Never overwrite original video.

Validate raw1920x1088, final1920x1080,69frames/24fps, duration within1frame, original unchanged checksum, identical audio stream hash. Preserve private logs/artifacts and resource/elapsed evidence. Use a distinct v1.10 idempotency identity and normal shared-job exclusion. v1.9 actual24GiB/zero-swap/heartbeat/180minute policy remains; no Docker RAM ceiling and no automatic retries.
