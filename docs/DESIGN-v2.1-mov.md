# v2.1: MOV input container

User requested MOV input support. This bounded amendment adds the MOV container without changing the existing resolution/duration, codec or safety limits. No GPU/runtime policy change or new model run is required.

- Accept self-contained QuickTime/MOV as well as MP4. Permit the `qt  ` brand; legacy MOV without `ftyp` requires both `moov` and `mdat` structural boxes. Preserve strict box bounds, self-contained data-reference checks, disabled external references, isolated full decode and CFR validation.
- Existing codecs remain H264/yuv420p and optional AAC; HEVC, ProRes and PCM are not added by this container-only amendment. Display the supported codecs alongside MP4/MOV rather than claim all MOV encodings work.
- Keep0.25–3s,720p/near16:9,100MiB, audio timing and shared lease constraints. Normalize accepted MOV to the existing H264/AAC MP4 contract, preserving audio and normalized frame count.
- API still accepts bounded octet-stream bytes and UUID-only references. Internal raw filenames remain fixed; filenames/extensions do not establish media validity.
- Add `.mov`/`video/quicktime` to the browser picker. Use the normalized MP4 for validated input preview because browser support for raw MOV varies.
- Validate positive/negative container fixtures, all existing regressions, a real synthetic MOV through the isolated validator and browser, and byte-identical copied audio. No repeated GPU trial: the Refiner still receives the same normalized MP4 contract already accepted.
