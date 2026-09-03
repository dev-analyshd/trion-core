// Compile TRION Solidity BTCP contracts with solcjs, output ABI+bytecode
import fs from 'fs';
import path from 'path';
import solc from 'solc';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOL_DIR = path.join(__dirname, '..', 'contracts', 'solidity');
const OUT_DIR = path.join(__dirname, 'compiled');
fs.mkdirSync(OUT_DIR, { recursive: true });

const targets = ['BTCPEscrow.sol', 'BTCPIntent.sol', 'BTCPRoute.sol', 'LiquidityOcean.sol'];
const sources = {};
for (const f of targets) {
  sources[f] = { content: fs.readFileSync(path.join(SOL_DIR, f), 'utf-8') };
}
const input = {
  language: 'Solidity',
  sources,
  settings: {
    optimizer: { enabled: true, runs: 200 },
    viaIR: true,
    evmVersion: 'cancun',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } },
  },
};
console.log('Compiling', targets.length, 'Solidity contracts with solc', solc.version());
const output = JSON.parse(solc.compile(JSON.stringify(input)));
if (output.errors) for (const e of output.errors) { if (e.severity === 'error') console.error('ERROR:', e.formattedMessage); }
let ok = 0;
for (const f of targets) {
  const name = f.replace('.sol', '');
  const contract = output.contracts?.[f]?.[name];
  if (!contract) { console.error(`✗ ${name}: no output`); continue; }
  fs.writeFileSync(path.join(OUT_DIR, `${name}.json`), JSON.stringify({
    contractName: name, abi: contract.abi, bytecode: '0x' + contract.evm.bytecode.object,
  }, null, 2));
  console.log(`✓ ${name}: abi=${contract.abi.length} entries, bytecode=${contract.evm.bytecode.object.length} hex chars`);
  ok++;
}
console.log(`\n${ok}/${targets.length} compiled -> ${OUT_DIR}`);
