// Compile TRION Solidity BTCP contracts with solcjs, output ABI+bytecode.
//
// Targets now include TRIONOracleV3 (the consensus oracle the escrow binds —
// S3/C2 fix): deploy scripts need its ABI+bytecode to deploy AND bind it in
// one flow. TRIONOracleV3 imports ./interfaces/ITRIONOracleV3.sol, which is
// remapped into the flat standard-JSON source map below (keyed by its
// import-relative path so solc can resolve it).
//
// Artifacts carry the provenance fields the deploy scripts and auditors rely
// on (compiler + optimizer + updatedAt) and are mirrored to
// contracts/solidity/compiled/ so both compiled/ trees stay identical.
import fs from 'fs';
import path from 'path';
import solc from 'solc';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOL_DIR = path.join(__dirname, '..', 'contracts', 'solidity');
const OUT_DIR = path.join(__dirname, 'compiled');
const MIRROR_DIR = path.join(SOL_DIR, 'compiled');
fs.mkdirSync(OUT_DIR, { recursive: true });
fs.mkdirSync(MIRROR_DIR, { recursive: true });

const targets = [
  'BTCPEscrow.sol',
  'BTCPIntent.sol',
  'BTCPRoute.sol',
  'LiquidityOcean.sol',
  'TRIONOracleV3.sol',
];
const sources = {};
for (const f of targets) {
  sources[f] = { content: fs.readFileSync(path.join(SOL_DIR, f), 'utf-8') };
}
// Import-relative source for TRIONOracleV3's `import "./interfaces/ITRIONOracleV3.sol"`.
sources['interfaces/ITRIONOracleV3.sol'] = {
  content: fs.readFileSync(path.join(SOL_DIR, 'interfaces', 'ITRIONOracleV3.sol'), 'utf-8'),
};
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
  const artifact = {
    contractName: name,
    abi: contract.abi,
    bytecode: '0x' + contract.evm.bytecode.object,
    compiler: { version: `${solc.version()}+viaIR`, optimizer: { enabled: true, runs: 200 } },
    updatedAt: new Date().toISOString(),
  };
  const json = JSON.stringify(artifact, null, 2);
  fs.writeFileSync(path.join(OUT_DIR, `${name}.json`), json);
  fs.writeFileSync(path.join(MIRROR_DIR, `${name}.json`), json);
  console.log(`✓ ${name}: abi=${contract.abi.length} entries, bytecode=${contract.evm.bytecode.object.length} hex chars`);
  ok++;
}
console.log(`\n${ok}/${targets.length} compiled -> ${OUT_DIR} (+ mirror ${MIRROR_DIR})`);
