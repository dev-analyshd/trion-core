# TRION Protocol — Federated Validator Deployment

This directory contains everything an operator needs to run **TRION Protocol**
as a **decentralized, federated cluster of full validators** — no single node
holds privileged state, no operator needs an HSM to participate, and every
validator runs the entire stack end-to-end (Python Oracle + ANIMA FAISS +
Rust indexers + Go mesh daemon).

The directory is **headless only** — there is no dashboard, no frontend, no
Next.js. Operators interact with the cluster over the Oracle REST API and the
Go validator's `/healthz` endpoint.

---

## What the federated deployment is

A TRION **federation** is 4–5 (or more) validators, each running an identical
copy of the full TRION stack:

| Component              | Binary / entrypoint                        | Default port | Source |
| ---------------------- | ------------------------------------------ | -----------: | ------ |
| Python Oracle API      | `serve.py` (Flask)                          | `5000` | `serve.py` |
| ANIMA FAISS engine     | `anima-service/faiss_service.py` (uvicorn) | `8001` | `anima-service/faiss_service.py` |
| Rust L0 indexer(s)     | `indexers/target/release/trion-<family>`   |   –    | `indexers/crates/trion-*/src/main.rs` |
| Go validator daemon    | `validator/trion-validator`                 | `7001` (mesh) + `7080` (`/healthz`) | `validator/cmd/trion-validator/` |

Every validator shares a **single TimescaleDB cluster** pointed at by
`TIMESCALEDB_URL` — the schema is multi-tenant via the `validator_id`
column. Behavioral attestations are gossiped peer-to-peer over the Go mesh
on `:7001` (Diversity-Weighted BFT, whitepaper L4); the Oracle API exposes
the public read path + the `X-API-Key`-protected write path.

### Software-key model (`KMS_PROVIDER=env`, NO HSM)

The federated profile uses **software keys**, not HSMs:

- `KMS_PROVIDER=env` is the value the relayer's KMS abstraction layer
  (`relayer/kms_provider.js`) routes to the plaintext `RELAYER_PRIVATE_KEY`
  branch. The relayer constructs an in-memory `ethers.Wallet` and signs
  EIP-191 quorum attestations with it.
- `TRION_ALLOW_RAW_ENV_KEYS=1` is the explicit operator acknowledgment that
  env-custodied keys are intentional. The default TRION_ENV=production guard
  in `scripts/start_trion.sh` would otherwise refuse to start; the federated
  launcher sets this var so the relayer loads `RELAYER_PRIVATE_KEY` cleanly.
- For **production mainnet**, swap `KMS_PROVIDER` to `aws` / `gcp` / `yubihsm`
  / `pkcs11`, remove `RELAYER_PRIVATE_KEY`, and provision the corresponding
  HSM/KMS env vars. The five-provider abstraction is documented in
  `relayer/kms_provider.js` — no code changes needed, just env rotation.

The federated dev/test profile is the **only** path that uses env keys; for
mainnet custody the same `start_validator_full.sh` works unchanged once
`KMS_PROVIDER` is switched (the relayer will simply ignore
`RELAYER_PRIVATE_KEY` and call the configured KMS instead).

---

## Files in this directory

| File | Purpose |
| ---- | ------- |
| `start_validator_full.sh` | Bash launcher — boots the full stack on one node, manages PID files, traps SIGTERM/SIGINT, supports `--stop` / `--status` / `--help`. |
| `validator.env.example` | Template env file — copy to `validator.env` and fill in. Documents every var the launcher / services read. |
| `docker-compose.federated.yml` | 4 validator containers + 1 shared TimescaleDB. Use for local clusters. |
| `systemd/trion-validator-full.service` | systemd unit for bare-metal / VM deployment. |
| `README.md` | (this file) |

---

## Quick start: 4 validators locally with docker-compose

The compose file brings up 4 validators (`validator-1` through `validator-4`)
sharing one TimescaleDB. Each validator's ports are offset so they don't
collide on a single host:

| Validator | Oracle (host:ctr) | FAISS (host:ctr) | Mesh (host:ctr) | healthz (host:ctr) |
| --------- | ----------------: | ---------------: | --------------: | -----------------: |
| validator-1 | `5001:5000` | `8001:8001` | `7001:7001` | `7081:7080` |
| validator-2 | `5002:5000` | `8002:8001` | `7002:7001` | `7082:7080` |
| validator-3 | `5003:5000` | `8003:8001` | `7003:7001` | `7083:7080` |
| validator-4 | `5004:5000` | `8004:8001` | `7004:7001` | `7084:7080` |

### Steps

```bash
cd /path/to/trion-core/deploy/federated

# 1. Generate two API keys (32-byte hex, no 0x prefix) and a relayer key.
openssl rand -hex 32   # → TRION_API_KEY
openssl rand -hex 32   # → FAISS_API_KEY

# 2. Create your env file from the template.
cp validator.env.example validator.env
# Edit validator.env:
#   TRION_API_KEY=<paste hex 1>
#   FAISS_API_KEY=<paste hex 2>
#   RELAYER_PRIVATE_KEY=0x<your 32-byte EVM private key>
#   TRION_VALIDATOR_REGION=NA-US   (per-validator overrides come from compose)

# 3. (Optional) Build the Go validator + Rust indexers on the host so they
#    can be mounted into the containers. Skip if you only need FAISS + Oracle.
(cd ../../validator && go build -o trion-validator ./cmd/trion-validator/)
(cd ../../indexers   && cargo build --release -p trion-evm)

# 4. Bring up the cluster (builds the Python image on first run).
docker compose -f docker-compose.federated.yml up --build -d

# 5. Watch it come up.
docker compose -f docker-compose.federated.yml ps
docker compose -f docker-compose.federated.yml logs -f validator-1

# 6. Probe the four validators' health endpoints.
for p in 5001 5002 5003 5004; do
  echo "→ http://localhost:$p/api/v1/health"
  curl -fsS "http://localhost:$p/api/v1/health" -H "X-API-Key: $(grep ^TRION_API_KEY= validator.env | cut -d= -f2)" | head
done

# 7. Tear it down (keeps volumes).
docker compose -f docker-compose.federated.yml down
```

The compose file mounts `../../schema.sql` into TimescaleDB's
`/docker-entrypoint-initdb.d/` — the schema is loaded **only on first boot**
(when the `timescale-data` volume is empty). Subsequent `up`s reuse the
existing schema and data.

---

## Bare-metal / VM: one validator with systemd

For production, deploy each validator on its own host (4–5 hosts for a real
federation). On each host:

```bash
# 1. Drop the repo at /opt/trion (or wherever — adjust WorkingDirectory).
sudo cp -r /path/to/trion-core /opt/trion
sudo cp /opt/trion/deploy/federated/start_validator_full.sh /opt/trion/
sudo cp /opt/trion/deploy/federated/validator.env.example /opt/trion/validator.env
sudo chmod 700 /opt/trion/validator.env
sudo $EDITOR /opt/trion/validator.env   # fill in secrets

# 2. Create the dedicated system user.
sudo useradd --system --no-create-home --shell /usr/sbin/nologin trion
sudo chown -R trion:trion /opt/trion

# 3. Pre-build the Rust + Go binaries (Python deps are in the system venv
#    or the /home/z/.venv venv referenced by PYTHON_BIN).
(cd /opt/trion/validator && go build -o trion-validator ./cmd/trion-validator/)
(cd /opt/trion/indexers   && cargo build --release -p trion-evm)

# 4. Install the unit + start it.
sudo cp /opt/trion/deploy/federated/systemd/trion-validator-full.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trion-validator-full
sudo systemctl status trion-validator-full
sudo journalctl -u trion-validator-full -f
```

The unit reads env vars from `/opt/trion/validator.env` via
`EnvironmentFile=`, runs `start_validator_full.sh` as `ExecStart`, and uses
`start_validator_full.sh --stop` as `ExecStop`. `KillMode=process` lets the
launcher's SIGTERM trap cascade cleanly to every child.

### Operational commands

```bash
# Live status (without going through systemd):
sudo -u trion /opt/trion/start_validator_full.sh --status

# Restart the whole stack:
sudo systemctl restart trion-validator-full

# Stop the stack gracefully:
sudo systemctl stop trion-validator-full

# Apply env changes (just restart — no daemon-reload needed for env-only):
sudo $EDITOR /opt/trion/validator.env
sudo systemctl restart trion-validator-full
```

---

## Verifying the mesh is working

Once the cluster is up, verify each layer in turn:

### 1. TimescaleDB reachable from every validator

```bash
for p in 5001 5002 5003 5004; do
  curl -fsS "http://localhost:$p/api/v1/health" \
    | grep -q '"status"' && echo "validator on :$p ✓"
done
```

The Oracle's `/api/v1/health` endpoint checks its own state *and* the FAISS
service *and* TimescaleDB connectivity — if it returns `200` the entire
per-validator Python stack is wired.

### 2. FAISS engine indexing live

```bash
for p in 8001 8002 8003 8004; do
  echo "→ FAISS on :$p"
  curl -fsS "http://localhost:$p/health"
  curl -fsS "http://localhost:$p/index/stats" \
       -H "X-API-Key: $(grep ^FAISS_API_KEY= validator.env | cut -d= -f2)"
done
```

Each FAISS instance should report a growing `total` vector count as the
Rust indexers feed behavioral hashes into it.

### 3. Go validator mesh up

```bash
for p in 7081 7082 7083 7084; do
  echo "→ validator /healthz on :$p"
  curl -fsS "http://localhost:$p/healthz"
done
```

Each validator should return `{"status":"ok","service":"trion-validator",...}`.

### 4. Diversity-Weighted BFT quorum

Once 3+ validators have gossiped ≥3 attestations for the same entity,
`GET /sigmascore` on any validator returns `sigma > 0.25` (the cold-start
default) — meaning live Σ-plane data has displaced the bootstrap value:

```bash
curl -fsS http://localhost:7081/sigmascore | jq .
```

### 5. Peer-to-peer mesh connectivity (bare-metal only)

If `TRION_BOOTSTRAP_PEERS` is set on each validator, the Go mesh dials the
listed peers on startup and the `peers` field on `/healthz` reflects the
count of reachable peers. For docker-compose, the validators share the
compose network — set `TRION_VALIDATOR_ADDR=0.0.0.0:7001` and configure
peers via service name (`validator-2:7001`, etc.).

---

## Adding a 5th validator

### With docker-compose

Append a `validator-5` block to `docker-compose.federated.yml` — copy the
`validator-4` block verbatim and:

- Change `container_name` to `trion-validator-5`.
- Change `TRION_VALIDATOR_ID` to `validator-5`.
- Override `TRION_VALIDATOR_REGION_5` (or hardcode it in the env block).
- Offset the host ports to `5005:5000`, `8005:8001`, `7005:7001`, `7085:7080`.
- Add `validator-5-state` and `validator-5-logs` to the `volumes:` block.

Then `docker compose -f docker-compose.federated.yml up -d validator-5`
brings the new node in without disturbing the existing 4.

### On bare metal

Provision a fresh host, follow the [bare-metal install](#bare-metal--vm-one-validator-with-systemd)
steps, set `TRION_VALIDATOR_ID=validator-5` and `TRION_VALIDATOR_REGION=AF-ZA`
in `/opt/trion/validator.env`, point `TIMESCALEDB_URL` at the shared cluster,
and `systemctl enable --now trion-validator-full`.

If the new node should bootstrap from existing peers, also set
`TRION_BOOTSTRAP_PEERS=validator-1.example.com:7001,validator-2.example.com:7001`
before starting — the Go mesh will dial them on startup so its DW-BFT view
converges without manual `AddPeer` RPCs.

---

## Software-key model vs HSM

The federated profile defaults to **software keys** (`KMS_PROVIDER=env`):

| Aspect              | `KMS_PROVIDER=env` (federated default)      | HSM-backed (`aws`/`gcp`/`yubihsm`/`pkcs11`)         |
| ------------------- | ------------------------------------------- | -------------------------------------------------- |
| Key material        | `RELAYER_PRIVATE_KEY` env var (plaintext)   | Lives inside the HSM boundary; never exported     |
| Signing path        | `ethers.Wallet.signDigest()` in-process    | `SignCommand` over network / PKCS#11 session       |
| Audit trail         | OS env-var access logs                      | HSM audit log (FIPS 140-2/3 compliant)             |
| Compromise impact   | Full key theft if env leaks                | Key theft requires physical HSM access              |
| Use case            | Dev / testnet / federated test clusters    | Production mainnet, regulated deployments           |
| Setup complexity    | One env var                                | KMS IAM role + key-id / HSM provisioning ceremony |

The relayer's KMS abstraction (`relayer/kms_provider.js`) exposes a uniform
`{ address, signMessage, signDigest }` interface for all five providers —
switching from `env` to `aws` is a single env-var rotation, no code changes:

```bash
# validator.env (production cut-over)
KMS_PROVIDER=aws
AWS_KMS_KEY_ID=arn:aws:kms:us-east-1:111122223333:key/abcd-...
AWS_REGION=us-east-1
# RELAYER_PRIVATE_KEY is now IGNORED — remove it from the env file.
```

See `relayer/kms_provider.js` for the full per-provider env matrix.

---

## Troubleshooting

### `start_validator_full.sh` exits with "missing required environment"

Set every var listed in the error message — see `validator.env.example` for
the canonical list and inline documentation.

### FAISS not healthy within 60s

The first boot loads the BH ledger schema and may take longer than 60s on
slow disks. Either raise the budget in the `wait_healthy` call (edit
`start_validator_full.sh`) or simply re-run the launcher — the Oracle will
retry the connection.

### Oracle API returns 503 `auth_not_configured`

`TRION_API_KEY` is empty. The Oracle fails **closed** when the API key is
unset (writes + non-GET routes return 503). Generate one with
`openssl rand -hex 32` and put it in `validator.env`.

### Go validator binary missing

`start_validator_full.sh` looks for `${TRION_HOME}/validator/trion-validator`.
Build it once with:

```bash
(cd ${TRION_HOME}/validator && go build -o trion-validator ./cmd/trion-validator/)
```

If you have no Go toolchain on the host, the launcher logs a warning and
skips the Go mesh — the FAISS + Oracle + indexer stack still comes up
(useful for pure indexer / Oracle replicas).

### Rust indexer binary missing

The launcher iterates `INDEXER_FAMILIES` (default `evm`) and warns for any
family whose binary is missing. Build the ones you want:

```bash
(cd ${TRION_HOME}/indexers && cargo build --release -p trion-evm -p trion-svm)
```

### `docker compose up` complains about `validator.env` not found

`cp validator.env.example validator.env` first. The compose file marks the
`env_file` as `required: false` (compose v2.24+) so it doesn't fail when
absent — but you still want it for the secret values.

---

## Architecture notes

- **One TimescaleDB, many validators.** All validators in a federation share
  the same `TIMESCALEDB_URL`. The schema uses `validator_id` columns on
  every writer table so writes are isolated. Read paths (Oracle
  `/api/v1/health`, `/api/v1/akashic/<entity>`) aggregate across validators.
- **Mesh on `:7001` is for attestations, not data.** The Go mesh gossips
  behavioral attestations and TRION-BFT consensus messages. Heavy data
  (BH streams, vector batches) flows Oracle ↔ FAISS over loopback.
- **No dashboard.** Every observability surface is HTTP JSON:
  `GET /api/v1/health` (Oracle), `GET /health` (FAISS),
  `GET /healthz` + `/sigmascore` + `/attestations` (Go validator).
- **Software-key custody is intentional.** The federated profile targets
  dev / testnet / community-run validators. Production mainnet custody MUST
  switch to `KMS_PROVIDER=aws|gcp|yubihsm|pkcs11` — see the matrix above.
