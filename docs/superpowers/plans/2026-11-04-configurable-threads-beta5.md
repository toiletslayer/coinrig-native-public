# COINrig Native Configurable Threads beta.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify an unpublished deterministic beta.5 candidate that safely applies `threads=N` across HiveOS configuration, validation, and launch.

**Architecture:** `h-config.sh` strictly parses the one allowed Extra-config key and writes an exact sequential `cpu.rx/2` profile. `submission-gate.py validate-config` validates the locked profile and emits its count; `h-run.sh` uses only that validated count for the XMRig CLI.

**Tech Stack:** Bash, Python 3 standard library, `unittest`, deterministic `tarfile` packaging, Linux Docker with networking disabled.

**Spec:** `docs/superpowers/specs/2026-11-04-configurable-threads-beta5.md`

## Global Constraints

- Preserve all beta.4 security, logging, readiness, path, and lifecycle behavior.
- Accept blank as 32 and only exact `threads=N` for ASCII decimal N in 1-256.
- Package only the checksum-pinned unmodified XMRig v6.26.0-coin binary.
- Do not access or alter live rigs, nodes, wallets, cloud systems, or the private repository.
- Do not push, tag, publish, or create a GitHub release.

## Review Focus

- Shell metacharacters, whitespace, signs, leading zeros, and extra keys must fail before config creation.
- Counts at 1 and 256 must pass; 0 and 257 must fail.
- A tampered non-sequential CPU profile must block launch.
- The XMRig CLI count must equal the validated generated profile count.
- A 24-thread extracted archive must retain readiness, cleanup, and MINER_DIR behavior.

---

### Task 1: Config parsing and generated CPU profile

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `coinrig-native/h-config.sh`

**Interfaces:**
- Produces: generated `config.json` whose `cpu.rx/2` is exactly `list(range(N))`.

- [ ] Add failing behavior tests for blank/24/32/1/256 and malformed/injected/out-of-range Extra config.
- [ ] Run the focused Linux tests and confirm beta.4 fails on the new valid counts.
- [ ] Implement strict parsing and sequential profile generation without evaluation.
- [ ] Run the focused tests and full offline suite.

### Task 2: Validator-to-launcher propagation

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `tests/test_launcher.py`
- Modify: `coinrig-native/submission-gate.py`
- Modify: `coinrig-native/h-run.sh`

**Interfaces:**
- Produces: `validate-config` stdout containing one validated decimal thread count.
- Consumes: exact sequential `cpu.rx/2` profile from Task 1.

- [ ] Add failing tests for validator output, non-sequential/out-of-range profiles, and captured 24/32 CLI arguments.
- [ ] Confirm focused tests fail because the validator and launcher remain hard-coded at 32.
- [ ] Validate the supported profile and return its count; capture and revalidate that output in the launcher.
- [ ] Run launcher, readiness, restart, stale marker, and signal lifecycle tests.

### Task 3: Version, documentation, and extracted candidate lifecycle

**Files:**
- Modify: `tests/test_release_package.py`
- Modify: `scripts/package_release.py`
- Modify: `coinrig-native/h-manifest.conf`
- Modify: `README.md`
- Modify: `coinrig-native/README.md`
- Modify: `SECURITY.md`

**Interfaces:**
- Produces: `coinrig-native-1.1.0_beta5.tar.gz` and matching `.sha256` file.

- [ ] Change release tests first to require beta.5 and a 24-thread extracted lifecycle; confirm failure on beta.4 constants.
- [ ] Update version metadata and documentation, including blank=32 migration behavior and exact supported syntax/range.
- [ ] Build twice from the pinned upstream archive and compare hashes for determinism.
- [ ] Validate archive members, modes, manifest, `SHA256SUMS`, binary hash, and extracted lifecycle offline.

### Task 4: Exact-binary offline verification and candidate handoff

**Files:**
- Modify only if a failing test identifies a candidate defect.
- Create outside Git: user-facing candidate artifacts in this task's `outputs` directory.

**Interfaces:**
- Consumes: pinned upstream archive SHA, source archive SHA, and extracted binary SHA.
- Produces: candidate archive, checksum, source archive copy, release notes, and verification evidence.

- [ ] Run syntax, compile, and full tests in network-disabled Linux.
- [ ] Run the exact XMRig binary test with `COINRIG_REAL_XMRIG` and `--network none`.
- [ ] Re-run extracted release lifecycle from the final archive.
- [ ] Inspect Git diff/status and verify no remote push/tag/release occurred.
- [ ] Report local paths, exact hashes, passed/skipped tests, limitations, and ask for explicit publication approval.

