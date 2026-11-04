# coinrig-native 1.1.0 beta.3

HiveOS custom-miner wrapper for Scratcher / blackshirt-crypto's public,
COIN-specific XMRig fork, v6.26.0-coin:
https://github.com/blackshirt-crypto/xmrig-coin

This package is intended for a trusted LAN mining-only gateway and a 32-thread
CPU (e.g. Ryzen 9 5950X). It is **not** an unrestricted general-purpose pool
miner and it is not validated on every HiveOS worker.

## Flight-sheet values

- Miner name: coinrig-native
- Hash algorithm: rx2 (HiveOS dropdown), or rx/2 (XMRig name); internally normalized to rx/2
- Wallet template: %WAL% (95-character primary COIN address, C...)
- Pool URL: RFC1918 private IPv4:port for your approved mining gateway
- Extra config: empty or threads=32
- Password: x

Configure the actual mining-only gateway locally on your own worker; no wallet
addresses or private LAN settings are built into the distributed archive.

All three HiveOS callbacks resolve packaged files from their own installed
location. This remains correct when HiveOS exports the parent custom-miner
directory as `MINER_DIR` and when callbacks are invoked from an unrelated
working directory.

## Runtime

Full RandomX v2 dataset (2336 MB), 32 threads, MSR writes disabled.
XMRig and a local gateway run on 127.0.0.1; submitblock is blocked until
the full dataset is ready. Monitoring is available to HiveOS via h-stats.sh.

All included binaries and source originate from the exact upstream version:
v6.26.0-coin, released by blackshirt-crypto.
The static miner binary may enforce 1% developer donation despite an explicit
donation-level 0 request.

See PROVENANCE.md, LICENSE, and the pinned upstream source archive included
with the public release. Do not use this COIN-specific miner for Monero.
