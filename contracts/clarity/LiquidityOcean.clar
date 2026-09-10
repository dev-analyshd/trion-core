;; LiquidityOcean.clar - liquidity commitment registry (chain-agnostic).
;; Stores commitments that settle only if coherence >= min-coherence before expiry.

(define-constant STATUS-PENDING u0)
(define-constant STATUS-SETTLED u1)
(define-constant STATUS-REVERTED u2)

(define-map commitments
  { commitment-id: (buff 32) }
  { entity-id: (buff 32), route-id: (buff 32), asset: (buff 32), amount: uint,
    min-coherence: uint, expiry: uint, status: uint, created: uint,
    execution-bh: (buff 32), settled: uint, revert-code: uint, committer: principal }
)

(define-data-var owner principal tx-sender)

(define-public (commit-liquidity (commitment-id (buff 32)) (entity-id (buff 32)) (route-id (buff 32))
                                (asset (buff 32)) (amount uint) (min-coherence uint) (expiry uint))
  (begin
    (asserts! (> amount u0) (err u505))
    (asserts! (<= min-coherence u1000000) (err u504))
    (asserts! (> expiry tenure-height) (err u503))
    (asserts! (is-none (map-get? commitments { commitment-id: commitment-id })) (err u506))
    (map-set commitments
      { commitment-id: commitment-id }
      { entity-id: entity-id, route-id: route-id, asset: asset, amount: amount,
        min-coherence: min-coherence, expiry: expiry, status: STATUS-PENDING,
        created: tenure-height,
        execution-bh: 0x0000000000000000000000000000000000000000000000000000000000000000,
        settled: u0, revert-code: u0, committer: tx-sender }
    )
    (ok true)
  )
)

(define-public (settle-commitment (commitment-id (buff 32)) (coherence uint) (execution-bh (buff 32)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u501))
    (let ((c (unwrap! (map-get? commitments { commitment-id: commitment-id }) (err u500))))
      (asserts! (is-eq (get status c) STATUS-PENDING) (err u506))
      (asserts! (>= coherence (get min-coherence c)) (err u502))
      (asserts! (> (get expiry c) tenure-height) (err u503))
      (map-set commitments
        { commitment-id: commitment-id }
        { entity-id: (get entity-id c), route-id: (get route-id c), asset: (get asset c),
          amount: (get amount c), min-coherence: (get min-coherence c), expiry: (get expiry c),
          status: STATUS-SETTLED, created: (get created c), execution-bh: execution-bh,
          settled: tenure-height, revert-code: u0, committer: (get committer c) }
      )
      (ok true)
    )
  )
)

(define-public (revert-commitment (commitment-id (buff 32)) (reason uint))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u501))
    (let ((c (unwrap! (map-get? commitments { commitment-id: commitment-id }) (err u500))))
      (asserts! (is-eq (get status c) STATUS-PENDING) (err u506))
      (map-set commitments
        { commitment-id: commitment-id }
        { entity-id: (get entity-id c), route-id: (get route-id c), asset: (get asset c),
          amount: (get amount c), min-coherence: (get min-coherence c), expiry: (get expiry c),
          status: STATUS-REVERTED, created: (get created c),
          execution-bh: (get execution-bh c), settled: tenure-height,
          revert-code: reason, committer: (get committer c) }
      )
      (ok true)
    )
  )
)

(define-read-only (get-commitment (commitment-id (buff 32)))
  (map-get? commitments { commitment-id: commitment-id })
)

(define-read-only (get-owner) (var-get owner))
