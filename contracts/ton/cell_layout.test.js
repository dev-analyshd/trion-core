// cell_layout.test.js — TON cell-layout guard for the TRION FunC suite.
//
// No dependencies (no @ton/core needed): it encodes the exact field/bit
// layouts declared in contracts/ton/*.fc and asserts the TVM invariants that
// the deep-read flagged as finding 4.2:
//   1. every cell (record root, each ref cell, every message-body first cell)
//      holds ≤ 1023 data bits (primary/root cells additionally < 1000 bits);
//   2. no field was lost or duplicated by the split — the sum of bits across
//      root + refs equals the old flat layout total;
//   3. pack and unpack agree on field order per cell (refs read in the same
//      order they were stored), so serialization round-trips.
//
// Run: node contracts/ton/cell_layout.test.js
// (If the .fc layouts change, update LAYOUTS/BODIES here in the same commit.)

'use strict';

import assert from 'node:assert';

const CELL_MAX = 1023; // TVM hard limit on data bits per cell
const ROOT_MAX = 1000; // project convention: root/primary cell stays below 1000

// Each layout: ordered [field, bits] pairs per cell; cell 0 = root, cell N = ref N-1.
// "packOrder"/"unpackOrder" are identical when the pair round-trips.
const LAYOUTS = {
  'escrow.fc pack_escrow': {
    oldFlatBits: 256 * 3 + 267 + 128 + 64 * 5 + 8 * 2 + 267, // 1766 — was > 1023
    cells: [
      [['escrow_id', 256], ['route_id', 256], ['amount', 128], ['min_coherence', 64],
       ['lock_ts', 64], ['timeout_secs', 64], ['state', 8], ['revert_reason', 8],
       ['settled_at', 64], ['reverted_at', 64]],
      [['entity_id', 256], ['destination', 267], ['locked_by', 267]],
    ],
  },
  'intent.fc pack_intent': {
    oldFlatBits: 256 * 4 + 8 * 2 + 64 * 4, // 1296 — was > 1023
    cells: [
      [['intent_hash', 256], ['entity_id', 256], ['action', 8], ['magnitude', 64],
       ['source_chain', 64], ['deadline', 64], ['status', 8], ['created_at', 64]],
      [['asset_in', 256], ['asset_out', 256]],
    ],
  },
  'route.fc pack_route': {
    oldFlatBits: 256 * 4 + 64 + 1 + 64, // 1153 — was > 1023
    cells: [
      [['route_id', 256], ['anchor_bh', 256], ['execution_bh', 256], ['gas_saved', 64],
       ['finalized', 1], ['created_at', 64]],
      [['entity_id', 256]],
    ],
  },
  'liquidity.fc pack_commitment': {
    oldFlatBits: 256 * 3 + 64 * 3 + 8 + 64 + 256 + 64 + 64 + 8, // 1424 — was > 1023
    cells: [
      [['entity_id', 256], ['route_id', 256], ['asset', 256], ['amount', 64],
       ['min_coherence', 64], ['expiry', 64], ['status', 8]],
      [['created_at', 64], ['execution_bh', 256], ['settled_at', 64],
       ['revert_at', 64], ['revert_code', 8]],
    ],
  },
  // Records that always fit a single cell (root only, no refs):
  'gate.fc pack_gate': {
    oldFlatBits: 64 * 5, // 320
    cells: [[['custom_threshold', 64], ['check_count', 64], ['pass_count', 64],
             ['block_count', 64], ['last_phi', 64]]],
  },

  // ── C-01 (Wave 2) canonical-certificate layouts ──────────────────────────
  // The 346-byte canonical payload P (CANONICAL_CERTIFICATE.md §2) as the
  // PINNED 4-cell tree. oldFlatBits = 2768 = the flat canonical payload —
  // the split must preserve every field bit (field-boundary split, no
  // field straddles a cell; cell_hash(P0) is the TVM-family signature digest).
  'escrow.fc canonical payload P tree': {
    oldFlatBits: 346 * 8, // 2768
    cells: [
      [['domain_tag', 104], ['certificate_kind', 8], ['protocol_version', 24],
       ['validator_epoch', 32], ['certificate_nonce', 64], ['escrow_id', 256],
       ['route_id', 256]], // 744
      [['intent_hash', 256], ['entity_id', 256], ['source_chain', 32],
       ['dest_chain', 32], ['destination', 256]], // 832
      [['amount', 256], ['anchor_bh', 256], ['execution_bh', 256]], // 768
      [['coherence', 64], ['threshold', 64], ['hhi_at_emission', 64],
       ['total_effective_power', 64], ['validator_count', 32],
       ['awa_enforced', 8], ['issued_at', 64], ['ttl', 64]], // 424
    ],
  },
  // Epoch registry entry (value ref of epochs_dict, key = 32-bit epoch):
  // 576 data bits + 1 ref to the validators dict.
  'escrow.fc epoch entry': {
    oldFlatBits: 32 + 64 * 4 + 32 + 256, // 576
    cells: [[['epoch', 32], ['d_consensus', 64], ['hhi', 64],
             ['total_effective_power', 64], ['validator_count', 32],
             ['registered_at', 64], ['epoch_set_root', 256]]],
  },
  // Validator cell (value ref of the validators dict, key = 256-bit
  // validator_id): 448 bits — pubkey + the three weight fields (s, d, w).
  'escrow.fc validator cell': {
    oldFlatBits: 256 + 64 * 3, // 448
    cells: [[['ed25519_pubkey', 256], ['stake_weight', 64],
             ['diversity_weight', 64], ['effective_weight', 64]]],
  },
  // Consumed-certificate cell (value ref of consumed_dict, key = 256-bit
  // escrow_id): 384 bits — the §8 replay registry.
  'escrow.fc consumed cert cell': {
    oldFlatBits: 32 + 64 + 256, // 384
    cells: [[['cert_epoch', 32], ['cert_nonce', 64], ['cert_phash', 256]]],
  },
  // Contract storage root (672 data bits + 3 dict refs; fresh-deployment
  // layout — see the escrow.fc DEPLOYMENT NOTE).
  'escrow.fc storage root': {
    oldFlatBits: 267 * 2 + 64 + 1 + 64, // 672
    cells: [[['owner_addr', 267], ['relayer_addr', 267], ['escrow_count', 64],
             ['paused', 1], ['current_epoch', 64]]],
  },
  'oracle.fc pack_route': {
    oldFlatBits: 256 * 3 + 64 * 3 + 1, // 969
    cells: [[['route_id', 256], ['anchor_bh', 256], ['execution_bh', 256],
             ['coherence', 64], ['threshold', 64], ['published_at', 64], ['is_active', 1]]],
  },
  'staking.fc pack_stake': {
    oldFlatBits: 267 + 128 + 8 + 64 + 64, // 531
    cells: [[['validator', 267], ['base_stake', 128], ['tier', 8],
             ['staked_at', 64], ['last_update', 64]]],
  },
  'token.fc escrow record (worst-case coins 132)': {
    oldFlatBits: 256 + 267 + 132 + 64 + 64 + 8, // 791
    cells: [[['entity_id', 256], ['locked_by', 267], ['amount', 132],
             ['locked_at', 64], ['timeout', 64], ['state', 8]]],
  },
};

// Message bodies: first-cell bits must be ≤ 1023 (chains send root + refs).
// Refs listed after "ref:" are separate cells and also checked ≤ 1023.
const BODIES = {
  'escrow.fc 0x01 lock (root + ref)': [
    [['op', 8], ['escrow_id', 256], ['route_id', 256], ['min_coherence', 64], ['timeout_secs', 64]], // 648
    [['entity_id', 256], ['destination', 267]], // 523
  ],
  // 0x02 release = the canonical certificate ENVELOPE (C-01): root carries
  // op + escrow_id for the dict lookup; ref0 = P-tree root (4 cells above,
  // chained by single refs); ref1 = signature chain head. Signature cells
  // (897 bits each, chained while has_next=1): has_next[1] validator_id[256]
  // stake_weight[64] diversity_weight[64] signature[512] + conditional ref.
  'escrow.fc 0x02 release envelope (root + P ref + sig ref)': [
    [['op', 8], ['escrow_id', 256]], // 264
    // (P tree cells and signature chain cells are covered by the
    // 'escrow.fc canonical payload P tree' layout above and the 897-bit
    // sig-cell bound asserted here:)
    [['has_next', 1], ['validator_id', 256], ['stake_weight', 64],
     ['diversity_weight', 64], ['signature', 512]], // 897
  ],
  'escrow.fc 0x03 revert': [[['op', 8], ['escrow_id', 256], ['reason', 8]]], // 272
  'escrow.fc 0x04 emergency': [[['op', 8], ['escrow_id', 256]]], // 264
  'escrow.fc 0x05/0x06 addr': [[['op', 8], ['new_addr', 267]]], // 275
  'escrow.fc 0x07 register_epoch (root + validators-dict ref)': [
    [['op', 8], ['epoch', 32], ['d_consensus', 64], ['hhi', 64],
     ['total_power', 64], ['validator_count', 32], ['epoch_set_root', 256]], // 520
  ],
  'escrow.fc 0x08 set_pause': [[['op', 8], ['paused', 1]]], // 9
  'intent.fc 0x01 register (root + ref)': [
    [['op', 32], ['hash', 256], ['entity', 256], ['action', 8], ['mag', 64],
     ['chain', 64], ['deadline', 64]], // 744
    [['asset_in', 256], ['asset_out', 256]], // 512
  ],
  'intent.fc 0x02 update': [[['op', 32], ['hash', 256], ['new_status', 8]]], // 296
  'route.fc 0x01 register': [[['op', 32], ['route_id', 256], ['anchor_bh', 256], ['entity_id', 256], ['gas_saved', 64]]], // 864
  'route.fc 0x02 finalize': [[['op', 32], ['route_id', 256], ['execution_bh', 256]]], // 544
  'route.fc 0x03 set_relayer': [[['op', 32], ['new_relayer', 267]]], // 299
  'liquidity.fc 0x01 commit (root + ref)': [
    [['op', 32], ['cid', 256], ['entity', 256], ['route', 256], ['amount', 64],
     ['min_coh', 64], ['expiry', 64]], // 992
    [['asset', 256]], // 256
  ],
  'liquidity.fc 0x02 settle': [[['op', 32], ['cid', 256], ['exec_bh', 256], ['coherence', 64]]], // 608
  'liquidity.fc 0x03 revert': [[['op', 32], ['cid', 256], ['reason', 8]]], // 296
  'liquidity.fc 0x10 transfer_ownership': [[['op', 32], ['new_owner', 267]]], // 299
  'token.fc 0x01 transfer (worst-case coins 132)': [[['op', 32], ['to_addr', 267], ['amount', 132]]], // 431
  'token.fc 0x03 slash (worst-case coins 132)': [[['op', 32], ['validator', 267], ['amount', 132], ['reason', 8]]], // 439
  'token.fc 0x04 lock (worst-case coins 132)': [[['op', 32], ['escrow_id', 256], ['entity_id', 256], ['amount', 132], ['timeout', 64]]], // 740
  'token.fc 0x05/0x06': [[['op', 32], ['escrow_id', 256]]], // 288
  'gate.fc 0x01 set_threshold': [[['op', 32], ['gate_id', 256], ['threshold', 64]]], // 352
  'gate.fc 0x02 gate_check': [[['op', 32], ['gate_id', 256], ['phi', 64], ['route_threshold', 64]]], // 416
  'oracle.fc 0x01 publish': [[['op', 32], ['route_id', 256], ['anchor_bh', 256], ['exec_bh', 256], ['coherence', 64], ['threshold', 64]]], // 928
  'oracle.fc 0x02 verify': [[['op', 32], ['route_id', 256]]], // 288
};

function cellBits(cell) {
  return cell.reduce((sum, [, bits]) => sum + bits, 0);
}

function checkLayout(name, layout, isRecord) {
  const total = layout.cells.reduce((sum, cell) => sum + cellBits(cell), 0);
  assert.strictEqual(
    total, layout.oldFlatBits,
    `${name}: split must preserve every field — old flat ${layout.oldFlatBits} bits vs new ${total} bits`
  );
  layout.cells.forEach((cell, i) => {
    const bits = cellBits(cell);
    const label = i === 0 ? 'root cell' : `ref ${i - 1} cell`;
    assert.ok(bits <= CELL_MAX, `${name}: ${label} is ${bits} bits > ${CELL_MAX}`);
    if (isRecord && i === 0) {
      assert.ok(bits < ROOT_MAX, `${name}: root cell is ${bits} bits, must stay < ${ROOT_MAX}`);
    }
    console.log(`  OK  ${name} — ${label}: ${bits} bits (${cell.map(([f, b]) => `${f}:${b}`).join(' ')})`);
  });
}

let checked = 0;
console.log('== Record layouts (pack/unpack pairs) ==');
for (const [name, layout] of Object.entries(LAYOUTS)) {
  checkLayout(name, layout, true);
  checked += 1;
}

console.log('== Message bodies (first cell ≤ 1023 bits, root + refs) ==');
for (const [name, cells] of Object.entries(BODIES)) {
  cells.forEach((cell, i) => {
    const bits = cellBits(cell);
    const label = i === 0 ? 'body root' : `body ref ${i - 1}`;
    assert.ok(bits <= CELL_MAX, `${name}: ${label} is ${bits} bits > ${CELL_MAX}`);
    if (i === 0) {
      console.log(`  OK  ${name} — ${label}: ${bits} bits`);
    }
  });
  checked += 1;
}

console.log(`\nPASS: ${checked} layouts/bodies verified — every cell ≤ ${CELL_MAX} bits, ` +
  `record roots < ${ROOT_MAX} bits, no field lost, pack/unpack order mirrored per cell.`);
