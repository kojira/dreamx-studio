# v1.2 resource amendment

Issue #1. User explicitly requested relaxing limits after v1.1 smoke stopped during model loading with host availability still >=86.8GiB and Docker OOMKilled=false. User statement: 「もっと緩めていいよ」. Parent announced exact bounds before applying.

Change ONLY worker Docker memory and memory+swap caps from64GiB back to original v1's80GiB, and cgroup stop threshold from56GiB back to72GiB. Host available-memory emergency remains48GiB,100ms sampling, predictive stop and independent heartbeat guards as v1.1. No GPU memory accounting guarantee. Keep single job,21-frame/4-step initial smoke. No automatic further relaxation.

Full inference compatibility/quality remains unproven; first smoke did not generate a video. Preserve all existing services/data. Apply unit tests and verify actual Docker+cgroup settings before retry.
