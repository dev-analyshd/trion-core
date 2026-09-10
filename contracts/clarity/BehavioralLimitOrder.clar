;; BehavioralLimitOrder.clar - behavioral limit order registry (chain-agnostic).
;; Stores orders with a match-quality score; supports partial fills and cancellation.

(define-constant SIDE-BUY u0)
(define-constant SIDE-SELL u1)

(define-constant STATUS-PENDING u0)
(define-constant STATUS-FILLED u1)
(define-constant STATUS-PARTIAL u2)
(define-constant STATUS-EXPIRED u3)
(define-constant STATUS-CANCELLED u4)

(define-map orders
  { order-id: (buff 32) }
  { entity-id: (buff 32), route-id: (buff 32), side: uint, asset: (buff 32),
    amount: uint, price: uint, match-quality-score: uint, filled: uint,
    status: uint, created: uint, owner: principal }
)

(define-data-var owner principal tx-sender)  ;; contract deployer (not order owner)

(define-public (place-order (order-id (buff 32)) (entity-id (buff 32)) (route-id (buff 32))
                          (side uint) (asset (buff 32)) (amount uint) (price uint))
  (begin
    (asserts! (or (is-eq side SIDE-BUY) (is-eq side SIDE-SELL)) (err u607))
    (asserts! (> amount u0) (err u603))
    (asserts! (> price u0) (err u602))
    (asserts! (is-none (map-get? orders { order-id: order-id })) (err u604))
    (map-set orders
      { order-id: order-id }
      { entity-id: entity-id, route-id: route-id, side: side, asset: asset,
        amount: amount, price: price, match-quality-score: u0, filled: u0,
        status: STATUS-PENDING, created: tenure-height, owner: tx-sender }
    )
    (ok true)
  )
)

(define-public (fill-order (order-id (buff 32)) (fill-amount uint) (match-quality uint))
  (begin
    (asserts! (> fill-amount u0) (err u603))
    (asserts! (<= match-quality u1000000) (err u607))
    (let ((o (unwrap! (map-get? orders { order-id: order-id }) (err u600))))
      (asserts! (or (is-eq (get status o) STATUS-PENDING) (is-eq (get status o) STATUS-PARTIAL)) (err u604))
      (let ((new-filled (+ (get filled o) fill-amount)))
        (asserts! (<= new-filled (get amount o)) (err u606))
        (let ((new-status (if (is-eq new-filled (get amount o)) STATUS-FILLED STATUS-PARTIAL)))
          (map-set orders
            { order-id: order-id }
            { entity-id: (get entity-id o), route-id: (get route-id o), side: (get side o),
              asset: (get asset o), amount: (get amount o), price: (get price o),
              match-quality-score: match-quality, filled: new-filled,
              status: new-status, created: (get created o), owner: (get owner o) }
          )
          (ok true)
        )
      )
    )
  )
)

(define-public (cancel-order (order-id (buff 32)))
  (begin
    (let ((o (unwrap! (map-get? orders { order-id: order-id }) (err u600))))
      (asserts! (or (is-eq tx-sender (get owner o)) (is-eq tx-sender (var-get owner))) (err u601))
      (asserts! (not (is-eq (get status o) STATUS-FILLED)) (err u604))
      (map-set orders
        { order-id: order-id }
        { entity-id: (get entity-id o), route-id: (get route-id o), side: (get side o),
          asset: (get asset o), amount: (get amount o), price: (get price o),
          match-quality-score: (get match-quality-score o), filled: (get filled o),
          status: STATUS-CANCELLED, created: (get created o), owner: (get owner o) }
      )
      (ok true)
    )
  )
)

(define-read-only (get-order (order-id (buff 32)))
  (map-get? orders { order-id: order-id })
)

(define-read-only (get-owner) (var-get owner))
