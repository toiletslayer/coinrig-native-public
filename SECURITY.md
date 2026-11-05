# Security and operating boundaries

This is a **beta** HiveOS integration for COIN. Only use a mining-only COIN
JSON-RPC gateway that you operate or trust; never expose your wallet's RPC
credentials, seed phrases, or unrestricted daemon RPC to a public network.

- The gateway is restricted to an RFC1918 IPv4 host and TCP port.
- That check does **not** authenticate the gateway or encrypt LAN traffic.
  Restrict clients through the gateway's allowlist and firewall.
- The local submission gate blocks submitblock until the current miner log
  confirms full RandomX dataset allocation. It is not a formal proof of hash
  correctness and cannot guarantee no other implementation defects.
- Never run this miner in RandomX light mode for COIN.
- Extra config is limited to exact `threads=N` syntax for N from 1 to 256.
  Empty Extra config retains the beta.4 default of 32. No other XMRig option is
  accepted through this field.
- The miner's local HTTP statistics API binds to 127.0.0.1 only.
- No wallet keys or credentials belong in a public repository or bug report.

Report vulnerabilities via private contact with the project owner rather than
posting live wallet secrets, network access details, or exploitation payloads.
