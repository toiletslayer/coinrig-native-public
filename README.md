# coinrig-native — COIN HiveOS custom miner

**Public beta** of a HiveOS integration for the COIN-specific RandomX v2 miner
by [Scratcher / blackshirt-crypto](https://github.com/blackshirt-crypto/xmrig-coin).

Scratcher created the COIN-compatible XMRig patch. This project contributes a
HiveOS wrapper, hashrate statistics and a full-memory submission gate.
It does **not** claim authorship of his hashing implementation.

## Public beta release

Current release tag: `coinrig-native-v1.1.0-beta.3`.
The installable archive is named `coinrig-native-1.1.0_beta3.tar.gz`
and contains the unmodified verified upstream XMRig 6.26.0-coin binary.
[Release details](https://github.com/toiletslayer/coinrig-native-public/releases/tag/coinrig-native-v1.1.0-beta.3).

Direct HiveOS Installation URL: https://github.com/toiletslayer/coinrig-native-public/releases/download/coinrig-native-v1.1.0-beta.3/coinrig-native-1.1.0_beta3.tar.gz

beta.2 is superseded: real HiveOS exports `MINER_DIR=/hive/miners/custom`,
while the package is installed one level below it. beta.3 makes every callback
resolve its package files from the callback's own installed location. beta.1
is also superseded because it does not accept the HiveOS `rx2` dropdown value.

Source for the upstream miner (pinned to Scratcher's v6.26.0-coin tag) is
offered alongside the binary archive as a separate release asset.
This repository contains the wrapper's corresponding source and GPLv3 license.

## HiveOS flight sheet (32-thread reference)

- Coin: your existing COIN custom coin
- Wallet: your own COIN payout address (95-character primary address, C...)
- Pool: Configure in miner
- Miner: Custom
- Miner name: `coinrig-native`
- Installation URL: direct URL for the archive under the release page
- Hash algorithm in HiveOS: `rx2` (also accepts `rx/2`; internal miner remains `rx/2`)
- Wallet and worker template: `%WAL%` (no worker suffix)
- Pool URL: your trusted *mining-only* RFC1918 IPv4 gateway and port
- Password: `x`
- Extra config: empty or exactly `threads=32`

Do not point it directly to a publicly exposed unrestricted node RPC.
Public IP addresses and hostnames are rejected by design. The miner's RPC
statistics API and full-memory submission gate bind to loopback only.

## Safety and limitations

- Forced full-memory RandomX v2, no MSR writes, gate blocks submitblock until
  a 2336 MB dataset is ready.
- This is a **32-thread reference implementation**, not automatic CPU tuning.
- The original XMRig release may enforce a 1% development donation despite
  the `--donate-level=0` argument.
- The beta.2 path failure was reproduced from a real HiveOS worker. The beta.3
  correction has passed offline source and extracted-package lifecycle tests,
  but has not yet been started on that live worker. Treat this as beta software.

Run offline validation with `python -m unittest discover -s tests -v`.
See [security guidance](SECURITY.md), [integration detail](coinrig-native/README.md)
and [upstream attribution](coinrig-native/PROVENANCE.md).

## Licensing

GNU GPLv3 — see [LICENSE](coinrig-native/LICENSE).
Before redistributing a build, include or provide complete corresponding source
for the XMRig binary and retain the upstream license and attribution.
