;; BTCPSwap.clar - Yield vault for tTRION (accounting-only, no in-contract transfers)
;; Users deposit tTRION directly to the contract address via the token's transfer,
;; then call deposit() to record their share. Withdraw reverses this.

(define-constant CONTRACT-PRINCIPAL 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcpswap-v4)

(define-constant ERR-NOT-AUTHORIZED (err u950))
(define-constant ERR-INSUFFICIENT-LIQUIDITY (err u953))
(define-constant ERR-INSUFFICIENT-LP (err u955))
(define-constant SCALE u1000000)

(define-map user-shares { user: principal } { shares: uint, since: uint })
(define-data-var total-shares uint u0)
(define-data-var total-pool uint u0)
(define-data-var owner principal tx-sender)

(define-public (deposit (amount uint))
  (begin
    (asserts! (> amount u0) (err u953))
    (let ((existing (map-get? user-shares { user: tx-sender })))
      (let ((shares-to-mint (if (is-eq (var-get total-shares) u0)
        amount
        (/ (* amount (var-get total-shares)) (var-get total-pool)))))
        (if (is-none existing)
          (map-set user-shares { user: tx-sender } { shares: shares-to-mint, since: burn-block-height })
          (let ((e (unwrap-panic existing)))
            (map-set user-shares { user: tx-sender } { shares: (+ (get shares e) shares-to-mint), since: burn-block-height })))
        (var-set total-shares (+ (var-get total-shares) shares-to-mint))
        (var-set total-pool (+ (var-get total-pool) amount))
        (print { event: "deposit", user: tx-sender, amount: amount, shares: shares-to-mint })
        (ok true)))))

(define-public (withdraw (shares uint))
  (let ((s (unwrap! (map-get? user-shares { user: tx-sender }) (err u955))))
    (asserts! (>= (get shares s) shares) (err u955))
    (asserts! (> shares u0) (err u955))
    (let ((payout (/ (* shares (var-get total-pool)) (var-get total-shares))))
      (map-set user-shares { user: tx-sender } { shares: (- (get shares s) shares), since: burn-block-height })
      (var-set total-shares (- (var-get total-shares) shares))
      (var-set total-pool (- (var-get total-pool) payout))
      (print { event: "withdraw", user: tx-sender, shares: shares, payout: payout })
      (ok true))))

(define-public (donate-yield (amount uint))
  (begin
    (asserts! (> amount u0) (err u953))
    (var-set total-pool (+ (var-get total-pool) amount))
    (print { event: "yield-donated", amount: amount, new-pool: (var-get total-pool) })
    (ok true)))

(define-public (set-owner (new-owner principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED) (var-set owner new-owner) (ok true)))

(define-read-only (get-balance (user principal))
  (let ((s (map-get? user-shares { user: user })))
    (if (is-none s) u0 (get shares (unwrap-panic s)))))

(define-read-only (get-total-shares) (var-get total-shares))
(define-read-only (get-total-pool) (var-get total-pool))
(define-read-only (get-share-price)
  (if (is-eq (var-get total-shares) u0) SCALE (/ (* (var-get total-pool) SCALE) (var-get total-shares))))
(define-read-only (get-payout-for-shares (shares uint))
  (if (is-eq (var-get total-shares) u0) u0 (/ (* shares (var-get total-pool)) (var-get total-shares))))
(define-read-only (get-owner) (var-get owner))
