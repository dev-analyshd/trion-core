;; LiquidityOcean.clar - liquidity commitment registry (chain-agnostic).
;; FIX: Added ocean_score formula (§6.1): ocean_score = (cost × time × beo) / 1e12
;; FIX: Added MIN-COHERENCE-FLOOR on settlement

(define-constant STATUS-PENDING u0)
(define-constant STATUS-SETTLED u1)
(define-constant STATUS-REVERTED u2)
(define-constant MIN-COHERENCE-FLOOR u550000)

;; FIX: Added cost-score, time-score, beo-health, ocean-score fields
(define-map commitments
  { commitment-id: (buff 32) }
  { entity-id: (buff 32), route-id: (buff 32), asset: (buff 32), amount: uint,
    min-coherence: uint, expiry: uint, status: uint, created: uint,
    execution-bh: (buff 32), settled: uint, revert-code: uint, committer: principal,
    cost-score: uint, time-score: uint, beo-health: uint, ocean-score: uint }
)

(define-data-var owner principal tx-sender)

;; FIX: commit-liquidity now accepts ocean_score components and computes the score
(define-public (commit-liquidity (commitment-id (buff 32)) (entity-id (buff 32)) (route-id (buff 32))
                                (asset (buff 32)) (amount uint) (min-coherence uint) (expiry uint)
                                (cost-score uint) (time-score uint) (beo-health uint))
  (begin
    (asserts! (> amount u0) (err u505))
    (asserts! (<= min-coherence u1000000) (err u504))
    (asserts! (> expiry tenure-height) (err u503))
    (asserts! (is-none (map-get? commitments { commitment-id: commitment-id })) (err u506))
    (asserts! (<= cost-score u1000000) (err u507))
    (asserts! (<= time-score u1000000) (err u507))
    (asserts! (<= beo-health u1000000) (err u507))
    (let ((partial1 (/ (* cost-score time-score) u1000000))
          (ocean (/ (* partial1 beo-health) u1000000)))
      (map-set commitments
        { commitment-id: commitment-id }
        { entity-id: entity-id, route-id: route-id, asset: asset, amount: amount,
          min-coherence: min-coherence, expiry: expiry, status: STATUS-PENDING,
          created: tenure-height,
          execution-bh: 0x0000000000000000000000000000000000000000000000000000000000000000,
          settled: u0, revert-code: u0, committer: tx-sender,
          cost-score: cost-score, time-score: time-score, beo-health: beo-health,
          ocean-score: ocean }
      )
      (print { event: "liquidity-committed", commitment-id: commitment-id, ocean-score: ocean })
      (ok true)
    )
  )
)

;; FIX: settle-commitment now enforces MIN-COHERENCE-FLOOR
(define-public (settle-commitment (commitment-id (buff 32)) (coherence uint) (execution-bh (buff 32)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u501))
    (let ((c (unwrap! (map-get? commitments { commitment-id: commitment-id }) (err u500))))
      (asserts! (is-eq (get status c) STATUS-PENDING) (err u506))
      (asserts! (>= coherence (get min-coherence c)) (err u502))
      (asserts! (>= coherence MIN-COHERENCE-FLOOR) (err u508))
      (asserts! (> (get expiry c) tenure-height) (err u503))
      (map-set commitments
        { commitment-id: commitment-id }
        { entity-id: (get entity-id c), route-id: (get route-id c), asset: (get asset c),
          amount: (get amount c), min-coherence: (get min-coherence c), expiry: (get expiry c),
          status: STATUS-SETTLED, created: (get created c), execution-bh: execution-bh,
          settled: tenure-height, revert-code: u0, committer: (get committer c),
          cost-score: (get cost-score c), time-score: (get time-score c),
          beo-health: (get beo-health c), ocean-score: (get ocean-score c) }
      )
      (print { event: "liquidity-settled", commitment-id: commitment-id })
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
          revert-code: reason, committer: (get committer c),
          cost-score: (get cost-score c), time-score: (get time-score c),
          beo-health: (get beo-health c), ocean-score: (get ocean-score c) }
      )
      (print { event: "liquidity-reverted", commitment-id: commitment-id })
      (ok true)
    )
  )
)

(define-read-only (get-commitment (commitment-id (buff 32)))
  (map-get? commitments { commitment-id: commitment-id })
)

(define-read-only (get-ocean-score (commitment-id (buff 32)))
  (let ((c (map-get? commitments { commitment-id: commitment-id })))
    (if (is-none c) u0 (get ocean-score (unwrap-panic c)))
  )
)

(define-read-only (get-owner) (var-get owner))
