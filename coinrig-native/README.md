# coinrig-native 1.1.0 beta.5 release candidate

HiveOS custom-miner wrapper for Scratcher / blackshirt-crypto's public,
COIN-specific XMRig fork, v6.26.0-coin:
https://github.com/blackshirt-crypto/xmrig-coin

This package is intended for a trusted LAN mining-only gateway and an explicitly
configured CPU thread count. It is **not** an unrestricted general-purpose pool
miner and it is not validated on every HiveOS worker.

## Flight-sheet values

- Miner name: coinrig-native
- Hash algorithm: rx2 (HiveOS dropdown), or rx/2 (XMRig name); internally normalized to rx/2
- Wallet template: %WAL% (95-character primary COIN address, C...)
- Pool URL: RFC1918 private IPv4:port for your approved mining gateway
- Extra config: exactly `threads=N`, where N is 1-256; empty defaults to 32
- Password: x

Configure the actual mining-only gateway locally on your own worker; no wallet
addresses or private LAN settings are built into the distributed archive.
The Extra config parser accepts no other key, whitespace, sign, leading zero,
suffix, or additional argument. It never evaluates the supplied text.

For a Ryzen 9 3900, use `threads=24`. Existing beta.4 flight sheets remain
compatible: empty Extra config and `threads=32` both select 32 threads.

All three HiveOS callbacks resolve packaged files from their own installed
location. This remains correct when HiveOS exports the parent custom-miner
directory as `MINER_DIR` and when callbacks are invoked from an unrelated
working directory.

## Runtime

Full RandomX v2 dataset (2336 MB), the validated 1-256 thread selection, and
MSR writes disabled.
XMRig and a local gateway run on 127.0.0.1; submitblock is blocked until
the full dataset is ready. Monitoring is available to HiveOS via h-stats.sh.
Launcher and gateway events remain in HiveOS's `coinrig-native.log`. XMRig's
native output is written to `xmrig.log` in the installed package directory;
the launcher clears that file before each start so readiness can only come
from the current XMRig process.
The launcher derives `--threads` only from the validator's successful reading
of the generated sequential `rx/2` CPU profile; it does not re-use raw Extra
config text.

All included binaries and source originate from the exact upstream version:
v6.26.0-coin, released by blackshirt-crypto.
The static miner binary may enforce 1% developer donation despite an explicit
donation-level 0 request.

See PROVENANCE.md, LICENSE, and the pinned upstream source archive included
with the public release. Do not use this COIN-specific miner for Monero.
