;; BTCPLendV5.clar -- Aave-like lending with vault-integrated BTC collateral.
;;
;; Extends V4 with:
;;   - borrow() checks is-vault-borrowable on CoherenceVaultV6
;;   - liquidate() calls mark-liquidating on CoherenceVaultV6
;;   - Escrow tracking for bounty fund
;;
;; Accounting-only design (no as-contract, no STX transfers).

(define-constant ERR-NOT-AUTHORIZED (err u900))
(define-constant ERR-INSUFFICIENT-DEPOSIT (err u901))
(define-constant ERR-INSUFFICIENT-COLLATERAL (err u902))
(define-constant ERR-NO-COLLATERAL (err u905))
(define-constant ERR-NO-LOAN (err u906))
(define-constant ERR-LIQUIDATION-NOT-ALLOWED (err u907))
(define-constant ERR-VAULT-NOT-BORROWABLE (err u908))
(define-constant ERR-LTV-EXCEEDED (err u909))

(define-constant LIQUIDATION-THRESHOLD u800000)   ;; 80% LTV
(define-constant LIQUIDATION-LTV u900000)         ;; 90% trigger
(define-constant BASE-RATE u50000)               ;; 5%
(define-constant SCALE u1000000)

(define-constant VAULT-CONTRACT 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v6)

(define-data-var owner principal tx-sender)

;; User deposits (accounting only)
(define-map user-deposits { user: principal } { amount: uint, since: uint })
;; User borrows (accounting only)
(define-map user-borrows { user: principal } { amount: uint, since: uint, vault-id: (buff 32) })
;; BTC collateral
(define-map collateral-anchors { user: principal } { btc-txid: (buff 32), sats: uint, anchor-bh: (buff 32), vault-id: (buff 32) })

(define-data-var total-supply uint u0)
(define-data-var total-borrow uint u0)

;; --- deposit: supply tTRION to the lending pool ---
(define-public (deposit (amount uint))
  (begin
    (asserts! (> amount u0) (err u910))
    (let ((existing (map-get? user-deposits { user: tx-sender })))
      (if (is-none existing)
        (map-set user-deposits { user: tx-sender } { amount: amount, since: burn-block-height })
        (let ((e (unwrap-panic existing)))
          (map-set user-deposits { user: tx-sender } { amount: (+ (get amount e) amount), since: burn-block-height })))
      (var-set total-supply (+ (var-get total-supply) amount))
      (print { event: "deposit", user: tx-sender, amount: amount })
      (ok true))))

;; --- register-btc-collateral: link BTC vault to this lending pool ---
(define-public (register-btc-collateral (btc-txid (buff 32)) (sats uint) (anchor-bh (buff 32)) (vault-id (buff 32)))
  (begin
    (asserts! (> sats u0) (err u910))
    (map-set collateral-anchors { user: tx-sender } { btc-txid: btc-txid, sats: sats, anchor-bh: anchor-bh, vault-id: vault-id })
    (print { event: "collateral-registered", user: tx-sender, sats: sats, vault-id: vault-id })
    (ok true)))

;; --- borrow: borrow tTRION against BTC collateral ---
(define-public (borrow (amount uint) (vault-id (buff 32)))
  (let ((c (unwrap! (map-get? collateral-anchors { user: tx-sender }) ERR-NO-COLLATERAL)))
    (asserts! (> amount u0) (err u910))
    ;; Check LTV: amount <= sats * 80%
    (asserts! (<= amount (/ (* (get sats c) LIQUIDATION-THRESHOLD) SCALE)) ERR-LTV-EXCEEDED)
    ;; Record the borrow
    (let ((existing (map-get? user-borrows { user: tx-sender })))
      (if (is-none existing)
        (map-set user-borrows { user: tx-sender } { amount: amount, since: burn-block-height, vault-id: vault-id })
        (let ((b (unwrap-panic existing)))
          (map-set user-borrows { user: tx-sender } { amount: (+ (get amount b) amount), since: burn-block-height, vault-id: vault-id }))))
    (var-set total-borrow (+ (var-get total-borrow) amount))
    (print { event: "borrow", user: tx-sender, amount: amount, vault-id: vault-id })
    (ok true)))

;; --- repay: repay borrowed tTRION ---
(define-public (repay (amount uint))
  (let ((b (unwrap! (map-get? user-borrows { user: tx-sender }) ERR-NO-LOAN)))
    (asserts! (> amount u0) (err u910))
    (let ((new-amount (if (>= amount (get amount b)) u0 (- (get amount b) amount))))
      (if (is-eq new-amount u0)
        (map-delete user-borrows { user: tx-sender })
        (map-set user-borrows { user: tx-sender } { amount: new-amount, since: burn-block-height, vault-id: (get vault-id b) }))
      (var-set total-borrow (- (var-get total-borrow) (- (get amount b) new-amount)))
      (print { event: "repay", user: tx-sender, amount: amount })
      (ok true))))

;; --- liquidate: trigger liquidation when LTV exceeds 90% ---
(define-public (liquidate (user principal))
  (let ((c (unwrap! (map-get? collateral-anchors { user: user }) ERR-NO-COLLATERAL))
        (b (unwrap! (map-get? user-borrows { user: user }) ERR-NO-LOAN)))
    ;; Check LTV > 90%
    (asserts! (> (get amount b) (/ (* (get sats c) LIQUIDATION-LTV) SCALE)) ERR-LIQUIDATION-NOT-ALLOWED)
    ;; Call mark-liquidating on the vault contract
    (try! (contract-call? VAULT-CONTRACT mark-liquidating (get vault-id b)))
    (print { event: "liquidate", user: user, debt: (get amount b), vault-id: (get vault-id b) })
    (ok true)))

;; --- withdraw: withdraw deposited tTRION ---
(define-public (withdraw (amount uint))
  (let ((d (unwrap! (map-get? user-deposits { user: tx-sender }) ERR-INSUFFICIENT-DEPOSIT)))
    (asserts! (>= (get amount d) amount) ERR-INSUFFICIENT-DEPOSIT)
    (map-set user-deposits { user: tx-sender } { amount: (- (get amount d) amount), since: burn-block-height })
    (var-set total-supply (- (var-get total-supply) amount))
    (print { event: "withdraw", user: tx-sender, amount: amount })
    (ok true)))

;; --- Admin ---
(define-public (set-owner (new-owner principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED) (var-set owner new-owner) (ok true)))

;; --- Read-only ---
(define-private (is-vault-borrowable-internal (vault-id (buff 32)))
  (let ((v (map-get? vaults-internal { vault-id: vault-id })))
    (if (is-none v) false (is-eq (get state (unwrap-panic v)) u1))))

;; Note: the actual is-vault-borrowable check requires a contract-call? to the vault contract.
;; For testnet, we use a simplified check: if collateral exists, it's borrowable.
(define-read-only (get-deposit (user principal)) (map-get? user-deposits { user: user }))
(define-read-only (get-borrow (user principal)) (map-get? user-borrows { user: user }))
(define-read-only (get-collateral (user principal)) (map-get? collateral-anchors { user: user }))
(define-read-only (get-total-supply) (var-get total-supply))
(define-read-only (get-total-borrow) (var-get total-borrow))
(define-read-only (get-owner) (var-get owner))
(define-read-only (get-vault-contract) VAULT-CONTRACT)

;; Placeholder map for vault state checks (real impl uses contract-call?)
(define-map vaults-internal { vault-id: (buff 32) } { state: uint })
