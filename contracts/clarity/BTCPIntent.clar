;; BTCPIntent.clar - BTCP intent registry (chain-agnostic).
;; Stores cross-chain intents with a 7-status lifecycle.

;; Action enum
(define-constant ACTION-SWAP u0)
(define-constant ACTION-TRANSFER u1)
(define-constant ACTION-LIQUIDITY u2)
(define-constant ACTION-STAKE u3)
(define-constant ACTION-BORROW u4)

;; Status enum
(define-constant STATUS-PENDING u0)
(define-constant STATUS-ROUTING u1)
(define-constant STATUS-EXECUTING u2)
(define-constant STATUS-COMPLETED u3)
(define-constant STATUS-FAILED u4)
(define-constant STATUS-RESURRECTED u5)
(define-constant STATUS-EXPIRED u6)

(define-map intents
  { intent-hash: (buff 32) }
  { entity-id: (buff 32), action: uint, asset-in: (buff 32), asset-out: (buff 32),
    magnitude: uint, source-chain: uint, dest-chain: uint, deadline: uint,
    max-gas-usd: uint, min-nl-score: uint, status: uint, created: uint, submitter: principal }
)

(define-data-var owner principal tx-sender)

(define-public (register-intent (intent-hash (buff 32)) (entity-id (buff 32)) (action uint)
                                (asset-in (buff 32)) (asset-out (buff 32)) (magnitude uint)
                                (source-chain uint) (dest-chain uint) (deadline uint)
                                (max-gas-usd uint) (min-nl-score uint))
  (begin
    (asserts! (<= action ACTION-BORROW) (err u300))
    (asserts! (> magnitude u0) (err u301))
    (asserts! (is-none (map-get? intents { intent-hash: intent-hash })) (err u305))
    (map-set intents
      { intent-hash: intent-hash }
      { entity-id: entity-id, action: action, asset-in: asset-in, asset-out: asset-out,
        magnitude: magnitude, source-chain: source-chain, dest-chain: dest-chain,
        deadline: deadline, max-gas-usd: max-gas-usd, min-nl-score: min-nl-score,
        status: STATUS-PENDING, created: tenure-height, submitter: tx-sender }
    )
    (ok true)
  )
)

(define-private (valid-transition (from uint) (to uint))
  (or
    (and (is-eq from STATUS-PENDING) (or (is-eq to STATUS-ROUTING) (is-eq to STATUS-FAILED) (is-eq to STATUS-EXPIRED)))
    (and (is-eq from STATUS-ROUTING) (or (is-eq to STATUS-EXECUTING) (is-eq to STATUS-FAILED) (is-eq to STATUS-EXPIRED)))
    (and (is-eq from STATUS-EXECUTING) (or (is-eq to STATUS-COMPLETED) (is-eq to STATUS-FAILED)))
    (and (is-eq from STATUS-FAILED) (is-eq to STATUS-RESURRECTED))
  )
)

(define-public (update-intent-status (intent-hash (buff 32)) (new-status uint))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u304))
    (let ((i (unwrap! (map-get? intents { intent-hash: intent-hash }) (err u303))))
      (asserts! (valid-transition (get status i) new-status) (err u302))
      (map-set intents
        { intent-hash: intent-hash }
        { entity-id: (get entity-id i), action: (get action i), asset-in: (get asset-in i),
          asset-out: (get asset-out i), magnitude: (get magnitude i),
          source-chain: (get source-chain i), dest-chain: (get dest-chain i),
          deadline: (get deadline i), max-gas-usd: (get max-gas-usd i),
          min-nl-score: (get min-nl-score i), status: new-status,
          created: (get created i), submitter: (get submitter i) }
      )
      (ok true)
    )
  )
)

(define-read-only (get-intent (intent-hash (buff 32)))
  (map-get? intents { intent-hash: intent-hash })
)

(define-read-only (get-owner) (var-get owner))
