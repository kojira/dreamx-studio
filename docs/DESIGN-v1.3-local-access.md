# v1.3 local trial access

User explicitly requested removing the access key because this is local verification over a trusted Tailscale connection (「なくして」). Remove the human login/key step and file-secret dependency from the UI/API container. Opening the page automatically creates an internal session and CSRF token; this is not an access-control claim or a user credential.

Keep host publish at127.0.0.1:8780 and the existing SSH forward; no public exposure or tailnet ACL changes. Keep exact Host/Origin checks and CSRF on modifying browser requests to prevent unrelated websites driving the local inference API. Trust local operator/SSH access. Existing private key file can remain unused; no deletion required.

No inference/memory/model changes. Restart only the dedicated UI container to apply. Persistent app data and active inference are preserved. Test that a fresh browser opens generation UI without typing any key, and cross-origin modifications remain rejected.
