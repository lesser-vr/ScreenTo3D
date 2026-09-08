# Reliability contracts

Failure and ownership contracts, reviewed 2026-09-07. Delivered evidence and
unpassed acceptance are in [implementation-status.md](implementation-status.md).

## Jobs and publication

Jobs transition through probe/plan/warmup/process/finalize to succeeded, failed
or cancelled. Only success publishes the final path. Write a unique temporary
sibling, drain encoder/mux, validate, then atomically replace; failed work and
cancellation preserve the prior output. Do not overwrite input or report truncated
media as success. Success requires the completion event, zero exit and final file.

Cancellation stops submissions and attempts every owned cleanup without hiding
the primary error. Native calls are cooperative cancellation boundaries. Retain
the job lease through child exit/join. The isolated capture watchdog may terminate
only its owned worker visibly; OS cleanup is not graceful GPU/device-loss recovery.
File-worker semantics do not inherit capture force-termination behavior.

## Resources and errors

- Validate capabilities, geometry, color and tensor descriptors before expensive
  work/output mutation. Reject unsupported artifacts or cadence explicitly.
- Use bounded queues/pools and explicit owner/thread/epoch contracts.
  Offline preserves declared frames/timestamps/audio; live latest-frame policy
  counts replacement/drop events and never builds an unbounded backlog.
- Keep borrowed resources alive until GPU completion. Release postprocessing
  before engine streams; uncertain GPU failures poison that session until restart.
- Native texture acknowledgments follow the last GPU lease, not merely metadata
  reads. Bound generations and lock attempts; validate adapter/resource identity.
- Stop/error clears stale pixels and invalidates consumers. Source loss, cuts,
  resize and topology changes follow the named path's reset/stop policy.
- Do not silently switch backend, model, precision, codec, resolution or CPU path.
- Unrecoverable decode, inference, stereo, encode, mux, OOM or device loss aborts
  the affected job. Do not skip corrupt offline frames silently; report the
  primary stage/frame/PTS error and cleanup failures without captured pixels.

## Temporal contracts

Each backend declares its state-update frame IDs, timestamps, sampling policy
and reset API. Current full-rate stateful file bindings reject unsupported skipped
updates. The recorded exact-RGB live reuse rule belongs to the DA2 live profile,
not every future algorithm. A separately evaluated model timeline plus FG is
permitted as research; it must prove sampling/cache and temporal quality and does
not disable current guards. Model cache, depth normalization/EMA, propagation and
presentation state have distinct owners in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Observability and validation

Use correlation IDs, resolved settings, stage errors, reset/drop/copy counters and
bounded health metrics. Default logs omit captured pixels, weights and private
paths. Detailed traces/hashes/readbacks are explicit, with retention and overhead
declared. Per-process private memory and GPU-wide samples have different meanings;
sampled descendants can miss short-lived processes and are not leak proof.

Required release coverage includes repeated jobs, cancellation, failed load,
malformed input, encoder failure, OOM and the named hardware/support scenarios.
During development run only affected checks and reuse still-applicable evidence;
these cases are not a per-edit full-suite requirement. Synthetic/injected tests,
full media decoding, playback review, real device-loss and long soak remain
separate evidence categories. Never call an unpassed gate complete.

## Current feature limits

File recovery restarts from the beginning. A future resume feature needs an
explicit compatible checkpoint/integrity format; partial files are not resumable.
The present capture watchdog and texture leases are described in architecture and
the scoped evidence, not a ban on alternative reliable implementations.

The user's FPS-collapse stop/notify/retest condition is retained in
`evidence/live-performance.md#guarded-run-condition`. It applies to that guarded
experiment, not unrelated development or read-only investigation.

Output preservation, path aliases/cancel markers, per-job temporary siblings and
nonempty final publication have examples in `v1/tests/test_cleanup.py`,
`test_file_contracts.py` and `test_projection_publication.py`. Real FFmpeg checks
are in `v1/test_media_contracts.py`. Native final-lease acknowledgment examples
are in `test_native_delivery_protocol.py`, with real NT/Qt/CUDA entry points in
`scripts/test-hardware-contracts.py`. These are bounded contracts; actual long
sessions and physical device loss still need their named evidence.
