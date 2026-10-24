;; TRIONCoherenceVaultV6.clar -- Coherence Vault with DeFi integration.
;;
;; Extends V5 with:
;;   - ACTIVE state (vault is borrowable)
;;   - LIQUIDATING state (preimage published, BTC moving to lender)
;;   - LIQUIDATED state (BTC spend confirmed)
;;   - RELEASED state (borrower repaid, vault released)
;;   - release-vault (lender releases after repayment)
;;   - mark-liquidating (called by BTCPLend on default)
;;   - mark-liquidated (called after BTC spend confirms)
;;   - is-vault-borrowable (read-only check for BTCPLend)
;;
;; 80-byte payload, no suffix. sha256(payload) == committed-anchor-bh.

(define-constant ERR-NOT-AUTHORIZED (err u900))
(define-constant ERR-VAULT-EXISTS (err u901))
(define-constant ERR-VAULT-NOT-FOUND (err u902))
(define-constant ERR-INVALID-STATE (err u903))
(define-constant ERR-PREIMAGE-MISMATCH (err u904))
(define-constant ERR-ALREADY-RELEASED (err u905))
(define-constant ERR-NOT-LENDER (err u906))
(define-constant ERR-NOT-BORROWABLE (err u907))
(define-constant ERR-COHERENCE-BELOW-THRESHOLD (err u908))

;; States
(define-constant STATE-LOCKED u0)
(define-constant STATE-ACTIVE u1)
(define-constant STATE-RELEASED u2)
(define-constant STATE-LIQUIDATING u3)
(define-constant STATE-LIQUIDATED u4)
(define-constant STATE-REFUNDED u5)

(define-constant MIN-COHERENCE u550000)  ;; 0.55

(define-data-var owner principal tx-sender)
(define-data-var lending-contract principal tx-sender)  ;; set to BTCPLend address

;; Vault state
(define-map vaults
  { vault-id: (buff 32) }
  { borrower-beo: (buff 32), committed-anchor-bh: (buff 32), lender-btc-addr: (buff 32),
    amount-sats: uint, csv-blocks: uint, lock-burn-height: uint,
    state: uint, registered-by: principal, lender: principal,
    preimage-publisher: principal, preimage-published-at: uint })

;; --- register-vault: borrower commits anchor_bh ---
(define-public (register-vault (vault-id (buff 32)) (borrower-beo (buff 32))
                               (anchor-bh (buff 32)) (lender-btc-addr (buff 32))
                               (amount-sats uint) (csv-blocks uint))
  (begin
    (asserts! (> amount-sats u0) (err u910))
    (asserts! (> csv-blocks u0) (err u911))
    (asserts! (is-none (map-get? vaults { vault-id: vault-id })) ERR-VAULT-EXISTS)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: borrower-beo, committed-anchor-bh: anchor-bh, lender-btc-addr: lender-btc-addr,
        amount-sats: amount-sats, csv-blocks: csv-blocks, lock-burn-height: burn-block-height,
        state: STATE-LOCKED, registered-by: tx-sender, lender: tx-sender,
        preimage-publisher: tx-sender, preimage-published-at: u0 })
    (print { event: "vault-registered", vault-id: vault-id, amount-sats: amount-sats })
    (ok true)))

;; --- activate-vault: lender activates the vault (makes it borrowable) ---
(define-public (activate-vault (vault-id (buff 32)) (lender principal))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (is-eq (get state v) STATE-LOCKED) ERR-INVALID-STATE)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: (get borrower-beo v), committed-anchor-bh: (get committed-anchor-bh v),
        lender-btc-addr: (get lender-btc-addr v), amount-sats: (get amount-sats v),
        csv-blocks: (get csv-blocks v), lock-burn-height: (get lock-burn-height v),
        state: STATE-ACTIVE, registered-by: (get registered-by v), lender: lender,
        preimage-publisher: (get preimage-publisher v), preimage-published-at: (get preimage-published-at v) })
    (print { event: "vault-activated", vault-id: vault-id, lender: lender })
    (ok true)))

;; --- release-vault: lender releases after borrower repays (happy path) ---
(define-public (release-vault (vault-id (buff 32)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (or (is-eq tx-sender (get lender v)) (is-eq tx-sender (var-get owner))) ERR-NOT-LENDER)
    (asserts! (or (is-eq (get state v) STATE-ACTIVE) (is-eq (get state v) STATE-LOCKED)) ERR-INVALID-STATE)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: (get borrower-beo v), committed-anchor-bh: (get committed-anchor-bh v),
        lender-btc-addr: (get lender-btc-addr v), amount-sats: (get amount-sats v),
        csv-blocks: (get csv-blocks v), lock-burn-height: (get lock-burn-height v),
        state: STATE-RELEASED, registered-by: (get registered-by v), lender: (get lender v),
        preimage-publisher: (get preimage-publisher v), preimage-published-at: (get preimage-published-at v) })
    (print { event: "vault-released", vault-id: vault-id })
    (ok true)))

;; --- mark-liquidating: called by lending contract when loan defaults ---
(define-public (mark-liquidating (vault-id (buff 32)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (or (is-eq tx-sender (var-get lending-contract)) (is-eq tx-sender (var-get owner))) ERR-NOT-AUTHORIZED)
    (asserts! (is-eq (get state v) STATE-ACTIVE) ERR-INVALID-STATE)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: (get borrower-beo v), committed-anchor-bh: (get committed-anchor-bh v),
        lender-btc-addr: (get lender-btc-addr v), amount-sats: (get amount-sats v),
        csv-blocks: (get csv-blocks v), lock-burn-height: (get lock-burn-height v),
        state: STATE-LIQUIDATING, registered-by: (get registered-by v), lender: (get lender v),
        preimage-publisher: (get preimage-publisher v), preimage-published-at: (get preimage-published-at v) })
    (print { event: "vault-liquidating", vault-id: vault-id })
    (ok true)))

;; --- publish-preimage: anyone publishes the 80-byte preimage ---
(define-public (publish-preimage (vault-id (buff 32)) (payload (buff 80)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (or (is-eq (get state v) STATE-LIQUIDATING) (is-eq (get state v) STATE-ACTIVE)) ERR-INVALID-STATE)
    (asserts! (is-eq (sha256 payload) (get committed-anchor-bh v)) ERR-PREIMAGE-MISMATCH)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: (get borrower-beo v), committed-anchor-bh: (get committed-anchor-bh v),
        lender-btc-addr: (get lender-btc-addr v), amount-sats: (get amount-sats v),
        csv-blocks: (get csv-blocks v), lock-burn-height: (get lock-burn-height v),
        state: STATE-LIQUIDATED, registered-by: (get registered-by v), lender: (get lender v),
        preimage-publisher: tx-sender, preimage-published-at: burn-block-height })
    (print { event: "preimage-published", vault-id: vault-id, publisher: tx-sender, payload: payload })
    (ok true)))

;; --- mark-liquidated: confirm BTC spend (owner-only, after explorer verification) ---
(define-public (mark-liquidated (vault-id (buff 32)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (asserts! (is-eq (get state v) STATE-LIQUIDATED) ERR-INVALID-STATE)
    (print { event: "vault-liquidated", vault-id: vault-id })
    (ok true)))

;; --- refund-vault: borrower claims refund after CSV (borrower-only) ---
(define-public (refund-vault (vault-id (buff 32)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) ERR-VAULT-NOT-FOUND)))
    (asserts! (is-eq tx-sender (get registered-by v)) ERR-NOT-AUTHORIZED)
    (asserts! (or (is-eq (get state v) STATE-LOCKED) (is-eq (get state v) STATE-ACTIVE) (is-eq (get state v) STATE-RELEASED)) ERR-INVALID-STATE)
    (asserts! (>= burn-block-height (+ (get lock-burn-height v) (get csv-blocks v))) ERR-INVALID-STATE)
    (map-set vaults { vault-id: vault-id }
      { borrower-beo: (get borrower-beo v), committed-anchor-bh: (get committed-anchor-bh v),
        lender-btc-addr: (get lender-btc-addr v), amount-sats: (get amount-sats v),
        csv-blocks: (get csv-blocks v), lock-burn-height: (get lock-burn-height v),
        state: STATE-REFUNDED, registered-by: (get registered-by v), lender: (get lender v),
        preimage-publisher: (get preimage-publisher v), preimage-published-at: (get preimage-published-at v) })
    (print { event: "vault-refunded", vault-id: vault-id })
    (ok true)))

;; --- Admin ---
(define-public (set-lending-contract (addr principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED) (var-set lending-contract addr) (ok true)))

;; --- Read-only ---
(define-read-only (get-vault (vault-id (buff 32)))
  (map-get? vaults { vault-id: vault-id }))

(define-read-only (get-vault-state (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-none v) none (some (get state (unwrap-panic v))))))

(define-read-only (is-vault-borrowable (vault-id (buff 32)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-none v) false
      (let ((vault (unwrap-panic v)))
        (and (is-eq (get state vault) STATE-ACTIVE)
             (> (get amount-sats vault) u0))))))

(define-read-only (verify-preimage (vault-id (buff 32)) (payload (buff 80)))
  (let ((v (map-get? vaults { vault-id: vault-id })))
    (if (is-none v) (err ERR-VAULT-NOT-FOUND)
      (ok (is-eq (sha256 payload) (get committed-anchor-bh (unwrap-panic v)))))))

(define-read-only (get-owner) (var-get owner))
(define-read-only (get-lending-contract) (var-get lending-contract))
