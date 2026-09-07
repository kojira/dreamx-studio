# Development rules

Canonical workflow: docs/DEVELOPMENT-WORKFLOW.md. Issue #1 and approved design docs/DESIGN-v1.md define scope. Design v1 approved by the user; no PR or merge approvals yet.

Follow requirements Issue → detailed design → explicit design approval → implementation branch → implementation → verification. Return to design for unspecified APIs, dependencies, compatibility workarounds or changes to safety boundaries. Obtain explicit user testing approval before PR creation (including drafts) and separately before merge.

Preserve existing services, datasets, host drivers and SSH responsiveness. Never run inference before verified independent memory monitoring, job-scoped kill, admission and heartbeat-loss protection. GPU shared-memory allocations may escape cgroup accounting. Do not test safety by exhausting host RAM. No broad deletions, privileged container shortcuts, daemon restarts or volume pruning. Deletion requires an itemized dry run and user approval.

Keep credentials, private connection details, prompts, inputs and generated artifacts out of this public repository. Keep development checkpoints updated to permit session-reload recovery. One writer per worktree. Runtime compatibility failures require design revision, not silent dependency substitutions.
