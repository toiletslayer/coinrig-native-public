# HiveOS Package Directory beta.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct all HiveOS callbacks so beta.3 works when HiveOS exports the custom-miner parent as `MINER_DIR`, then build, validate, and publish the public prerelease.

**Architecture:** Each callback resolves an immutable package directory from `BASH_SOURCE[0]`, with a dedicated test override when explicitly supplied; runtime state and packaged helpers are addressed through that directory. Regression tests recreate HiveOS's parent `MINER_DIR`, unrelated cwd, and callback invocation forms, while archive validation extracts the deterministic package into the same layout and replaces only the miner executable with a fake for an offline lifecycle.

**Tech Stack:** Bash, Python `unittest`, deterministic `tarfile` packaging, GitHub Actions/CLI.

**Spec:** `docs/superpowers/specs/2026-11-04-hiveos-package-dir-beta3.md`

## Global Constraints

- Never access or modify any private repository or live miner configuration.
- Never contact a real COIN node or submit a block.
- Keep the XMRig binary exactly at SHA-256 `5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462`.
- Keep upstream source pinned to Scratcher's v6.26.0-coin commit `ca01d6df121c5c3692cd16cb64d95cf861398703` and retain GPLv3 attribution.
- Publish only after local tests, extracted-archive Linux validation, and remote CI succeed.

## Review Focus

- `MINER_DIR` points at `/hive/miners/custom`: every callback must still use the sibling package files under `coinrig-native`.
- Current working directory is unrelated to the package: relative invocation state must not affect path resolution.
- `h-config.sh` is sourced while `h-run.sh` is directly executed: both forms must derive the same package directory.
- `h-stats.sh` helper lookup fails: HiveOS-facing fallback values must remain safe and syntactically valid.
- Release archive layout or binary changes: validation must reject the wrong folder, missing executability, or non-pinned XMRig hash.

---

### Task 1: Reproduce and fix callback package-directory resolution

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `tests/test_launcher.py`
- Modify: `coinrig-native/h-config.sh`
- Modify: `coinrig-native/h-run.sh`
- Modify: `coinrig-native/h-stats.sh`

**Interfaces:**
- Consumes: HiveOS environment variables and callback invocation behavior.
- Produces: `COINRIG_PACKAGE_DIR` as the explicit test-only override; otherwise each callback derives its package directory from `BASH_SOURCE[0]`.

- [ ] **Step 1: Write failing regression tests**

Add behavior tests that install the callbacks under a temporary `.../custom/coinrig-native`, set `MINER_DIR` to the `.../custom` parent, run from an unrelated cwd, source `h-config.sh`/`h-stats.sh`, directly execute `h-run.sh`, and assert configuration, helper lookup, fake-miner lifecycle, and cleanup occur inside the package directory.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_integration tests.test_launcher -v`

Expected: the new tests fail because beta.2 looks for `submission-gate.py`, `config.json`, and `xmrig` in the parent directory.

- [ ] **Step 3: Implement minimal package-directory derivation**

In all three callbacks resolve `PACKAGE_DIR` from `${BASH_SOURCE[0]}` using physical absolute paths, allow only the explicit `COINRIG_PACKAGE_DIR` override for tests, and replace package-file references that currently use `MINER_DIR`.

- [ ] **Step 4: Run focused tests and full suite**

Run: `python -m unittest tests.test_integration tests.test_launcher -v`

Expected: focused tests pass.

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with no network or real miner.

- [ ] **Step 5: Commit**

Commit message: `Fix HiveOS package directory resolution`

### Task 2: Prepare beta.3 metadata and deterministic archive validation

**Files:**
- Modify: `coinrig-native/h-manifest.conf`
- Modify: `scripts/package_release.py`
- Create: `tests/test_release_package.py`
- Modify: `README.md`
- Modify: `coinrig-native/README.md`

**Interfaces:**
- Consumes: Task 1 callback behavior and pinned upstream binary/source metadata.
- Produces: `coinrig-native-1.1.0_beta3.tar.gz`, its checksum, and an extracted-archive offline lifecycle test.

- [ ] **Step 1: Write failing package regression test**

Add a test that builds/extracts the candidate archive, verifies root layout, executable modes, manifest beta.3 version, pinned XMRig SHA-256, then exercises config/run/stats from an unrelated cwd with parent `MINER_DIR` and a fake replacement miner in the extracted test copy.

- [ ] **Step 2: Run the package test and verify RED**

Run: `python -m unittest tests.test_release_package -v`

Expected: fail because beta.3 metadata and archive fixture do not yet exist.

- [ ] **Step 3: Update version and documentation**

Set all public version references to `1.1.0_beta3`, document the package-directory fix, and mark beta.2 superseded without changing the pinned binary/source provenance.

- [ ] **Step 4: Build and validate the archive**

Use Scratcher's checksum-verified original release archive to run `scripts/package_release.py`; then run the complete Python suite and an offline Linux-shell extracted lifecycle with network isolation.

Expected: package and source hashes verify; XMRig hash remains pinned; no real endpoint is contacted.

- [ ] **Step 5: Commit**

Commit message: `Prepare COINrig Native beta.3 release`

### Task 3: Publish and verify the public prerelease

**Files:**
- No source changes expected.
- Create release assets outside the repository working tree.

**Interfaces:**
- Consumes: Task 2 commit, green local suite, deterministic archive/checksum, and unchanged pinned source assets.
- Produces: public main commit, tag `coinrig-native-v1.1.0-beta.3`, prerelease assets, superseded beta.2 notice, exact public URLs and checksums.

- [ ] **Step 1: Push the feature branch and verify CI**

Expected: GitHub Actions succeeds for the exact beta.3 commit.

- [ ] **Step 2: Publish the verified commit to main**

Fast-forward public `main` only after confirming it still points at the observed beta.2 base, then verify main CI.

- [ ] **Step 3: Create the beta.3 prerelease**

Upload the deterministic package, package checksum, unchanged pinned source archive, and source checksum; edit beta.2 with a clear superseded-by-beta.3 notice.

- [ ] **Step 4: Verify remote evidence**

Check tag/commit, prerelease/draft flags, all four asset names and byte counts, GitHub asset digests, downloaded checksums, public URLs, and beta.2 superseded text.

- [ ] **Step 5: Record publication evidence**

Report the exact release and installation URLs, package/source SHA-256 values, commit, CI result, test counts, and the explicit limits of offline validation.
