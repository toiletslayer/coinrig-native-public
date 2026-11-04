# COINrig Native beta.3 HiveOS package-directory fix

## Goal

Publish `coinrig-native-v1.1.0-beta.3` from the public repository after proving
the HiveOS callbacks locate their installed package from their own script path.

## Required behavior

- Real HiveOS may export `MINER_DIR=/hive/miners/custom`, while the installed
  package is `/hive/miners/custom/coinrig-native`.
- `h-config.sh`, `h-run.sh`, and `h-stats.sh` must resolve package files from
  their own installed script directory rather than trusting `MINER_DIR`.
- Tests must still be able to use temporary package and log directories.
- Regression coverage must use the real parent-directory `MINER_DIR`, an
  unrelated working directory, and source/direct execution patterns matching
  HiveOS.
- The extracted release archive must pass an offline Linux lifecycle test with
  a fake miner and no real node submissions.
- The packaged XMRig binary must remain byte-identical to Scratcher's pinned
  v6.26.0-coin binary (`sha256:5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462`).
- The pinned source archive and GPLv3 attribution must remain part of the
  prerelease assets and documentation.
- Documentation must point to beta.3 and state that beta.2 is superseded.
- Do not modify a private repository, live HiveOS flight sheet, LAN gateway,
  node, wallet, or start a real miner.

## Publication

Publish a GitHub prerelease with the package, package checksum, pinned source
archive, and source checksum. Verify the remote URLs, asset checksums, release
state, and public main-branch commit before reporting completion.
