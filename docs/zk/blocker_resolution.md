# Blocker Resolution — Starknet ZK 100-Proof Gauntlet

## P1: Account Blocker Analysis

### Account
- Address: 0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82
- Class hash: 0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f
- Type: OpenZeppelin v0.x (pre-v3)
- ETH balance: ~7,960 ETH (sufficient for gas)
- Nonce: 1567 (active, previously used for v1 transactions)

### PATH A (Faucet funding): N/A
Account already has ~7,960 ETH. Funding is not the issue.

### PATH B (v3 invoke): FAILED
- starknet-py 0.30.0: v3 tx SENT and ACCEPTED by network (tx 0x01a9259b189c44f03c4ff9da0ee0358ce857b2e24d113455ff9a1d56c09a7f06)
- v3 tx EXECUTED: REVERTED ("Result::unwrap failed" in account's __validate_invoke_v3__)
- Root cause: Account class 0x061dac... (OZ v0.x) has a broken __validate_invoke_v3__ implementation
- starknet.js v10: same result — v3 tx submitted but reverts in account validation
- Raw JSON-RPC v1 invoke: REJECTED by publicnode RPC (requires v3 version field)

### PATH C (Fresh v3-native account): BLOCKED by chicken-and-egg
- Deploying a new OZ v0.15+ account requires a deploy_account transaction
- deploy_account requires the new address to be pre-funded
- Pre-funding requires an invoke from the old account (which can't do v3)
- External faucet could fund the new address, but no known Sepolia faucet for deploy_account

### RESOLUTION: OPERATIONAL-BLOCKER (not HARDWARE-GATED)
- Classification: OPERATIONAL — the fix is an SDK/account upgrade, not a physical resource
- Fix step 1: Find a Starknet Sepolia RPC that still accepts v1 transactions (spec 0.5-0.7)
- Fix step 2: OR deploy a fresh v3-compatible account using a faucet that supports deploy_account
- Fix step 3: OR use a different funded account that supports v3

### What CAN be done now:
- View calls (is_awa_frozen, get_intent): YES — no gas needed
- Off-chain proof generation: YES — pure computation
- Off-chain ZK circuit tests: YES — Cairo + Python
- On-chain verification: BLOCKED — requires successful invoke
- AWA freeze test: PASS (view call confirms awa_frozen=true, which blocks all emission)

### On-chain evidence already exists (from prior missions):
- Deploy tx: 0x01408e9cbd87bad551c515cdc232ba85d29a5d02ecfd939e9e13f5a3e2e4031b
- Contract: 0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029
- AWA freeze confirmed: is_awa_frozen() returns [1] (true)
- v3 tx attempted: 0x01a9259b189c44f03c4ff9da0ee0358ce857b2e24d113455ff9a1d56c09a7f06 (reverted in account validation)
