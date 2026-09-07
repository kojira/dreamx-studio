# v1.11 — user-authorized8GiB reserve

User explicitly allowed available RAM down to8GiB and authorized stopping AivisSpeech, lipsync-engine and open-webui. Those three containers have been stopped, not deleted. Do not restart them without instruction.

Change only the host RAM stop threshold from24 to8GiB (below8 stops; exactly8 is allowed). Use one shared HOST_RESERVE constant for host_guard and pure emergency policy. No prediction, no Docker RAM capacity ceiling, worker swap prohibited before load and monitored, missing telemetry/heartbeats still fail closed. Admission96GiB/free disk150GiB, single active job and180minute timeout remain unchanged. Sampling can overshoot8GiB; this is not a guaranteed remaining-memory minimum.

Verify synthetic boundary tests and high worker usage without hidden thresholds; replace the independent host guardian with fresh-health overlap at verified idle. Retry the same official2x Refiner case under a new v1.11 identity, existing SDPA patch, same video/seed and no mmap. Requested1080p reduced-resolution trial has not been run; defer it while this same2x comparison runs. If2x succeeds,1080p can be produced afterward without another GPU generation. Do not change other services or relax further limits automatically.
