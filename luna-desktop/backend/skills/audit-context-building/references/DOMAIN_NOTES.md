# Luna Audit Context — Domain Notes

These notes specialize the same context-building method without changing its evidence standard.

## Smart contracts

Map:
- externally reachable state-changing instructions/functions;
- signer/authority derivation and account ownership;
- PDA/seeds or equivalent address derivation;
- asset custody and token/account constraints;
- CPI/external calls and callbacks;
- state transitions and economic invariants;
- integer width, base units, decimals and rounding;
- upgrade/configuration authority.

Do not infer an exploit from a missing-looking check until all framework/account constraints and called code are inspected.

## Web/API services

Map:
- routes, methods and middleware order;
- authentication and authorization enforcement;
- tenant/object ownership boundaries;
- parser/deserializer behavior;
- server-side validation versus UI validation;
- storage, queues, caches and background jobs;
- outbound requests and trust in upstream data;
- secrets/config/defaults that alter enforcement.

## C/C++ and native code

Map:
- ownership and lifetime;
- buffer sizes and integer conversions;
- error paths and cleanup;
- privilege transitions;
- parsing boundaries;
- syscalls/FFI;
- concurrency/shared state;
- compile-time/runtime feature guards.

## Decompiled firmware / binaries

Treat names and recovered types as uncertain. Track:
- cross-references;
- call graph evidence;
- memory-mapped I/O;
- trust transitions from input to privileged operation;
- inferred structures with confidence labels;
- opaque library/runtime calls.

## Data/security analytics

When code consumes telemetry, logs or datasets, record:
- source provenance;
- timestamp/timezone semantics;
- schema/grain;
- missingness and duplicates;
- joins/keys;
- transformations;
- thresholds;
- whether a conclusion depends on sampled or complete data.

A statistically plausible pattern is not automatically a security finding; preserve the distinction between observation, inference and verified mechanism.
