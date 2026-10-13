;; BTCPIntent.clar - BTCP intent registry (chain-agnostic).
;; FIX: Added 6 missing S4.1 fields to map schema + register-intent params
;; FIX: Aligned status enum with Solidity (EXPIRED=5, RESURRECTED=6)

;; Action enum
(define-constant ACTION-SWAP u0)
(define-constant ACTION-TRANSFER u1)
(define-constant ACTION-LIQUIDITY u2)
(define-constant ACTION-STAKE u3)
(define-constant ACTION-BORROW u4)

;; Status enum -- ALIGNED with Solidity (EXPIRED=5, RESURRECTED=6)
(define-constant STATUS-PENDING u0)
(define-constant STATUS-ROUTING u1)
(define-constant STATUS-EXECUTING u2)
(define-constant STATUS-COMPLETED u3)
(define-constant STATUS-FAILED u4)
(define-constant STATUS-EXPIRED u5)
(define-constant STATUS-RESURRECTED u6)

;; Privacy enum
(define-constant PRIVACY-PUBLIC u0)
(define-constant PRIVACY-ZK-CREDENTIAL u1)
(define-constant PRIVACY-INVISIBLE u2)

;; Chain preference enum
(define-constant CHAIN-PREF-OPTIMAL u0)
(define-constant CHAIN-PREF-SINGLE-CHAIN u1)
(define-constant CHAIN-PREF-LIST u2)

;; Finality enum
(define-constant FINALITY-FAST u0)
(define-constant FINALITY-STANDARD u1)
(define-constant FINALITY-SECURE u2)

;; FIX: Map schema now includes all 6 S4.1 fields
(define-map intents
  { intent-hash: (buff 32) }
  { entity-id: (buff 32), action: uint, asset-in: (buff 32), asset-out: (buff 32),
    magnitude: uint, source-chain: uint, dest-chain: uint, deadline: uint,
    max-gas-usd: uint, min-nl-score: uint,
    min-finality: uint, chain-pref: uint, privacy: uint,
    btcp-version: uint, nonce: uint, travel-rule-proof: (buff 32),
    status: uint, created: uint, submitter: principal }
)

(define-data-var owner principal tx-sender)

;; FIX: register-intent now accepts all S4.1 fields
(define-public (register-intent (intent-hash (buff 32)) (entity-id (buff 32)) (action uint)
                                (asset-in (buff 32)) (asset-out (buff 32)) (magnitude uint)
                                (source-chain uint) (dest-chain uint) (deadline uint)
                                (max-gas-usd uint) (min-nl-score uint)
                                (min-finality uint) (chain-pref uint) (privacy uint)
                                (btcp-version uint) (nonce uint) (travel-rule-proof (buff 32)))
  (begin
    (asserts! (<= action ACTION-BORROW) (err u300))
    (asserts! (> magnitude u0) (err u301))
    (asserts! (> nonce u0) (err u306))
    (asserts! (<= privacy PRIVACY-INVISIBLE) (err u307))
    (asserts! (<= chain-pref CHAIN-PREF-LIST) (err u308))
    (asserts! (<= min-finality FINALITY-SECURE) (err u309))
    (asserts! (is-none (map-get? intents { intent-hash: intent-hash })) (err u305))
    (map-set intents
      { intent-hash: intent-hash }
      { entity-id: entity-id, action: action, asset-in: asset-in, asset-out: asset-out,
        magnitude: magnitude, source-chain: source-chain, dest-chain: dest-chain,
        deadline: deadline, max-gas-usd: max-gas-usd, min-nl-score: min-nl-score,
        min-finality: min-finality, chain-pref: chain-pref, privacy: privacy,
        btcp-version: btcp-version, nonce: nonce, travel-rule-proof: travel-rule-proof,
        status: STATUS-PENDING, created: burn-block-height, submitter: tx-sender }
    )
    (print { event: "intent-registered", intent-hash: intent-hash })
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
          min-nl-score: (get min-nl-score i), min-finality: (get min-finality i),
          chain-pref: (get chain-pref i), privacy: (get privacy i),
          btcp-version: (get btcp-version i), nonce: (get nonce i),
          travel-rule-proof: (get travel-rule-proof i), status: new-status,
          created: (get created i), submitter: (get submitter i) }
      )
      (print { event: "intent-status-updated", intent-hash: intent-hash, new-status: new-status })
      (ok true)
    )
  )
)

(define-read-only (get-intent (intent-hash (buff 32)))
  (map-get? intents { intent-hash: intent-hash })
)

(define-read-only (get-owner) (var-get owner))
