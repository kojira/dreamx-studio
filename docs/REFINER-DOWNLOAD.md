# Refiner download receipt

User authorized download only. Completed successfully; no Refiner model loading or inference performed.

Source: `GD-ML/DreamX-Creator`, pinned revision `10fb869a92dd45659f38fdc2bb74c8ef0ba7bf7c`.

| File | Bytes | Verified SHA256 |
| --- | ---: | --- |
| `refiner/sr_dit_5b.pt` | 9999839408 | `87787d48e132e1bc8cd7dbbd28d40f00c56fc3b4abe7e28620c731047c198691` |
| `refiner/latent_upsampler_flash.pt` | 20014099 | `daf3ec014b54bcd43e797d4e9c47771aa7206d68ec18c9ada6330e0de9342f6d` |

Both files passed byte-count and SHA256 checks. Download container exited0, OOMKilled=false, final marker `REFINER_DOWNLOAD_VERIFIED`. GPU was not exposed; memory and memory+swap limits were1GiB. No existing data was deleted. Optional LightVAE and causal upsampler were not downloaded.

Tracking: https://github.com/kojira/dreamx-studio/issues/1#issuecomment-5575105528

## Remaining boundary

Standalone video enhancement and exact1080p output have been discussed, but their detailed design and implementation are not approved. Download permission is not inference/deployment permission. Do not launch a Refiner job or alter the running UI on a scheduler wakeup alone. Base880 generation succeeded; user quality acceptance and PR/merge permissions remain outstanding.
