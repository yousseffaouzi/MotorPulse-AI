# Physical operation feature snapshots (MP-076)

MP-075 hashes parsed feature content and raw bytes from the same bounded read.
MP-076 extends MP-072's private-copy approach to training and validation,
including standalone model/result replay. All three scoring/fitting operations
validate their existing approval chain against their captured feature cohort.
Nested synchronous replay with the exact active paths reuses those copies.

Each feature file is limited to 256 MiB, and the entire captured cohort to
1 GiB. This is a new aggregate limit for training and validation. Copies live
in the local temporary directory, never appear in model or result artifacts,
and are removed on ordinary success or exception. A process kill or crash can
leave files behind; deletion is not secure erasure. Use private local storage.

The capture is not an atomic snapshot of a changing filesystem. The complete
approval chain checks the captured canonical and raw hashes against the frozen
bundle; a mismatch fails closed. A change to the original after capture does
not affect that operation, and a fresh invocation rechecks the new bytes.
Metadata inputs are not protected against concurrent in-process mutation.
Use a trusted local machine and stable metadata; this mechanism is not a
security boundary against a hostile local operator.

Integrity replay still parses all partitions and recomputes the original
train-only fit and approved validation scores. The test partition is not
sealed. No new fit on held-out rows, tuning, authenticated human consent,
diagnosis, deployment, publication or hardware capability is introduced.
Metadata-only stages that independently reopen originals remain separate.
All regressions use generated physical-style fixtures. MP-016 remains ON HOLD.
