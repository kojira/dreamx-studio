# Refiner test v1.12 — retain video ending during audio mux

Bounded compatibility correction authorized under the user's direction to proceed with Refiner tests. No memory-policy/model changes.

1080 trial completed Refiner inference and decode: tensor69frames, internal1920x1088,111s SR stage; minimum sampled host availability18.366GiB. Validation failed because upstream audio mux retained only67 video frames. Source audio is2.858s versus video2.875s. Independent CPU reproduction on source: ffmpeg stream-copy with-shortest produced68frames; without-shortest retained69. Therefore do not truncate to the shorter audio stream.

Patch only the pinned inference_sr.py audio mux argv by removing-shortest. Do not change checkpoint loading, tensors, seed, frame count, model or default inference schedule. Original SHA25617410e170dc6c42d098668478da226fa48a98678ab1e628202988cf204d2415d must match. Mount the test-only patched file read-only in a new trial; retain failed artifacts. Test the actual patched mux function on a CPU-only private copy and verify69frames/audio hash before GPU retry.

Repeat one1080 trial with the existing attention patch and same input/settings. Keep8GiB host stop, unlimited Docker RAM, zero worker swap, heartbeats, single job and180minute timeout. Validate raw and final frame counts/duration, unchanged audio and original checksum. Do not duplicate frames to conceal missing endings or mark failed acceptance as success. Earlier complete69-frame video was overwritten by upstream mux, so redoing inference is needed; do not rerun once the corrected output passes.
