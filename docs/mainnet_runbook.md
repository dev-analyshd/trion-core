# TRION Protocol — Mainnet Deployment Runbook

> **Scope**: this runbook covers the full TRION protocol mainnet
> deployment (oracle, validator mesh, relayer, FAISS service, Akashic
> ledger, token contract, governance). It supersedes the BTC↔Starknet
> zero-bridge runbook that previously occupied this file (that content
> has been moved to `proofs/btcp-zero-bridge/starknet/BTC_STARKNET_ZERO_BRIDGE.md`
> where it belongs).

## 1. Pre-deployment checklist

### 1.1 Validator set

- [ ] **100 validators minimum** registered in the epoch registry
      (`contracts/solidity/TrionEpochRegistry.sol`).
- [ ] Validators distributed across **≥ 4 continents** (F9 falsifiability
      condition — see `core/governance/falsifiability_registry.py`).
      Continent codes: NA, EU, ASIA, ME, AF, SA, OC.
- [ ] **No single validator controls > 10% of total effective stake**
      (`stake × diversity` weight). Enforced by `HHI ≤ 2500` (F8).
- [ ] At least **2/3 of effective weight** is online and signing during
      the deployment window (L4.2 tier-1 quorum).
- [ ] Each validator has registered:
      - secp256k1 pubkey (family 1 — EVM/Starknet)
      - Ed25519 pubkey (family 2 — SVM/NEAR/Move)
      - stake weight, diversity weight
- [ ] Validator mesh daemon (`trion-validator`) running on `:6000` for
      each validator, peered with at least 8 others.

### 1.2 Token & treasury

- [ ] **TRION token contract deployed** (`contracts/vyper/TRIONToken.vy`
      or `contracts/solidity/TRIONToken.sol` if Vyper is unavailable on
      the target chain).
- [ ] **Treasury multisig** configured (3-of-5) and funded with
      operational gas budget (≥ 5 ETH on Arbitrum).
- [ ] Token allocations: validator incentives, community grants, team
      (with vesting cliffs ≥ 12 months), treasury reserve.
- [ ] **Relayer key funded**: the relayer account holds ≥ 0.5 ETH on
      Arbitrum One to cover signal publication gas for the first 30
      days.

### 1.3 Contracts

- [ ] `TRIONOracleV3.sol` compiled with `solc 0.8.20+` via IR pipeline.
- [ ] `TrionEpochRegistry.sol` compiled and address recorded.
- [ ] `BTCPEscrow.sol` + `BTCSPVVerifier.sol` + `BTCSPVVerifierArb.sol`
      compiled and addresses recorded.
- [ ] Canonical certificate library (`libraries/CanonicalCertificate.sol`)
      linked into the oracle and escrow binaries.
- [ ] **Upgrade plan documented** — TRION contracts are deployed
      WITHOUT proxies (immutable bytecode). Bug fixes require
      redeployment + state migration. See
      `docs/oracle_publishSignalWithType.md` for the canonical typed
      signal upgrade procedure.

### 1.4 Services

- [ ] **FAISS service** (`anima-service/faiss_service.py`) deployed and
      health-checking on `:8000`. The service must report
      `total_bh_records ≥ 100` before the first signal emission.
- [ ] **Oracle API** (`api/app.py`) deployed on `:5000` behind nginx +
      gunicorn (2 workers minimum, see `deploy/docker/Dockerfile.api`).
- [ ] **Validator mesh** running on `:6000` (one process per validator;
      see `deploy/systemd/trion-validator.service`).
- [ ] **Relayer** configured with `RELAYER_PRIVATE_KEY` env var (or
      `KMS_PROVIDER` for AWS KMS-backed signing) — see
      `api/blockchain.py::ChainRelay._init`.
- [ ] **PostgreSQL/TimescaleDB** for Akashic hypertables (optional in
      bootstrap phase; SQLite fallbacks exist for `bh_ledger.db` and
      `annotations.db`).

### 1.5 Behavioral sediment (genesis backfill)

- [ ] Genesis backfill has populated `bh_ledger.db` with **≥ 100 real
      behavioral hashes** for at least one EVM chain (see Fix 9 /
      `scripts/genesis_backfill_runner.py`). The first signal cannot
      be emitted without this — the cold-start guard in
      `api/app.py::_plane_values` will return `COLD_START` until
      FAISS reports behavioral history.

## 2. Deployment sequence

### 2.1 Deploy contracts

```bash
cd /home/z/my-project/trion-core
# 1. Compile all Solidity contracts (via IR, optimised)
solc --via-ir --optimize --bin \
  contracts/solidity/TRIONOracleV3.sol \
  contracts/solidity/TrionEpochRegistry.sol \
  contracts/solidity/BTCPEscrow.sol \
  contracts/solidity/BTCSPVVerifier.sol \
  -o build/mainnet/ --overwrite

# 2. Deploy epoch registry (no constructor args)
REGISTRY=$(cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  build/mainnet/TrionEpochRegistry.bin | jq -r .contractAddress)

# 3. Deploy oracle (bind registry in constructor)
ORACLE=$(cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  --create2 $(cast wallet address $RELAYER_PRIVATE_KEY) \
  build/mainnet/TRIONOracleV3.bin $REGISTRY | jq -r .contractAddress)

# 4. Bind the registry on the oracle (one-way; owner-gated)
cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  $ORACLE "setEpochRegistry(address)" $REGISTRY

# 5. Deploy BTC SPV verifier + escrow
SPV=$(cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  build/mainnet/BTCSPVVerifier.bin $(cast wallet address $RELAYER_PRIVATE_KEY) true \
  | jq -r .contractAddress)

ESCROW=$(cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  build/mainnet/BTCPEscrow.bin $(cast wallet address $RELAYER_PRIVATE_KEY) \
  | jq -r .contractAddress)

cast send --private-key $RELAYER_PRIVATE_KEY \
  --rpc-url $ARB_ONE_RPC \
  $ESCROW "set_trion_oracle(address)" $ORACLE
```

Record every address in `proof-ledger/deployments.json` (create the
file if it does not exist) and in `docs/deployments/evm_mainnet.json`.

### 2.2 Initialize the epoch registry ceremony

```bash
# Owner calls add_validator for each of the 100 validators, then seals epoch 1
for v in $(cat deploy/validators.txt); do
  cast send --private-key $RELAYER_PRIVATE_KEY --rpc-url $ARB_ONE_RPC \
    $REGISTRY "add_validator(address,uint256,uint256)" \
    $v 1000000 800000   # stake=1.0×1e6, diversity=0.8×1e6
done

cast send --private-key $RELAYER_PRIVATE_KEY --rpc-url $ARB_ONE_RPC \
  $REGISTRY "seal_epoch(uint32)" 1
```

### 2.3 Emit the first signal

The first signal emission is the canonical mainnet genesis event. See
`proof-ledger/first_signal.json` for the full emission plan and to
record the resulting `first_signal_tx_hash`.

```bash
# 1. Verify FAISS has behavioral sediment
curl -s $FAISS_BASE/health | jq .total_bh_records  # must be ≥ 100

# 2. Trigger publication via the API
curl -X POST $API_BASE/api/v1/publish/uniswap

# 3. Record the tx hash
jq '.first_signal_tx_hash = "<tx-hash-from-step-2>"' \
  proof-ledger/first_signal.json > /tmp/fs.json && \
  mv /tmp/fs.json proof-ledger/first_signal.json
git commit -am "proof-ledger: record first mainnet signal tx hash"
```

### 2.4 Emit the first SILENCE

Even when the AWA gate is frozen (intentionally or due to a transient
condition), the first SILENCE must be emitted to demonstrate the
structured-null payload. Record its tx hash in
`proof-ledger/first_signal.json::first_silence_tx_hash`.

### 2.5 Emit the first GENESIS signal

The genesis signal (`SignalType.GENESIS`) is the protocol's birth
certificate. It carries the initial epoch registry root hash and is
signed by every validator in the first sealed epoch. Record its tx
hash in `proof-ledger/first_signal.json::first_genesis_tx_hash`.

## 3. Post-deployment verification

### 3.1 On-chain signal count

```bash
cast call $ORACLE "totalBehavioralSignals()" --rpc-url $ARB_ONE_RPC
# Expected: ≥ 3 after the three first-emission transactions above.
```

### 3.2 AWA gate enforcement

```bash
curl -s $API_BASE/api/v1/governance/awa | jq .enforced
# Expected: true (or false with a documented freeze reason).
# AWA enforcement is the MD §17 anti-weaponization guarantee: while
# frozen, no VALUATION signals can be published — only SILENCE.
```

### 3.3 HHI monitoring

```bash
curl -s $API_BASE/api/v1/validator/hhi | jq .
# Expected: hhi ≤ 2500 (F8 falsifiability condition).
# Alerts fire at hhi > 2000 (warning) and hhi > 2500 (critical —
# auto-corrective slashing kicks in).
```

### 3.4 Validator mesh health

```bash
curl -s http://127.0.0.1:6000/consensus/hhi | jq .
# Expected: validators.length ≥ 100, all active.
```

### 3.5 Akashic ledger depth

```bash
sqlite3 bh_ledger.db "SELECT COUNT(*) FROM bh_ledger"
# Expected: monotonically increasing; must be ≥ 100 immediately after
# the first signal emission (the genesis backfill seeds it; the
# real-time streamer grows it).
```

## 4. Rollback procedure

TRION contracts are immutable — there is no on-chain rollback. The
rollback procedure is therefore a **coordinated re-deployment + state
migration**:

1. **Freeze the relayer** — stop the `trion-relayer` systemd unit.
2. **Pause the oracle** — call `pause()` on `TRIONOracleV3` (only
   owner; emits `Paused` event). No new signals can be published
   while paused; `verifyExecution` continues to return the last
   recorded verdict.
3. **Diagnose** — read the most recent events (`BehavioralSignalPublished`,
   `SilenceRecorded`, `SignalTypeRecorded`) to identify the failure point.
4. **Re-deploy** if a contract bug is confirmed:
   - Deploy a fresh `TRIONOracleV3` at a new address.
   - Migrate every entity's `behavioralSignals[entityId]` +
     `signalTypeByEntity[entityId]` via `publishSignalWithType` on the
     new contract (use the off-chain Akashic record for the type byte).
   - Re-register every validator (`addValidator`) and re-seal the
     current epoch (`seal_epoch`).
5. **Cut over** — update `ORACLE_ADDRESS` env var on the relayer,
   restart it, verify with `/api/v1/onchain/<entity_id>`.
6. **Decommission** the old contract — drain relay-held ETH, mark the
   address as deprecated in `proofs/oracle/` and in
   `proof-ledger/deployments.json`.

### 4.1 State-recovery from Akashic

The Akashic ledger (`bh_ledger.db` SQLite, or the TimescaleDB
hypertable when `psycopg2` is installed) is the source of truth for
every behavioral observation. If a contract is re-deployed, the
off-chain Akashic record is used to replay every published signal:

```bash
python3 scripts/replay_signals_to_new_oracle.py --new-oracle $NEW_ORACLE
```

(See `scripts/deploy_mainnet.py` and `scripts/mainnet_preflight.py`
for the existing re-deployment tooling.)

## 5. Monitoring and alerting

### 5.1 Prometheus metrics

Deployed via `deploy/monitoring/prometheus.yml` + Grafana dashboards
(`deploy/monitoring/grafana/dashboards/`). Key metrics:

- `trion_signals_published_total` (counter)
- `trion_silence_recorded_total` (counter)
- `trion_coherence_score` (histogram, per entity)
- `trion_validator_hhi` (gauge)
- `trion_awa_enforced` (gauge, 0/1)
- `trion_bh_ledger_rows` (gauge)
- `trion_faiss_vectors` (gauge)
- `trion_publication_latency_seconds` (histogram)

### 5.2 Alerting rules

Defined in `deploy/monitoring/alerts.yml`. Critical alerts (page
on-call):

- `AWAFreezeActive` — AWA gate has been frozen for > 5 minutes.
- `HHICritical` — validator HHI > 2500 (F8 violation threshold).
- `SignalPublicationStall` — no `BehavioralSignalPublished` event in
  30 minutes when the queue is non-empty.
- `ValidatorMeshQuorumLoss` — fewer than 2/3 of effective weight online.
- `FAISSStaleVectors` — `bh_ledger_rows` not growing for 5 minutes.
- `OraclePaused` — `Paused` event emitted on the oracle contract.

### 5.3 Log aggregation

All services emit structured JSON logs (see `_log` in `api/app.py`).
Forward to the operator's log aggregator (Loki, Datadog, CloudWatch).

## 6. Trust statement

> Trust = an immutable epoch-sealed validator set + the AWA gate
> (MD §17) + the L4.2 weight quorum + the canonical 346-byte
> certificate + honest disclosure of every bootstrap input. No single
> entity — including the deployer — can override signal emission.
> SILENCE is information: a frozen oracle still emits structured
> silence records so consumers can verify the freeze is intentional.

## 7. Related documents

- `docs/oracle_publishSignalWithType.md` — canonical typed-signal
  deployment & upgrade path.
- `docs/canonical_certificate_verification_audit.md` — cross-VM
  certificate verification audit (which VMs have full verification).
- `docs/DEPLOYMENT.md` — general deployment topology (companion).
- `proof-ledger/first_signal.json` — first-signal emission plan and
  tx-hash record (updated by this runbook's §2.3).
- `proofs/btcp-zero-bridge/starknet/BTC_STARKNET_ZERO_BRIDGE.md` —
  the BTC↔Starknet zero-bridge runbook previously occupying this file.
