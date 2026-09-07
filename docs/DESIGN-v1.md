# DreamX Studio detailed design v1 — approval requested

Issue: https://github.com/kojira/dreamx-studio/issues/1
Status: NOT APPROVED. No implementation branch or inference execution until explicit approval of v1.

## Scope and immutable boundaries
Browser frontend for first-frame image + prompt → synchronized audio/video using DreamX-Creator. Preserve existing host drivers, SSH, containers and data. Public repo must not contain private addresses, credentials, prompts, inputs, generated media or resolved secret-bearing configs. Runtime and storage are separate from existing deployments. No host reboot, Docker daemon restart, privileged containers, automatic deletion or replacement of existing environments.

v1 delivers base generation. Optional 2K refinement is NOT enabled in v1: separate design revision and memory validation required. UI explicitly labels it unavailable rather than pretending it works.

## Evidence / upstream pin
AMAP-ML/DreamX-Creator commit `215d4cd7fbed7e161ab508ae1f85a8fee0536f62`.
- https://github.com/AMAP-ML/DreamX-Creator/blob/215d4cd7fbed7e161ab508ae1f85a8fee0536f62/audio_video_generation/README.md
- https://github.com/AMAP-ML/DreamX-Creator/blob/215d4cd7fbed7e161ab508ae1f85a8fee0536f62/audio_video_generation/inference.py
- https://github.com/AMAP-ML/DreamX-Creator/blob/215d4cd7fbed7e161ab508ae1f85a8fee0536f62/audio_video_generation/requirements.txt
- https://github.com/AMAP-ML/DreamX-Creator/blob/215d4cd7fbed7e161ab508ae1f85a8fee0536f62/checkpoints/README.md
- Weights: https://huggingface.co/GD-ML/DreamX-Creator
Official defaults: 880 spatial tokens, 5 seconds, 24 fps, 50 steps. Frame count rounds down to 4n+1. Dependencies pin torch 2.10.0, torchvision 0.25.0, torchaudio 2.10.0; optional attention kernels are not mandatory (SDPA fallback).

## Hardware and hard stop conditions
Observed GB10 / ARM64, about 119 GiB unified RAM, initially 109 GiB available; about 685 GiB free disk. Neither peak model RAM nor compatibility has been measured. CPU offload shares the same physical memory and is not additional capacity.
Before any inference, validate ARM64 CUDA-capable wheels matching upstream requirements and host driver, BF16 tensor execution and SDPA on GB10. Record exact versions and image digest. If the pinned stack cannot run, stop and propose a design revision; no silent downgrade, driver replacement or custom attention dependency.

All budgets below are proposed conservative gates, NOT guarantees against host OOM. GPU/unified-memory allocations may not be completely cgroup-accounted. If independent kill monitoring and accounting cannot be verified, inference remains disabled.

## Deployment
FastAPI/Python API plus React/TypeScript/Vite static frontend served at the same origin. Separate one-job inference container, GPU access but no Docker socket inside it. Host-side runner and memory guardian owned by the SSH user; server/guardian never share the inference cgroup. Bind web listener only to 127.0.0.1:8780 (confirmed free during read-only inspection), not 0.0.0.0 or a network interface. Browser access in v1 uses an SSH local forward over Tailscale: `ssh -N -L 127.0.0.1:8780:127.0.0.1:8780 <configured-ssh-target>`, then http://127.0.0.1:8780. If the Mac port is occupied, stop and ask rather than replacing an existing listener. No public ingress, Tailscale Serve/Funnel setup or change to tailnet ACLs. API and host runner communicate over a mode-0600 Unix socket; client cannot submit Docker options or paths.

Dedicated application root `~/dreamx-studio-runtime`, mode 0700. Subdirectories config, weights, inputs, jobs, logs, evidence. Never reuse unrelated directories. Weights mounted read-only; per-job input read-only and per-job output writable. Container runs as host user's UID, no privileged mode, no host PID namespace. Docker logs capped at 10m × 3. No automatic host startup until acceptance; provide explicit start/stop procedures.

## Memory / SSH protection
- One inference globally; no pending queue. Second concurrent request receives 409 BUSY.
- Admission: MemAvailable >= 96 GiB, disk free >= 150 GiB; valid active guardian heartbeat less than 2 seconds old; runtime ready. Otherwise 503 RESOURCE_UNAVAILABLE with measured reason.
- Worker container cap 80 GiB; memory+swap cap also 80 GiB (no worker swap). Verify cgroup settings, don't assume GPU accounting coverage.
- Independent host guardian samples MemAvailable every 250 ms and worker cgroup memory where available. Stops admission and kills ONLY the exact active job container when host availability falls below 32 GiB or worker cgroup usage reaches 72 GiB. Do not wait for the nominal 24 GiB host reserve to be exhausted.
- Normal cancel: TERM to inference, 5-second grace then exact container kill. Memory emergency: immediate exact container kill. Record reason and measurements. No shell expansion / broad process-name killing.
- Runner checks guardian heartbeat every 500 ms; stale >2 seconds terminates current worker and disables new work. Inference maximum wall time 60 minutes. Docker restart policy `no`, no automatic OOM retry.
- First test guardian using injected readings and a harmless bounded process, NOT actual host memory exhaustion. Parallel independent SSH probe records responsiveness during inference. Missing two 2-second probes asks the existing host guardian to abort; lack of remote SSH is not the sole safety mechanism.
- Save 1-second resource samples (host available, swap, worker cgroup, Torch allocated/reserved if supported) and stage timings. Unsupported nvidia-smi memory metrics shown as unavailable.

## Presets and rollout
Fixed test preset: 220 spatial tokens, requested 1 second / 24 fps → 21 frames, 4 steps, BF16, SDPA, text/VAE CPU offload. This is a smoke test, not quality evidence.
First usable preset: 220 tokens, requested 3 seconds / 24 fps → 69 frames, 50 steps, same dtype and offload. UI duration is actual frame count / fps, not the rounded requested duration.
No arbitrary resolution/frame/steps input. After safe tests, only this initial usable preset is enabled. If upstream fails at these shapes or memory gates, stop for design revision. Larger/official presets and 2K need subsequent measured approval.
Do not simultaneously load refiner and generator. Worker exits after every job, releasing model memory.

## Frontend responsibilities
Responsive single-user Japanese UI: resource status/banner, upload preview, prompt textarea, seed field, named fixed preset, generate button; current job phase/elapsed time/cancel; history list; MP4 playback and MP4/WAV downloads. Never invent percentage progress or ETA: phase only unless upstream provides confirmed step count. Inputs stay editable but submit disabled during active job. Surface validation, resource refusal, model-not-ready and failed/cancelled/interrupted states separately. Show low-quality smoke preset only in diagnostics, not as normal generation.

## Auth / uploads
All tailnet users with access are not implicitly authorized. Random >=32-byte local access secret, not committed. Login exchanges secret for HttpOnly SameSite=Strict session cookie; verify Origin on modifying requests plus CSRF token. Browser access uses the SSH localhost tunnel exclusively in v1. Secret and session travel over loopback and the encrypted SSH connection. Cookie uses HttpOnly, SameSite=Strict and Path=/; Secure is not used on this HTTP-loopback-only deployment. Accept only the configured localhost Host and Origin; reject all non-loopback browser origins, do not enable CORS. Login rate limit: 5 failed attempts per minute, request size <=4 KiB; session lifetime 8 hours, restart invalidates sessions; secret supplied through a local protected config, never URL query strings.
No remote URL fetching. JPEG/PNG/WebP only, <=10 MiB and <=16 megapixels; decode/re-encode, reject animated/malformed/decompression-bomb images and unsupported formats. Limit request body at server; strip metadata. Prompt 1–4000 characters, seed 0–2147483647 or server-generated. Filenames and paths assigned by server UUID, never trust client paths. Commands use argv arrays with shell=False. Downloads are UUID-and-fixed-artifact-name lookups contained under job root, authenticated, with no symlink traversal.

## API and persistence
SQLite jobs DB in dedicated data root. Job record: UUID, timestamps, state, phase, input UUID, prompt, seed, fixed preset/version, upstream revision, runtime digest, resource summary, error code, artifact metadata. Private prompt/media not emitted to shared logs.
- POST /api/session (secret) → session; DELETE /api/session logout.
- GET /api/status → runtime readiness, active job ID, available RAM/disk, reason inference disabled.
- POST /api/inputs multipart image → 201 {input_id,width,height}; 413 size, 422 validation.
- POST /api/jobs JSON {input_id,prompt,seed,preset} → 202 {job_id,state}; transaction-protected active slot; 409 busy, 422 invalid, 503 resource/runtime refusal. Request ID prevents duplicate creation on retry.
- GET /api/jobs (paged, 20/page), GET /api/jobs/{id}: poll every 2 seconds while active.
- POST /api/jobs/{id}/cancel idempotent, 202 while stopping, 200 if terminal.
- GET /api/jobs/{id}/artifacts/{mp4|wav|first_frame}: authenticated stream with range support for MP4, ready state only.
No deletion endpoint in v1. No automatic cleanup. Disk limit refusal prevents uncontrolled retention. Manual cleanup requires itemized dry run and explicit user approval.

States: admitted → preparing → generating → muxing → succeeded; any active state → cancelling → cancelled; resource stop → failed(resource_guard); exception → failed; service restart with previously active job → interrupted. No automatic retry. Atomic finalize after ffprobe confirms video and audio streams, nonempty media and duration tolerance <=one video frame. Retain partial files private for diagnosis, never serve as successful artifacts. Release job lock in all terminal paths.

## Changes / validation
New frontend, backend, host runner/guardian, isolated runtime build recipe, deployment runbook and AGENTS instructions in kojira/dreamx-studio. No edits to upstream except separately reviewed compatibility patches requiring revision.
Tests: input boundary/security/path traversal, auth/CSRF, concurrency/idempotency, transitions/restart recovery, resource admission and injected emergency/stale heartbeat, cancel escalation, media validation/range, permission isolation and no unrelated container changes. Verify budgets without real host OOM.
Hardware acceptance: smoke then initial usable preset, audio/video playback, resource logs, independent SSH probe, no other container ID/start-time/state changes. Test cancel and subsequent successful request. Report actual measured resource peak and inference time, not model-name estimates. User-facing verification and explicit OK before PR creation and before merge.

## Approval gate
Read-only inspection found no existing Tailscale Serve configuration. The transport is therefore fixed to SSH local forwarding, without host-wide networking changes. This v1 is ready for user design review, not approved for implementation. Approval covers the staged runtime compatibility checks and safety tests; a failed compatibility/safety gate stops inference and requires a revised design rather than silent dependency or memory-budget changes. 2K refinement remains a separately approved follow-up.
