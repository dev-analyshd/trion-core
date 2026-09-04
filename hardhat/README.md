# hardhat/ — Real-EVM contract test harness

Self-contained Hardhat suite for the EVM-tier TRION/BTCP contracts
(`npx hardhat test` on the in-process network — see `hardhat.config.ts` for
the fail-closed mainnet key policy).

## Contract twins — byte-identity policy (W4-Q)

`hardhat/contracts/` holds **byte-identical twins** of the canonical sources
in [`../contracts/solidity/`](../contracts/solidity/):

| Twin | Canonical |
|---|---|
| `contracts/BTCPEscrow.sol` | `../contracts/solidity/BTCPEscrow.sol` |
| `contracts/TRIONExecutionGate.sol` | `../contracts/solidity/TRIONExecutionGate.sol` |
| `contracts/TRIONOracleV3.sol` | `../contracts/solidity/TRIONOracleV3.sol` |
| `contracts/TrionEpochRegistry.sol` | `../contracts/solidity/TrionEpochRegistry.sol` |
| `contracts/ReentrantAttacker.sol` | `../contracts/solidity/test/ReentrantAttacker.sol` |
| `contracts/libraries/CanonicalCertificate.sol` | `../contracts/solidity/libraries/CanonicalCertificate.sol` |
| `contracts/interfaces/ITRIONOracleV3.sol` | `../contracts/solidity/interfaces/ITRIONOracleV3.sol` |
| `contracts/interfaces/ITrionEpochRegistry.sol` | `../contracts/solidity/interfaces/ITrionEpochRegistry.sol` |

**Why twins instead of importing the canonical tree?** Hardhat compiles every
file under `paths.sources`; re-pointing sources at `../contracts/solidity`
would drag in 25+ contracts that have never been validated under this
toolchain (sol 0.8.28 / cancun / viaIR), and this suite is
external-toolchain (not runnable in the CI sandbox). Duplicated-but-pinned is
the provably safe option.

**Rule:** never hand-edit a twin. When a canonical contract changes, copy it
over (`cp ../contracts/solidity/<file>.sol contracts/<file>.sol`). Drift is
detected automatically by
[`tests/contracts/test_solidity_source_sync.py`](../tests/contracts/test_solidity_source_sync.py)
(byte-diff pin in the pytest battery) — the file set above is pinned too, so a
new file in either tree fails the suite until the map is updated.
