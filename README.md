# coinrig-native — COIN HiveOS integration

A public **source-only preview** of the HiveOS wrapper for the COIN-specific
RandomX v2 miner by [Scratcher / blackshirt-crypto](https://github.com/blackshirt-crypto/xmrig-coin).
Scratcher built the native COIN hashing implementation. This project provides
HiveOS integration scripts and a local submission safety gate.

The public source includes:
- HiveOS h-config, h-run, h-stats, h-manifest integration callbacks.
- Python submission gate that blocks submitblock before full dataset readiness.
- Endpoint validation allowing only RFC1918 private IPv4 host and port.
- Provenance, upstream GPLv3 license, and endpoint contract tests.

This is NOT a ready-to-install public HiveOS package. There is no published
binary or release asset. It is currently a 32-thread reference configuration.
Other hardware and gateway configurations require independent testing.
No actual wallet addresses, credentials, or private mining history are included.

Original COIN-compatible XMRig: https://github.com/blackshirt-crypto/xmrig-coin
The upstream project is GPLv3. See coinrig-native/LICENSE and
coinrig-native/PROVENANCE.md. Distributing a compiled binary requires
corresponding-source compliance.
