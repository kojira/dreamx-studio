# DreamX Studio

Minimal browser trial UI for [DreamX-Creator](https://github.com/AMAP-ML/DreamX-Creator) on NVIDIA GB10 / ARM64. First-frame image + prompt → video with audio, or short MP4/MOV →1080p with Refiner. Research prototype, not a production service.

## Safety first
GPU and CPU share RAM on GB10. Docker limits alone are **not** a proven GPU-memory ceiling. A separate host guardian checks available memory every100ms, stops the exact job when actual host availability falls below8GiB (predictive stopping is disabled), and detects lost runner heartbeats. The runner and worker also check guardian liveness. One job at a time, no automatic retries, no automatic data deletion. GPU workers have no Docker RAM capacity ceiling or cgroup-usage kill threshold. The separate CPU video validator is bounded to2 CPUs,2GiB RAM, no swap allowance,128 PIDs and60 seconds. Before model load the trusted host sets only the exact worker's cgroup memory.swap.max=0 (requires noninteractive sudo), verifies it, and the guardian monitors this prohibition. The host's global swap configuration is not changed. See approved amendments in `docs/` and measured limitations in `docs/HARDWARE-NOTES.md`. SSH survival cannot be guaranteed against rapid unaccounted allocations.

Existing host drivers/containers are never replaced by this application. 2K refinement is not enabled.

## Components
- `frontend/`: React/TypeScript single-page trial interface.
- `backend/dreamx/api.py`: FastAPI, automatic local session/CSRF, upload validation, job status and media.
- `backend/dreamx/host_runner.py`: host-only private Unix socket supervisor; **never mount Docker socket in web container**.
- `backend/dreamx/host_guard.py`: independent host process, not in inference cgroup.
- `runtime/Dockerfile`: pinned upstream model runtime. Keeps cuBLAS/cuBLASLt from the matching PyTorch dependency directory; this mattered on the tested host.
- `Dockerfile.ui`: CPU-only UI/API container.
- `runtime/Dockerfile.video-validator`: isolated, networkless input decoding/normalization.
- `runtime/Dockerfile.refiner`: separate Refiner dependencies and hash-checked compatibility patches; no changes to the generator image.

## Development checks
```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
cd frontend
npm ci
npm run build
```

## Trial access on the configured host
The web port must be published **only** at host `127.0.0.1:8780`. Reach it using an operator-managed SSH forward:
```sh
ssh -N -L 127.0.0.1:8780:127.0.0.1:8780 "$SSH_TARGET"
```
Open http://127.0.0.1:8780. No access key or login input is required. The page automatically establishes a local HttpOnly/SameSite session and CSRF token; these are browser-request safeguards, not user authentication. Trust is placed in local/SSH access. No public ingress.

Upload PNG/JPEG/WebP <=10MiB and16MP, enter prompt and optional seed, generate. The browser defaults to880 spatial tokens, with220/440/880 choices; API clients omitting the setting retain220. The trial produces69 frames at24fps (~2.875s),50 steps. Actual aspect ratio follows input; this is not a fixed landscape resolution. Cancel stops only the job. Files remain in dedicated storage and are not automatically cleaned.

## Standalone Refiner
Select **「動画を1080p化」**, choose a video, enter output fps, and press **「高解像度化」**. File selection does not upload or run validation. The single action uploads, converts to MP4, and submits Refiner inference. Conversion/inference failures are shown beside the controls. No image-generation step or prompt is required.

- MP4/MOV picker, up to100MiB. There is no duration/frame-count ceiling or independent codec/resolution/aspect/CFR admission check. FFmpeg attempts conversion; unsupported media produces an error.
- Output is1920×1080 at a positive numeric fps (default24; fractional rates supported), fitted/padded without cropping. Changing fps invalidates the prepared input for the next action.
- No structural media precheck, full pre-decode scan, redundant full output decode or CPU audio prehash. Only lightweight headers, one FFmpeg conversion and handoff checksums are used. Audio is stream-copied, so audio incompatible with MP4 can cause a conversion error.
- Converted input preview, progress, cancellation, history and MP4 download remain available. MOV browser playback depends on its codecs and browser; the app previews the converted MP4.

Videos longer than approximately5 seconds are split losslessly at frame boundaries, refined sequentially with one model load, then concatenated with original normalized audio. Clip tensors/caches are released after each saved segment; the final short segment is retained. Segment boundaries may flicker. Segmented GPU operation has not yet been verified and may still exhaust resources. Existing CPU isolation/timeouts and GPU emergency stopping remain unchanged. CPU conversion and GPU jobs use the existing shared operation lease; cancellation releases it only after the exact container stops. Inputs/results are not automatically pruned.

Refiner processes4n+1 padded tensors; the pinned upstream removes only the added frames before writing its intermediate MP4. The final worker verifies the original normalized count. It does not repair mouth motion, remove speaking gestures or guarantee face/identity fidelity.

Measured browser acceptance:69 frames completed in264s and72 frames in278.60s, both retaining audio and all frames. These are measurements, not an ETA or quality guarantee for every clip. Refiner adds approximately10.02GB of weights. The configured host enables this feature after acceptance; a new deployment needs pinned `validator_image_id`, `refiner_image_id` and operator-controlled `refiner_enabled` configuration. Do not bypass guardian/admission requirements to enable it.

## Operator notes
Deployment is currently a manually validated dedicated trial environment, not an unattended installer. Model weights require ~43.18GB for the selected base-generator files. Exact downloaded revision is recorded in the private runtime manifest. Run `runtime/probe.py` in a small resource-limited GPU container before model inference; run harmless guardian tests before accepting jobs. Never simulate protection by exhausting host RAM.

Host runtime directory contains private config, weights, `app/` data, `control/` socket/heartbeats and evidence. API container gets app-data read/write and control read-only; no GPU and no Docker socket. Per-job inference mounts only weights, one input, one output directory and read-only control/wrapper files. All job containers run as the host UID, without privileges, network or restart policy.

Guardian/runner startup commands (after explicit config/preflight):
```sh
PYTHONPATH="$APP_CODE/backend" python3 -m dreamx.host_guard --root "$RUNTIME/control"
PYTHONPATH="$APP_CODE/backend" python3 -m dreamx.host_runner --root "$RUNTIME"
PYTHONPATH="$APP_CODE/backend" python3 -m dreamx.progress_collector --root "$RUNTIME"
```
They must be independent host processes and remain running. Current trial does not install system boot services. If the runner stops, do not blindly remove its socket or clear an active job: verify and stop the exact old job, preserve evidence, reconcile state, then archive the stale socket before restarting. The supervisor deliberately refuses unresolved prior workers. No daemon-wide restart or pruning is required.

## Validation status
See `docs/PROGRESS.md`. Passing unit tests alone does not validate GPU safety, generation quality, or end-to-end operation. Technical checks do not constitute the user's quality acceptance; publication/merge gates follow the canonical development workflow.
