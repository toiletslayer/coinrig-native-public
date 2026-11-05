# COINrig Native Configurable Threads beta.5 Design

## Intent

Turn the beta.4 32-thread reference package into one HiveOS package that safely
supports different CPU thread counts from the flight sheet. The immediate use
cases are `threads=24` on a Ryzen 9 3900 and `threads=32` on a Ryzen 9 5950X.
The change exists to remove per-rig package builds without weakening beta.4's
full-dataset submission gate or locked network and RandomX policy.

## Goals

- Accept an empty Extra config as the beta.4-compatible 32-thread default.
- Accept exactly `threads=N`, where `N` is an ASCII decimal integer from 1 to
  256 with no sign, whitespace, leading zero, suffix, or additional parameter.
- Generate `cpu.rx/2` as the exact sequential profile `0..N-1`.
- Make the validated profile count the only value supplied to XMRig's
  `--threads` option.
- Keep `rx/2`, fast 2336 MB full-dataset readiness, `--randomx-wrmsr=-1`, no
  RDMSR, loopback API and gate, RFC1918-only upstream, native logging, stale
  marker cleanup, and fail-closed lifecycle behavior.
- Produce a deterministic beta.5 candidate with Scratcher's unmodified XMRig
  v6.26.0-coin binary SHA-256
  `5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462`.

## Non-goals and anti-goals

- No automatic CPU detection or tuning in beta.5.
- No wallet, gateway, node, cloud, live rig, private repository, tag, release,
  or GitHub publication changes.
- No arbitrary XMRig options in Extra config and no shell evaluation of its
  contents.
- No claim of live Ryzen 9 3900 validation from offline tests.

## Approaches considered

1. **Validated config as the single source of truth (selected).** The config
   callback writes the sequential profile. The Python validator accepts only a
   sequential profile of 1-256 entries and prints the validated count. The
   launcher uses that output for `--threads`. This keeps all three enforcement
   points consistent without a second mutable state file.
2. **Separate `.threads` state file.** Simple, but creates two values that must
   be kept atomic and compared on every run.
3. **Reparse `CUSTOM_USER_CONFIG` in the launcher.** Rejected because HiveOS
   callback environment propagation is not a dependable installed-state
   contract and it duplicates security-sensitive parsing.

## Constraints

Configuration remains source-safe when HiveOS invokes callbacks with a parent
`MINER_DIR` and an unrelated current directory. Invalid input must leave no new
config. The generated config and gateway remain mode 0600. The beta.5 archive
must preserve deterministic metadata, manifest consistency, per-file checksums,
and the pinned upstream archive and binary checks.

## Verification

Use tests written before implementation for 24, 32, 1, and 256 threads;
rejection of malformed, injected, zero, leading-zero, and out-of-range values;
validator/launcher propagation; MINER_DIR callbacks; readiness and gate state;
restart/stale marker; signal cleanup; extracted archive lifecycle; deterministic
packaging; and the exact real binary in a network-disabled Linux container.

