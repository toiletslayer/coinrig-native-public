# coinrig-native — HiveOS integration source

This wrapper uses [Scratcher / blackshirt-crypto's COIN-specific XMRig
fork](https://github.com/blackshirt-crypto/xmrig-coin). Scratcher is the
author of the COIN-compatible mining engine; these scripts are an independent
HiveOS launcher, stats integration, and local full-dataset submission gate.

Requirements: HiveOS x86-64, Bash, Python 3, the compatible upstream XMRig
executable, a 95-character COIN payout address beginning with C, and a trusted
mining-only RPC gateway on a private RFC1918 IPv4 LAN.

HiveOS fields:
- Coin: COIN (custom)
- Miner: Custom; name: coinrig-native
- Algorithm: rx/2
- Wallet template: %WAL% with no worker suffix
- Pool URL: your trusted RFC1918 private IPv4 host:port
- Extra config: empty or threads=32

This is a 32-thread reference profile, not an automatic CPU optimizer. It pins
RandomX to full-memory, disables MSR writes, serves metrics on loopback only,
and blocks submitblock until a 2336 MB full dataset is ready.

Source-only preview: no public binary asset or installer is released.
This generalized integration has not been tested on additional HiveOS rigs.
The upstream binary may enforce a 1% developer donation despite the
--donate-level=0 argument.

License and origin: LICENSE and PROVENANCE.md.
