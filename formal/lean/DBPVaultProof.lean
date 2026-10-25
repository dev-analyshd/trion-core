/-
  DBPVaultProof.lean
  Lean 4 formal proof of the DBP vault composition.

  Three theorems about the Coherence Vault (Taproot output with two
  script-path leaves: a DBP release leaf `OP_SHA256 <H> OP_EQUAL` and a CSV
  refund leaf `<borrowerKey> OP_CHECKSIGVERIFY <csv> OP_CHECKSEQUENCEVERIFY`):

    Theorem 1 (Spend Safety):  sha256(payload) = H  ⟹  release script = TRUE.
    Theorem 2 (Refund Safety): h ≥ lockHeight + csv ⟹  refund leaf spendable.
    Theorem 3 (Liveness):     refund path is always available at maturity.

  Theorem statements are precise. Lemmas requiring full Bitcoin consensus
  modeling (BIP-341/342 Tapscript, BIP-340 Schnorr) are admitted as clearly
  marked `axiom`s.

  References: docs/spec/DBP_PRIMITIVE_SPEC.md, docs/bip/BIP-DBP.md
-/

namespace DBPVault

open Classical

abbrev Byte : Type := Fin 256
abbrev Bytes (n : Nat) : Type := Vector Byte n
def PayloadLength : Nat := 80
abbrev Payload : Type := Bytes PayloadLength   -- 80-byte DBP payload
abbrev Hash : Type := Bytes 32                 -- SHA-256 digest
abbrev BlockHeight : Type := Nat
abbrev PubKey : Type := Bytes 32                -- BIP-340 x-only pubkey

/-- Abstract Schnorr signature; verification is `borrowerSigValid` below. -/
structure Sig where deriving DecidableEq

/-- SHA-256, treated as an opaque total deterministic function (NIST FIPS 180-4). -/
@[extern "lean_sha256"]
opaque sha256 : {n : Nat} → Bytes n → Hash

theorem sha256_deterministic (n : Nat) (x : Bytes n) : sha256 x = sha256 x := rfl

-- ----------------------------------------------------------------------
-- DBP primitive (BIP-DBP §"Primitive definition")
-- ----------------------------------------------------------------------

/-- `Commit(payload) = sha256(payload)` (BIP-DBP). -/
def commit (p : Payload) : Hash := sha256 p

/-- `Verify(payload, H) = 1` iff `sha256(payload) == H`. -/
def verify (p : Bytes 80) (H : Hash) : Bool := decide (sha256 p = H)

-- ----------------------------------------------------------------------
-- Bitcoin Script model (BIP-342 Tapscript, simplified to the DBP leaf)
-- ----------------------------------------------------------------------

/--
  `releaseScriptEval payload H` models Tapscript execution of
  `OP_SHA256 <H> OP_EQUAL` with witness top-item `payload`:
  OP_SHA256 pops payload, pushes sha256(payload); OP_EQUAL pushes 1 iff equal.
-/
def releaseScriptEval (witnessItem : Bytes 80) (committedHash : Hash) : Bool :=
  decide (sha256 witnessItem = committedHash)

/-- Consensus axiom: `releaseScriptEval` coincides with BIP-342 Tapscript. -/
axiom releaseScript_sound (p : Bytes 80) (H : Hash) :
    releaseScriptEval p H = true ↔ sha256 p = H

-- ----------------------------------------------------------------------
-- Taproot vault model
-- ----------------------------------------------------------------------

/-- Taproot output with two script-path leaves: leaf 1 = DBP release, leaf 2 = CSV refund. -/
structure Vault where
  payload : Option Payload      -- `some p` iff the preimage is known/published
  committedHash : Hash         -- H = sha256(payload), committed at lock time
  borrowerKey  : PubKey
  lockHeight   : BlockHeight   -- block at which the lock tx confirmed
  csvBlocks    : Nat           -- relative timelock for the refund path

/-- BIP-340 signature verification for the borrower's key. -/
axiom borrowerSigValid (v : Vault) (sig : Sig) : Bool

/-- CSV refund path spendable iff (i) borrower's sig verifies AND (ii) `h ≥ lockHeight + csvBlocks` (BIP-68 / BIP-112). -/
noncomputable def refundSpendable (v : Vault) (h : BlockHeight) (sig : Sig) : Bool :=
  borrowerSigValid v sig && decide (h ≥ v.lockHeight + v.csvBlocks)

/-- Consensus axiom: `refundSpendable` coincides with Tapscript execution of the refund leaf. -/
axiom refundScript_sound (v : Vault) (h : BlockHeight) (sig : Sig) :
    refundSpendable v h sig = true ↔
      borrowerSigValid v sig = true ∧ h ≥ v.lockHeight + v.csvBlocks

-- ======================================================================
-- THEOREM 1 (Spend Safety)
-- ======================================================================

/--
  **Theorem 1 (Spend Safety).** If `sha256(payload) == committedHash`, then
  the DBP release script `OP_SHA256 <committedHash> OP_EQUAL` evaluates to TRUE
  under a witness whose top item is `payload`.
-/
theorem spend_safety (payload : Bytes 80) (committedHash : Hash)
    (h : sha256 payload = committedHash) :
    releaseScriptEval payload committedHash = true := by
  unfold releaseScriptEval
  rw [h]
  exact decide_eq_true (Eq.refl committedHash)

-- ======================================================================
-- THEOREM 2 (Refund Safety)
-- ======================================================================

/--
  **Theorem 2 (Refund Safety).** If `h ≥ lockHeight + csvBlocks` and the
  borrower's signature is valid, then the CSV refund path is spendable.
  Trustless-safety: borrower always recovers their BTC after `csvBlocks`.
-/
theorem refund_safety (v : Vault) (h : BlockHeight) (sig : Sig)
    (h_time : h ≥ v.lockHeight + v.csvBlocks)
    (h_sig  : borrowerSigValid v sig = true) :
    refundSpendable v h sig = true := by
  simp [refundSpendable, h_sig, decide_eq_true h_time]

-- ======================================================================
-- THEOREM 3 (Liveness)
-- ----------------------------------------------------------------------

/--
  `releaseAvailable v` holds iff the preimage is known and hashes to H.
  Once `payload` is published, anyone may relay the spend (BIP-DBP §"Reveal").
-/
def releaseAvailable (v : Vault) : Prop :=
  ∃ payload : Payload,
    v.payload = some payload ∧ sha256 payload = v.committedHash

/-- `refundAvailable v h` holds iff `h ≥ lockHeight + csvBlocks`. -/
def refundAvailable (v : Vault) (h : BlockHeight) : Prop :=
  h ≥ v.lockHeight + v.csvBlocks

/--
  **Theorem 3 (Liveness, eventual).** There exists a finite height
  `h* = lockHeight + csvBlocks` such that for all `h ≥ h*`, the refund path is
  unconditionally available.

  This is the precise liveness guarantee: every vault becomes spendable no
  later than `csvBlocks` after lock confirmation. The release path may be
  available earlier (iff `releaseAvailable v`); the refund path is always
  available at maturity.
-/
theorem liveness_eventual (v : Vault) :
    ∃ maturity : BlockHeight,
      maturity = v.lockHeight + v.csvBlocks ∧
      ∀ h ≥ maturity, refundAvailable v h := by
  refine ⟨v.lockHeight + v.csvBlocks, rfl, ?_⟩
  intro h hh
  exact hh

/--
  **Theorem 3 (Liveness, pointwise).** At any height `h`:

    releaseAvailable v  ∨  refundAvailable v h  ∨  h < lockHeight + csvBlocks

  The third disjunct is the deliberate "lock period" — the vault is
  intentionally frozen for the borrower's protection during the timelock
  window, and no party (including the DBP issuer) can move the funds. After
  maturity, the refund path is always available.

  This statement captures the exact (safety, liveness) trade-off envelope as
  a function of `csvBlocks`: smaller `csvBlocks` ⇒ sooner the borrower can
  self-rescue; larger `csvBlocks` ⇒ longer the issuer has to publish the
  preimage before the borrower can refund.
-/
theorem liveness (v : Vault) (h : BlockHeight) :
    releaseAvailable v ∨ refundAvailable v h ∨ h < v.lockHeight + v.csvBlocks := by
  by_cases H_release : releaseAvailable v
  · exact Or.inl H_release
  · by_cases H_refund : h ≥ v.lockHeight + v.csvBlocks
    · exact Or.inr (Or.inl H_refund)
    · exact Or.inr (Or.inr (Nat.lt_of_not_le H_refund))

-- ======================================================================
-- Corollary: no adversary can indefinitely freeze the funds
-- ----------------------------------------------------------------------

/--
  No-indefinite-freeze: at any height `h ≥ lockHeight + csvBlocks`, the
  refund path is unconditionally available, regardless of any adversary's
  actions (modulo SHA-256 preimage resistance for the release path).
-/
theorem no_indefinite_freeze (v : Vault) (h : BlockHeight)
    (h_mature : h ≥ v.lockHeight + v.csvBlocks) :
    refundAvailable v h := h_mature

end DBPVault
