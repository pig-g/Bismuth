Bismuth Readme
=======
##### Warning: For production purposes, please only use code from the "releases" page, which is not in pre-release state.

### Official website:
* Dear CoinMarketCap, based on our communication, please update website URL to https://bismuth.cz

### Explorers:
* https://bismuth1.terranbase.xyz
* http://bismuth.online
* https://bismuth.im
* https://hypernodes.bismuth.live/?page_id=152

### Mainnet seed list:
`peers.txt` and `suggested_peers.txt` were refreshed on 2026-07-26 from nine
public nodes that returned an allowed protocol version and synchronized
`statusjson` data in two consecutive read-only probes at block 4,914,895.

### Wallets:
* [Tornado Wallet](https://github.com/bismuthfoundation/TornadoWallet)
* [tk-wallet](https://github.com/bismuthfoundation/tk-wallet)
* [BIS Paper Wallet](https://github.com/AngainorDev/BIS-Paper)
* [Android Mobile Wallet](https://github.com/redDwarf03/my_bismuth_wallet)

### Hypernodes website:
* https://hypernodes.bismuth.live
* https://bismuth.world

### Related repositories: 
* https://github.com/maccaspacca
* https://github.com/EggPool
* https://github.com/hclivess

### Links:

Bismuth Foundation: 
* https://github.com/bismuthfoundation

Market:
* [Exchange Implementation Guide](https://github.com/bismuthfoundation/Bismuth-FAQ/blob/master/Exchanges/How_to_Implement.md)
* [CoinGecko](https://www.coingecko.com/en/coins/bismuth)
* [CoinMarketCap](https://coinmarketcap.com/currencies/bismuth/)

### Social:
* [Discord](https://discord.gg/dKVZd4z)
* [Blog](https://hypernodes.bismuth.live/?page_id=20)
* [Reddit](https://www.reddit.com/r/cryptobismuth)
* [Facebook](https://web.facebook.com/cryptobismuth)
* [Telegram I](https://t.me/cryptobismuth)
* [Telegram II](https://t.me/bismuthplatform)
* [Egg's Twitter](https://twitter.com/EggPoolNet)
* [Jan's Twitter](https://twitter.com/bismuthdev)
* [Bismuth Twitter](https://twitter.com/BismuthPlatform)


### CI:
[![Build Status](https://travis-ci.org/bismuthfoundation/Bismuth.svg?branch=master)](https://travis-ci.org/bismuthfoundation/Bismuth)

### Practical learning labs:

Start with [Practical Labs 0–8](labs/README.md) for newcomer instructions that
cover the correct GitHub branch, ZIP or Git download, Python 3.11 setup, and the
exact macOS/Linux commands. Labs 0–5 use only an isolated local regnet,
temporary wallets, and valueless test BIS; Labs 6–8 are short read-only
simulations (difficulty feedback, fork rules, token reindex) that start no node.
They do not connect to mainnet.

A separate optional [Mainnet Interaction Track](labs/mainnet-interaction/README.md)
observes the real Bismuth mainnet (read only) and, at the learner's choice with a
small trial BIS balance, locally signs and sends a small trial amount. It never
sends a private key to a node and always prints a real-mainnet warning.


### Regnet tests
The test suite starts an isolated regnet node bound to `127.0.0.1:3030`.
It creates temporary ledger, index, peer, log, and wallet files and removes
them with the pytest temporary directory.

```bash
./scripts/test_regnet.sh
```

The script recreates `.venv`, installs the dependency graph pinned in
`tests/constraints.txt`, and runs the complete suite. Set `PYTHON` to select
the Python 3.11 interpreter.

The fixture waits for a successful `portget` RPC response instead of using a
fixed startup delay. It fails with the node output if startup does not finish
within 30 seconds or if port 3030 is already in use.
