# v1.4 — frontend resolution selection (approved)

Issue #1. User requests frontend control after reporting face/mouth distortion at220 spatial tokens. Approved by user after the three-option/default880 summary (「設計書見えてないけど任せるよ」), followed by explicit instructions to proceed quickly.

## UI and scope
Add a resolution-quality select: Low220 tokens, Medium440 tokens, Official880 tokens. New-page default is880. Keep50 sampling steps,69 frames/24fps and existing seed input unchanged. No free-form token count, 2K refinement, duration or step controls in this amendment. Show that actual dimensions follow image aspect ratio and higher values can consume more RAM/time. Do not promise better faces.

Changing selection only edits the next request; never changes an active job. Show submitted token count alongside job status/result, including historical jobs. Old job records with no token count are displayed as220. Existing history/media remain untouched.

## Data/API
POST /api/jobs adds integer spatial_tokens, strictly restricted to220/440/880; reject other values/types with422. For old cached clients, omitted field defaults to220, NOT880. Updated frontend always sends an explicit value and defaults its selection to880. Persist the requested value in job payload/spec/evidence. Different token count with same idempotency key is a409 conflict. Old payloads without the field are normalized to220 for comparison.

Worker uses stored spatial_tokens, defaults to220 for existing specs, validates allowed values, and passes it as one argv value to --target_spatial_tokens. No shell interpolation or arbitrary CLI options. Token count is not a literal pixel resolution. Actual output dimensions remain from upstream and ffprobe evidence.

## Safety and rollout
No relaxation of v1.2: admission96GiB, host available48GiB/predictive100ms guard, worker cap80GiB/no swap and cgroup guard72GiB, one job. No automatic retry or fallback. Confirm no active user job before changing host worker wrapper or restarting runner. UI replacement retains dedicated data and does not recreate inference containers. Existing upstream image/dependencies/drivers are unchanged.

## Acceptance
- Default frontend selection880; selecting220/440/880 sends/stores/executes the exact value.
- API rejects invalid types/values and preserves omitted-field220 compatibility.
- Old job history/specs remain220, and idempotency comparison handles omitted legacy value.
- Selection change during active generation has no effect on running job.
- Existing unit tests/build pass, plus parameter validation and argv tests.
- Check actual880-token generation under unchanged guards, comparing only approved same input/prompt/seed/steps when no user job is active; record actual dimensions/resource peak/result. A guard stop remains a valid safety outcome, not a reason to raise limits silently.
