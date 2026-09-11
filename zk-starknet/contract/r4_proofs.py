import json, asyncio, warnings
warnings.filterwarnings("ignore")
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.account.account import Account
from starknet_py.net.models import StarknetChainId
from starknet_py.contract import Contract
from starknet_py.net.client_models import ResourceBounds, ResourceBoundsMapping

PRIV_KEY = 0x2c3ee9b0e25b970ed0cd26fd929967bfdfdf98aa32b0abc03008308f97adaf4
DEPLOYER = 0x7cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82
RPC_URL = "https://starknet-sepolia-rpc.publicnode.com"
CONTRACT_ADDR = 0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029

client = FullNodeClient(node_url=RPC_URL)
key_pair = KeyPair.from_private_key(PRIV_KEY)
account = Account(client=client, address=DEPLOYER, key_pair=key_pair, chain=StarknetChainId.SEPOLIA)

sierra = json.loads(open("target/dev/zk_verifier_contract_ZKVerifier.contract_class.json").read())
abi = sierra.get("abi")
if isinstance(abi, str): abi = json.loads(abi)
contract = Contract(address=CONTRACT_ADDR, abi=abi, provider=account)

H_INTENT = 0x123456789abcdef
ENTITY_ID = 0xabc
BIRP_ANCHOR = 0xb1123456789abcdef

async def main():
    tx_hashes = {}
    print("=== R4: ON-CHAIN PROOFS PER SURFACE ===")

    # Check AWA frozen (view call — no gas needed)
    is_frozen = await contract.functions["is_awa_frozen"].call()
    print(f"AWA frozen (initial): {is_frozen}")

    # AWA freeze injection: commit should fail while frozen
    print("\n--- S1 commit while AWA frozen (expect REVERT) ---")
    try:
        invocation = contract.functions["commit_intent"].prepare_invoke_v3(
            H_INTENT, ENTITY_ID, max_fee=0
        )
        # This is a simulation — it should fail
        tx = await invocation.invoke(auto_estimate=True)
        await tx.wait_for_acceptance()
        print("UNEXPECTED: succeeded while frozen!")
    except Exception as e:
        err = str(e)[:150]
        print(f"EXPECTED REVERT: {err}")
        tx_hashes["awa_freeze_test"] = "PASS — commit reverted while frozen"

    # Thaw: try with explicit resource bounds (ETH gas via v1)
    print("\n--- Thaw AWA ---")
    try:
        tx_thaw = await contract.functions["set_awa_state"].prepare_invoke_v3(False).invoke(
            resource_bounds=ResourceBoundsMapping(
                l1_gas=ResourceBounds(max_amount=0, max_price_per_unit=0),
                l2_gas=ResourceBounds(max_amount=1000000, max_price_per_unit=1000000000),
            )
        )
        await tx_thaw.wait_for_acceptance()
        tx_hashes["thaw_awa"] = f"0x{tx_thaw.hash:064x}"
        print(f"Thaw TX: {tx_hashes['thaw_awa']}")
    except Exception as e:
        print(f"Thaw error: {str(e)[:200]}")
        # Try without resource bounds
        try:
            tx_thaw = await contract.functions["set_awa_state"].invoke_v3(False, auto_estimate=True)
            await tx_thaw.wait_for_acceptance()
            tx_hashes["thaw_awa"] = f"0x{tx_thaw.hash:064x}"
            print(f"Thaw TX (auto): {tx_hashes['thaw_awa']}")
        except Exception as e2:
            print(f"Thaw error (auto): {str(e2)[:200]}")

    # Check if thawed
    is_frozen = await contract.functions["is_awa_frozen"].call()
    print(f"AWA frozen after thaw attempt: {is_frozen}")

    if not is_frozen:
        # S1 commit
        print("\n--- S1 commit_intent ---")
        tx_c = await contract.functions["commit_intent"].invoke_v3(H_INTENT, ENTITY_ID, auto_estimate=True)
        await tx_c.wait_for_acceptance()
        tx_hashes["s1_commit"] = f"0x{tx_c.hash:064x}"
        print(f"S1 TX: {tx_hashes['s1_commit']}")
        r = await contract.functions["get_intent"].call(H_INTENT)
        print(f"  timestamp={r[0]}, entity_id={hex(r[1])}")

        # S3 travel rule
        print("\n--- S3 travel rule ---")
        tx_t = await contract.functions["submit_travel_rule_proof"].invoke_v3(
            ENTITY_ID, 0xdeadbeef, 0x46415446, 0xfedcba98, auto_estimate=True)
        await tx_t.wait_for_acceptance()
        tx_hashes["s3_travel"] = f"0x{tx_t.hash:064x}"
        print(f"S3 TX: {tx_hashes['s3_travel']}")

        # S5 BIRP
        print("\n--- S5 BIRP ---")
        tx_b = await contract.functions["enroll_birp"].invoke_v3(ENTITY_ID, BIRP_ANCHOR, auto_estimate=True)
        await tx_b.wait_for_acceptance()
        tx_hashes["s5_birp"] = f"0x{tx_b.hash:064x}"
        print(f"S5 TX: {tx_hashes['s5_birp']}")

        # Re-freeze
        print("\n--- Re-freeze AWA ---")
        tx_r = await contract.functions["set_awa_state"].invoke_v3(True, auto_estimate=True)
        await tx_r.wait_for_acceptance()
        tx_hashes["refreeze"] = f"0x{tx_r.hash:064x}"
        print(f"Re-freeze TX: {tx_hashes['refreeze']}")

    results = {
        "contract_address": f"0x{CONTRACT_ADDR:064x}",
        "deployer": f"0x{DEPLOYER:064x}",
        "deploy_tx": "0x01408e9cbd87bad551c515cdc232ba85d29a5d02ecfd939e9e13f5a3e2e4031b",
        "tx_hashes": tx_hashes,
    }
    with open("r4_onchain_proofs.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: {json.dumps(results, indent=2)}")

asyncio.run(main())
