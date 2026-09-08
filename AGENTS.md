# Development rules

The operator workspace's canonical workflow is [../docs/DEVELOPMENT-WORKFLOW.md](../docs/DEVELOPMENT-WORKFLOW.md). Follow that current policy rather than historical gate wording in checkpoint notes; do not duplicate its workflow rules here.

Issue #1 holds case requirements. Current Refiner scope is recorded in `docs/DESIGN-v2-refiner-1080p.md`, `docs/DESIGN-v2.1-mov.md` and `docs/DESIGN-v2.2-duration-fps.md`; current deployment/evidence is in `docs/PROGRESS.md`. These documents distinguish technical validation from the still-unmet closed-mouth clone behavior.

Preserve existing services, datasets, host drivers and SSH responsiveness. Never run inference before verified independent memory monitoring, job-scoped kill, admission and heartbeat-loss protection. GPU shared-memory allocations may escape cgroup accounting. Do not test safety by exhausting host RAM. No broad deletions, privileged container shortcuts, daemon restarts or volume pruning. Deletion requires an itemized dry run and user approval.

Keep credentials, private connection details, prompts, inputs and generated artifacts out of this public repository. Keep development checkpoints updated to permit session-reload recovery. One writer per worktree. Runtime compatibility failures require design revision, not silent dependency substitutions.
