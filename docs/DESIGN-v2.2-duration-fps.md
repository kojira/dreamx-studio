# v2.2 — remove duration limits; user-entered output fps

Approved scope: the user's latest explicit instruction is to remove the duration limit, not replace it with a15/20-second ceiling. Output fps becomes a positive finite numeric input (default24), not a preset list. No long GPU acceptance run before deployment; short CPU/media regression tests and build checks only. Generator weights must not be loaded for this work; Refiner remains standalone.

Remove duration and6–72-frame admission bounds throughout normalization, host receipt validation and Refiner argv/output checks. Retain positive duration/nonempty frames, media integrity and existing format/upload bounds. Carry selected fps from upload through CPU normalization, persisted metadata, job specification and final output validation. Existing uploads/jobs default to24fps. Selecting a different fps invalidates the previous normalized input. No model or inference algorithm change.

Existing emergency host reserve, heartbeat/exact-worker stopping and single-operation controls remain. No additional safety mechanisms or GPU tests. Existing CPU isolation and processing timeout remain operational limits, not promises of unlimited resource availability. Long-clip operation has not been GPU-verified; show this fact without disabling submission. MOV playback wording must not imply all MOV files are unsupported by browsers.
