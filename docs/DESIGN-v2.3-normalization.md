# v2.3 — normalize valid input instead of rejecting timing/aspect differences

The user's request to remove unnecessary input restrictions applies to the reported H264 upload rejection. Current input has a near-landscape but non-16:9 aspect and differing nominal/average fps. Remove the ±1% aspect requirement and input CFR equality tests. Validate decodability, finite nondecreasing presentation timestamps and consistent pixel geometry; normalize to the selected CFR with the existing FFmpeg filter. Retain other format bounds and all existing isolation/emergency controls. Final fit/pad already supports arbitrary source aspect ratios.

Move Refiner validation errors next to its controls and explicitly identify failed validation rather than leaving an apparently pending action. CPU-only validation of the supplied input is sufficient; do not start GPU inference, generator-model loading or browser automation. Do not claim long-clip GPU success.
