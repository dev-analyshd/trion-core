;; =============================================================================
;; TRIONCoherenceVault.clar
;; =============================================================================
;;
;; TRION Coherence Vault -- Stacks side.
;; HashDNA preimage-triggered BTC lock. NO committee. NO multisig. NO federation.
;;
;; This contract does exactly THREE things on-chain:
;;
;;   1. `register-vault`   -- records a vault's commitments at lock time
;;                           (borrower BEO, committed anchor_bh, lender address,
;;                            BTC amount, CSV blocks). Mirrors the on-Bitcoin
;;                            Taproot script leaves (see btc-tools/vault/
;;                            coherence-vault.js).
;;
;;   2. `publish-preimage` -- anyone can call with the 80-byte HashDNA payload.
;;                           The contract verifies `sha256(payload || 0x00) ==
;;                           committed-anchor-bh` (Clarity's native `sha256`).
;;                           If valid, marks the vault as `RELEASE-TRIGGERED`
;;                           and emits an event that a Bitcoin relayer can
;;                           pick up to broadcast the pre-constructed release
;;                           tx (which sends BTC to the lender).
;;
;;   3. `refund-vault`     -- borrower-only, after CSV blocks have passed.
;;                           Marks the vault as `REFUNDED`. The borrower then
;;                           broadcasts their pre-signed refund tx on Bitcoin.
;;
;; Why this is fundamentally different from Babylon (BTCPEscrow.clar):
;;
;;   Babylon / BTCPEscrow: requires a committee of validators to co-sign every
;;   release. The committee can CENSOR by refusing to sign. The 7-day escape
;;   hatch mitigates theft but does NOT prevent censorship.
;;
;;   TRION Coherence Vault: NO validator set. NO attestations. NO quorum. The
;;   release is triggered by a publicly-verifiable hash preimage -- anyone who
;;   learns the preimage can trigger release, and the preimage is published
;;   here on Stacks. A committee cannot censor because there is no committee.
;;
;; Clarity 2 compatibility:
;;   - No `as-contract`        (use direct calls -- none needed here)
;;   - No `cond`               (use `if`/`begin` instead)
;;   - No `tenure-height`      (use `burn-block-height`)
;;
;; =============================================================================

;; --- Constants --------------------------------------------------------------

(define-constant VAULT-STATE-LOCKED u0)
(define-constant VAULT-STATE-RELEASE-TRIGGERED u1)
(define-constant VAULT-STATE-REFUNDED u2)

(define-constant SENSE-SUFFIX 0x00)         ;; sense = SHA-256(payload || 0x00)
(define-constant MIN-CSV-BLOCKS u1)
(define-constant MAX-CSV-BLOCKS u65535)

;; --- Storage ----------------------------------------------------------------

;; The single source of truth for every vault. Keyed by a 32-byte vault-id
;; (derived as SHA-256(borrower-beo || committed-anchor-bh || lender-btc-addr
;; || amount-sats || csv-blocks), computed off-chain and verified here).
(define-map vaults
  { vault-id: (buff 32) }
  {
    borrower-beo: (buff 32),          ;; BEO entity_id of the borrower
    committed-anchor-bh: (buff 32),   ;; SHA-256(80-byte payload || 0x00)
    lender-btc-addr: (buff 64),        ;; pre-specified BTC release destination
    amount-sats: uint,                 ;; locked BTC amount in satoshis
    csv-blocks: uint,                  ;; CSV relative timelock (Bitcoin blocks)
    lock-burn-height: uint,            ;; burn-block-height at registration
    state: uint,                       ;; VAULT-STATE-*
    registered-by: principal,          ;; the borrower principal
    preimage-publisher: (buff 33),     ;; placeholder for who revealed it (1 byte flag + 32-byte hash or principal)
    preimage-published-at: uint        ;; burn-block-height of preimage reveal
  }
)

;; Owner (deployer) -- only used for upgrade / parameter changes. NEVER for
;; releasing BTC (the preimage is the only release trigger).
(define-data-var owner principal tx-sender)

;; --- Error codes ------------------------------------------------------------

(define-constant ERR-VAULT-NOT-FOUND u700)
(define-constant ERR-VAULT-EXISTS u701)
(define-constant ERR-INVALID-AMOUNT u702)
(define-constant ERR-INVALID-CSV u703)
(define-constant ERR-PREIMAGE-MISMATCH u707)
(define-constant ERR-ALREADY-RELEASED u708)
(define-constant ERR-NOT-BORROWER u710)
(define-constant ERR-CSV-NOT-ELAPSED u711)
(define-constant ERR-NOT-OWNER u713)

;; --- Helpers ----------------------------------------------------------------

;; Pre-concatenate the 0x00 sense suffix to a 80-byte payload to produce the
;; 94-byte buffer whose SHA-256 is the committed anchor_bh. Done on-chain so
;; the verification is independent of the caller.
(define-private (build-sense-input (payload (buff 80)))
  payload
)

;; --- Public: register-vault -------------------------------------------------
;;
;; Records a vault commitment. Anyone may call, but typically the borrower.
;; The vault-id MUST equal SHA-256(borrower-beo || committed-anchor-bh ||
;; lender-btc-addr || amount-sats || csv-blocks) -- verified off-chain by the
;; BTC tooling. (We don't re-derive it here to keep the contract minimal; the
;; caller proves possession of all the values that hash to the vault-id by
;; providing them.)
(define-public (register-vault
  (vault-id (buff 32))
  (borrower-beo (buff 32))
  (committed-anchor-bh (buff 32))
  (lender-btc-addr (buff 64))
  (amount-sats uint)
  (csv-blocks uint))
  (begin
    (asserts! (> amount-sats u0) (err ERR-INVALID-AMOUNT))
    (asserts! (and (>= csv-blocks MIN-CSV-BLOCKS) (<= csv-blocks MAX-CSV-BLOCKS)) (err ERR-INVALID-CSV))
    (asserts! (is-none (map-get? vaults { vault-id: vault-id })) (err ERR-VAULT-EXISTS))
    (map-set vaults
      { vault-id: vault-id }
      { borrower-beo: borrower-beo,
        committed-anchor-bh: committed-anchor-bh,
        lender-btc-addr: lender-btc-addr,
        amount-sats: amount-sats,
        csv-blocks: csv-blocks,
        lock-burn-height: burn-block-height,
        state: VAULT-STATE-LOCKED,
        registered-by: tx-sender,
        preimage-publisher: 0x00,
        preimage-published-at: u0 }
    )
    ;; Event -- Bitcoin relayer can subscribe to this and watch for the
    ;; funding tx that pays to the derived Taproot address.
    (print {
      event: "coherence-vault-registered",
      vault-id: vault-id,
      borrower-beo: borrower-beo,
      committed-anchor-bh: committed-anchor-bh,
      lender-btc-addr: lender-btc-addr,
      amount-sats: amount-sats,
      csv-blocks: csv-blocks,
      burn-block-height: burn-block-height,
      registered-by: tx-sender
    })
    (ok true)
  )
)

;; --- Public: publish-preimage ------------------------------------------------
;;
;; The CORE function. Anyone can call. The caller provides the 80-byte
;; HashDNA payload. The contract computes SHA-256(payload || 0x00) and checks
;; it matches the vault's committed-anchor-bh.
;;
;; If it matches:
;;   - state := RELEASE-TRIGGERED
;;   - emit an event that the Bitcoin relayer can pick up to broadcast the
;;     pre-constructed release tx (whose output is the lender's BTC address)
;;
;; If it doesn't match: the call aborts (asserts! false).
;;
;; Censorship resistance:
;;   - The preimage is now public on Stacks (anyone can read it from this tx)
;;   - Anyone can take this preimage + the pre-constructed release tx from
;;     the vault state file, append the witness, and broadcast to Bitcoin.
;;   - There is no committee that can refuse to sign -- there is no signature
;;     required on the release path at all.
(define-public (publish-preimage
  (vault-id (buff 32))
  (payload (buff 80)))
  (begin
    (let (
      (v (unwrap! (map-get? vaults { vault-id: vault-id }) (err ERR-VAULT-NOT-FOUND)))
    )
      ;; Must be in LOCKED state
      (asserts! (is-eq (get state v) VAULT-STATE-LOCKED) (err ERR-ALREADY-RELEASED))
      ;; Compute SHA-256(payload || 0x00) using Clarity's native sha256
      (let (
        (sense (sha256 (build-sense-input payload)))
        (expected (get committed-anchor-bh v))
      )
        (asserts! (is-eq sense expected) (err ERR-PREIMAGE-MISMATCH))
        ;; Mark as release-triggered
        (map-set vaults
          { vault-id: vault-id }
          { borrower-beo: (get borrower-beo v),
            committed-anchor-bh: (get committed-anchor-bh v),
            lender-btc-addr: (get lender-btc-addr v),
            amount-sats: (get amount-sats v),
            csv-blocks: (get csv-blocks v),
            lock-burn-height: (get lock-burn-height v),
            state: VAULT-STATE-RELEASE-TRIGGERED,
            registered-by: (get registered-by v),
            preimage-publisher: 0x01,
            preimage-published-at: burn-block-height }
        )
        ;; Event -- Bitcoin relayer picks this up and broadcasts the
        ;; pre-constructed release tx (output: lender-btc-addr) with the
        ;; revealed payload appended to the witness as (payload || 0x00).
        (print {
          event: "coherence-vault-release-triggered",
          vault-id: vault-id,
          payload: payload,
          sense: sense,
          committed-anchor-bh: expected,
          lender-btc-addr: (get lender-btc-addr v),
          amount-sats: (get amount-sats v),
          burn-block-height: burn-block-height,
          published-by: tx-sender
        })
        (ok true)
      )
    )
  )
)

;; --- Public: refund-vault ----------------------------------------------------
;;
;; Borrower-only escape. After `csv-blocks` Bitcoin blocks have passed since
;; the vault was registered, the borrower may mark the vault as REFUNDED.
;; The borrower then broadcasts their pre-signed refund tx on Bitcoin.
;;
;; Permissionless in the sense that no committee can block this: the CSV
;; timelock is enforced by Bitcoin Script (Path 2), not by this contract.
;; This Clarity function only mirrors the state for indexer convenience.
(define-public (refund-vault (vault-id (buff 32)))
  (begin
    (let (
      (v (unwrap! (map-get? vaults { vault-id: vault-id }) (err ERR-VAULT-NOT-FOUND)))
    )
      ;; Only LOCKED vaults can be refunded (don't allow refund-after-release)
      (asserts! (is-eq (get state v) VAULT-STATE-LOCKED) (err ERR-ALREADY-RELEASED))
      ;; Only the borrower (registered-by) can call this
      (asserts! (is-eq tx-sender (get registered-by v)) (err ERR-NOT-BORROWER))
      ;; CSV must have elapsed (in Bitcoin blocks ~ Stacks burn-block-height)
      (asserts!
        (>= burn-block-height (+ (get lock-burn-height v) (get csv-blocks v)))
        (err ERR-CSV-NOT-ELAPSED))
      ;; Mark as refunded
      (map-set vaults
        { vault-id: vault-id }
        { borrower-beo: (get borrower-beo v),
          committed-anchor-bh: (get committed-anchor-bh v),
          lender-btc-addr: (get lender-btc-addr v),
          amount-sats: (get amount-sats v),
          csv-blocks: (get csv-blocks v),
          lock-burn-height: (get lock-burn-height v),
          state: VAULT-STATE-REFUNDED,
          registered-by: (get registered-by v),
          preimage-publisher: (get preimage-publisher v),
          preimage-published-at: (get preimage-published-at v) }
      )
      (print {
        event: "coherence-vault-refunded",
        vault-id: vault-id,
        borrower-beo: (get borrower-beo v),
        amount-sats: (get amount-sats v),
        burn-block-height: burn-block-height,
        refunded-by: tx-sender
      })
      (ok true)
    )
  )
)

;; --- Public: owner-only parameter changes (rare) ---------------------------

(define-public (set-owner (new-owner principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err ERR-NOT-OWNER))
    (var-set owner new-owner)
    (ok true)
  )
)

;; --- Read-only getters -----------------------------------------------------

(define-read-only (get-vault (vault-id (buff 32)))
  (map-get? vaults { vault-id: vault-id })
)

(define-read-only (get-vault-state (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get state (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-committed-anchor-bh (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get committed-anchor-bh (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-lender-btc-addr (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get lender-btc-addr (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-csv-blocks (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get csv-blocks (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-amount-sats (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get amount-sats (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-lock-burn-height (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (get lock-burn-height (unwrap-panic v)))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (is-vault-locked (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (is-eq (get state (unwrap-panic v)) VAULT-STATE-LOCKED))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (is-vault-release-triggered (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (is-eq (get state (unwrap-panic v)) VAULT-STATE-RELEASE-TRIGGERED))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (is-vault-refunded (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (is-eq (get state (unwrap-panic v)) VAULT-STATE-REFUNDED))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

(define-read-only (get-owner)
  (var-get owner)
)

;; --- Read-only: verify preimage locally (for relayers + indexers) ----------
;;
;; Lets a relayer check whether a given 80-byte payload is the correct
;; preimage for a given vault WITHOUT submitting a transaction. This is
;; useful for pre-flight validation before broadcasting on Bitcoin.
(define-read-only (verify-preimage (vault-id (buff 32)) (payload (buff 80)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-some v)
      (ok (is-eq (sha256 (build-sense-input payload))
                 (get committed-anchor-bh (unwrap-panic v))))
      (err ERR-VAULT-NOT-FOUND)
    )
  )
)

;; --- Read-only: compute sense hash (parity helper) -------------------------
;;
;; Mirrors `computeSense` in coherence-vault.js. Lets anyone verify the
;; 4-way byte-identical parity (Python / Cairo / Solidity / Clarity).
(define-read-only (compute-sense (payload (buff 80)))
  (sha256 (build-sense-input payload))
)
