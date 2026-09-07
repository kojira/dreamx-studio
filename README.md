# DreamX Studio

Minimal browser trial UI for [DreamX-Creator](https://github.com/AMAP-ML/DreamX-Creator) on NVIDIA GB10 / ARM64. First-frame image + prompt → video with audio. Research prototype, not a production service.

## Safety first
GPU and CPU share RAM on GB10. Docker limits alone are **not** a proven GPU-memory ceiling. A separate host guardian checks available memory every100ms, stops the exact job below48GiB or a projected breach, and detects lost runner heartbeats. The runner and worker also check guardian liveness. One job at a time, no automatic retries, no automatic data deletion. Worker cap80GiB/no swap and cgroup stop72GiB are secondary limits. See approved amendments in `docs/` and measured limitations in `docs/HARDWARE-NOTES.md`. SSH survival cannot be guaranteed against rapid unaccounted allocations.

Existing host drivers/containers are never replaced by this application. 2K refinement is not enabled.

## Components
- `frontend/`: React/TypeScript single-page trial interface.
- `backend/dreamx/api.py`: FastAPI, automatic local session/CSRF, upload validation, job status and media.
- `backend/dreamx/host_runner.py`: host-only private Unix socket supervisor; **never mount Docker socket in web container**.
- `backend/dreamx/host_guard.py`: independent host process, not in inference cgroup.
- `runtime/Dockerfile`: pinned upstream model runtime. Keeps cuBLAS/cuBLASLt from the matching PyTorch dependency directory; this mattered on the tested host.
- `Dockerfile.ui`: CPU-only UI/API container.

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

Upload PNG/JPEG/WebP <=10MiB and16MP, enter prompt and optional seed, generate. Current trial preset is220 spatial tokens,69 frames at24fps (~2.875s),50 steps. Actual aspect ratio follows input; this is not a fixed landscape resolution. Cancel stops only the job. Files remain in dedicated storage and are not automatically cleaned.

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
See `docs/PROGRESS.md`. Passing unit tests alone does not validate GPU safety, generation quality, or end-to-end operation. PR/merge require separate user verification approval.
