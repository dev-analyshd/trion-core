/**
 * TRION TON Oracle — Testnet Deployer
 */
const { TonClient, WalletContractV4, internal } = require("@ton/ton");
const { Cell, contractAddress, beginCell } = require("@ton/core");
const { mnemonicToWalletKey, keyPairFromSecretKey } = require("@ton/crypto");
const fs   = require("fs");
const path = require("path");

const MNEMONIC = (process.env.TON_MNEMONIC || "").trim();
const PRIV_HEX = (process.env.TON_PRIVATE_KEY_HEX || "").replace(/^0x/,"");
const ENDPOINT = "https://testnet.toncenter.com/api/v2/jsonRPC";

async function main() {
  const bocPath = path.join(__dirname, "build", "oracle.boc");
  const codeCell = Cell.fromBoc(fs.readFileSync(bocPath))[0];
  console.log("Code cell hash:", codeCell.hash().toString("hex").slice(0,16));

  const dataCell = beginCell()
    .storeUint(0, 267)
    .storeUint(0, 64)
    .storeUint(1, 8)
    .storeRef(new Cell())
    .endCell();

  let keyPair;
  if (MNEMONIC && MNEMONIC.split(" ").length >= 12) {
    keyPair = await mnemonicToWalletKey(MNEMONIC.split(" "));
    console.log("Key source: mnemonic (" + MNEMONIC.split(" ").length + " words)");
  } else if (PRIV_HEX && PRIV_HEX.length === 64) {
    const privBuf = Buffer.from(PRIV_HEX, "hex");
    // For ed25519: secretKey is 64 bytes (priv+pub). We only have 32 priv bytes.
    // Derive public key using the nacl-compatible expand
    const nacl = require("tweetnacl");
    const kp = nacl.sign.keyPair.fromSeed(privBuf);
    keyPair = { publicKey: Buffer.from(kp.publicKey), secretKey: Buffer.from(kp.secretKey) };
    console.log("Key source: TON_PRIVATE_KEY_HEX");
  } else {
    throw new Error("Set TON_MNEMONIC or TON_PRIVATE_KEY_HEX");
  }

  const wallet = WalletContractV4.create({ publicKey: keyPair.publicKey, workchain: 0 });
  console.log("Wallet:", wallet.address.toString({ bounceable: true, testOnly: true }));

  const client = new TonClient({ endpoint: ENDPOINT });
  const balance = await client.getBalance(wallet.address);
  console.log("Balance:", Number(balance) / 1e9, "TON");
  if (balance < 500000000n) throw new Error("Need ≥0.5 TON");

  const stateInit = { code: codeCell, data: dataCell };
  const contractAddr = contractAddress(0, stateInit);
  const addrStr = contractAddr.toString({ bounceable: true, testOnly: true });
  console.log("Contract address:", addrStr);

  const existing = await client.isContractDeployed(contractAddr);
  if (existing) { console.log("✅ Already deployed!"); return addrStr; }

  const walletContract = client.open(wallet);
  const seqno = await walletContract.getSeqno();
  console.log("Seqno:", seqno);

  await walletContract.sendTransfer({
    secretKey: keyPair.secretKey,
    seqno,
    messages: [internal({ to: contractAddr, value: "0.15", bounce: false, init: stateInit, body: beginCell().endCell() })]
  });

  console.log("🚀 Deploy TX sent! Waiting 20s...");
  await new Promise(r => setTimeout(r, 20000));

  const deployed = await client.isContractDeployed(contractAddr);
  if (deployed) {
    console.log("✅ DEPLOYED:", addrStr);
    fs.writeFileSync(path.join(__dirname,"build","deployed_address.json"),
      JSON.stringify({ address: addrStr, network: "testnet", ts: new Date().toISOString() }, null, 2));
  } else {
    console.log("⏳ Pending confirmation. Address:", addrStr);
    fs.writeFileSync(path.join(__dirname,"build","deployed_address.json"),
      JSON.stringify({ address: addrStr, network: "testnet", status:"pending", ts: new Date().toISOString() }, null, 2));
  }
  return addrStr;
}

main().catch(e => { console.error("Deploy error:", e.message); process.exit(1); });
