// Compile TRION Solidity BTCP contracts with solcjs, output ABI+bytecode.
//
// Targets now include TRIONOracleV3 (the consensus oracle the escrow binds —
// S3/C2 fix): deploy scripts need its ABI+bytecode to deploy AND bind it in
// one flow.
//
// Imports are resolved transitively into the flat standard-JSON source map
// (keyed by import-relative path so solc can resolve them — the solcjs
// standard-JSON path has no file-system import callback). The stale-artifact
// incident this fixes: Wave-2 added `import "./libraries/CanonicalCertificate.sol"`
// and `import "./interfaces/ITrionEpochRegistry.sol"` to BTCPEscrow.sol /
// TRIONOracleV3.sol while this map still listed only ITRIONOracleV3, so a
// re-run compiled 0/5 and the committed artifacts silently stayed one
// revision behind the audited source. The walker below makes that class of
// drift impossible: any new relative import is picked up automatically, and
// tests/contracts/test_solidity_source_sync.py pins the committed artifacts
// against a fresh ABI compile of the source.
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
// Transitive relative-import walker: adds `rel` and everything it imports.
function addWithImports(rel) {
  if (sources[rel]) return;
  const content = fs.readFileSync(path.join(SOL_DIR, rel), 'utf-8');
  sources[rel] = { content };
  for (const m of content.matchAll(/import\s+["']([^"']+)["']/g)) {
    const imp = m[1];
    if (!imp.startsWith('./')) {
      throw new Error(`compile.mjs: non-relative import "${imp}" in ${rel} is not supported by the flat source map — remap it here`);
    }
    addWithImports(path.posix.normalize(path.posix.join(path.posix.dirname(rel), imp)));
  }
}
for (const f of targets) addWithImports(f);
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
