;; BTCPRoute.clar - BTCP route registry linking anchor_bh -> execution_bh (chain-agnostic).

;; Route type enum
(define-constant ROUTE-NETTING u0)
(define-constant ROUTE-SPLIT u1)
(define-constant ROUTE-IAP u2)
(define-constant ROUTE-BSC u3)
(define-constant ROUTE-BLO u4)
(define-constant ROUTE-OOA u5)
(define-constant ROUTE-DIRECT u6)

(define-map routes
  { route-id: (buff 32) }
  { intent-hash: (buff 32), anchor-bh: (buff 32), execution-bh: (buff 32),
    anchor-chain: uint, execution-chain: uint, entity-id: (buff 32),
    gas-saved: uint, beo-continuity: uint, cc-coherence: uint,
    route-type: uint, verified: bool, created: uint, finalized: uint, registrar: principal }
)

(define-data-var owner principal tx-sender)

(define-public (register-route (route-id (buff 32)) (intent-hash (buff 32)) (anchor-bh (buff 32))
                              (anchor-chain uint) (execution-chain uint) (entity-id (buff 32))
                              (route-type uint))
  (begin
    (asserts! (<= route-type ROUTE-DIRECT) (err u404))
    (asserts! (is-none (map-get? routes { route-id: route-id })) (err u404))
    (map-set routes
      { route-id: route-id }
      { intent-hash: intent-hash, anchor-bh: anchor-bh,
        execution-bh: 0x0000000000000000000000000000000000000000000000000000000000000000,
        anchor-chain: anchor-chain, execution-chain: execution-chain, entity-id: entity-id,
        gas-saved: u0, beo-continuity: u0, cc-coherence: u0,
        route-type: route-type, verified: false, created: tenure-height,
        finalized: u0, registrar: tx-sender }
    )
    (ok true)
  )
)

(define-public (finalize-route (route-id (buff 32)) (execution-bh (buff 32))
                              (gas-saved uint) (beo-continuity uint) (cc-coherence uint))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u401))
    (let ((r (unwrap! (map-get? routes { route-id: route-id }) (err u400))))
      (asserts! (not (get verified r)) (err u402))
      (asserts! (<= beo-continuity u1000000) (err u403))
      (asserts! (<= cc-coherence u1000000) (err u403))
      (map-set routes
        { route-id: route-id }
        { intent-hash: (get intent-hash r), anchor-bh: (get anchor-bh r),
          execution-bh: execution-bh,
          anchor-chain: (get anchor-chain r), execution-chain: (get execution-chain r),
          entity-id: (get entity-id r), gas-saved: gas-saved,
          beo-continuity: beo-continuity, cc-coherence: cc-coherence,
          route-type: (get route-type r), verified: true,
          created: (get created r), finalized: tenure-height, registrar: (get registrar r) }
      )
      (ok true)
    )
  )
)

(define-read-only (get-route (route-id (buff 32)))
  (map-get? routes { route-id: route-id })
)

(define-read-only (route-verified (route-id (buff 32)))
  (let ((r (map-get? routes { route-id: route-id })))
    (if (is-none r) false (get verified (unwrap-panic r)))
  )
)

(define-read-only (get-owner) (var-get owner))
