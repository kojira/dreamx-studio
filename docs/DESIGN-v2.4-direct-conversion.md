# v2.4 — start processing directly; no separate media prevalidation

User explicitly requested removal of the validation phase/button: select video, enter fps, press enhancement. Attempt conversion, then inference; report failures. Prevalidation cannot guarantee inference success.

Remove the structural media gate, input-format policy gate, full pre-decode inspection and redundant full output decode/audio hashing from CPU preparation. Retain only lightweight headers needed to configure conversion and read its output, one FFmpeg conversion, file checks and checksums for handoff identity. Do not gate readable input by resolution/codec/aspect/CFR metadata. Conversion errors surface normally. Keep existing isolated CPU execution, file-size transport limit, shared lease and GPU emergency stopping unchanged; add no safety machinery.

File selection performs no request. The single enhancement action uploads/converts then submits the Refiner. Cancel during conversion must not submit inference. Internal API/lease names may remain for compatibility; UI calls this conversion, not validation. No GPU or browser automation tests; a short CPU conversion of the user's provided file and local regressions suffice.
