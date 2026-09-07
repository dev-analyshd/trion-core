/**
 * Phase 0 — Evidence Integrity: Patched exec() that asserts receipt status.
 *
 * exec(call, label, expectRevert=false):
 *   - expectRevert=false (default): asserts receipt.execution_status === 'SUCCEEDED'.
 *     If REVERTED, throws with the revert reason.
 *   - expectRevert=true: asserts receipt.execution_status === 'REVERTED'.
 *     If SUCCEEDED, throws "expected revert but succeeded".
 *
 * This fixes F1: a submitted-but-reverted tx must throw, not return.
 */

// ─── Patched exec + awaitReceipt ──────────────────────────────
export async function makeExec(provider, account, accountAddr) {
  let nextNonce = null;

  async function awaitReceipt(txHash) {
    for (let i = 0; i < 50; i++) {
      try {
        const r = await provider.getTransactionReceipt(txHash);
        if (r && (r.execution_status === 'SUCCEEDED' || r.execution_status === 'REVERTED')) return r;
      } catch (e) {
        if (/Block not found|Transaction hash not found|code 24/i.test(e.message || '')) {
          await new Promise(r => setTimeout(r, 2500)); continue;
        }
        if (i < 3) { await new Promise(r => setTimeout(r, 2500)); continue; }
      }
      await new Promise(r => setTimeout(r, 2500));
    }
    return null;
  }

  async function exec(call, label, expectRevert = false) {
    for (let attempt = 1; attempt <= 5; attempt++) {
      try {
        if (nextNonce === null) nextNonce = await provider.getNonceForAddress(accountAddr);
        const tx = await account.execute(call, { maxFee: 0x10000000000n, skipValidate: true, nonce: nextNonce });
        nextNonce++;
        const r = await awaitReceipt(tx.transaction_hash);
        if (!r) throw new Error(`${label}: receipt timeout for ${tx.transaction_hash.slice(0, 16)}`);

        if (expectRevert) {
          // Negative path: expect REVERTED
          if (r.execution_status !== 'REVERTED') {
            throw new Error(`${label}: expected REVERT but got ${r.execution_status} (tx ${tx.transaction_hash.slice(0, 16)})`);
          }
          return { tx, receipt: r, reverted: true };
        } else {
          // Positive path: expect SUCCEEDED
          if (r.execution_status !== 'SUCCEEDED') {
            const reason = r.revert_reason ? decodeHex(r.revert_reason) : 'unknown';
            throw new Error(`${label}: tx REVERTED — ${reason} (tx ${tx.transaction_hash.slice(0, 16)})`);
          }
          return { tx, receipt: r, reverted: false };
        }
      } catch (e) {
        const msg = e.message || '';
        // If it's our own assert (contains "expected REVERT" or "tx REVERTED"), throw immediately
        if (/expected REVERT|tx REVERTED|receipt timeout/i.test(msg)) throw e;

        // Nonce desync
        if (/nonce|NonceTooOld/i.test(msg) && attempt < 5) {
          nextNonce = await provider.getNonceForAddress(accountAddr);
          await new Promise(r => setTimeout(r, 2000)); continue;
        }
        // Transient RPC errors
        if (attempt < 5 && /estimateFee|fetch failed|429|503|RESOURCE_BUSY|Block not found/i.test(msg)) {
          await new Promise(r => setTimeout(r, 2000 * attempt)); continue;
        }
        throw e;
      }
    }
    throw new Error('exec failed: ' + label);
  }

  function resetNonce() {
    nextNonce = null;
  }

  return { exec, awaitReceipt, resetNonce };
}

function decodeHex(revertReason) {
  if (!revertReason) return 'unknown';
  // Try to decode hex-encoded strings
  const hexMatches = revertReason.match(/0x[0-9a-f]{16,}/g) || [];
  for (const h of hexMatches) {
    try {
      const dec = Buffer.from(h.slice(2), 'hex').toString('utf8');
      if (/SPV:|BTCP:|PoW|linkage|bits|depth|exists|unknown|merkle|anchor|quorum|attestation|stale|dispute|renounced|rewind|future|monotonic|size|authorized|already/i.test(dec)) {
        return dec.slice(0, 80);
      }
    } catch {}
  }
  if (/Result::unwrap/i.test(revertReason)) return 'Result::unwrap failed (bare panic)';
  return revertReason.slice(0, 80);
}
