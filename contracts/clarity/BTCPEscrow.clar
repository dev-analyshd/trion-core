;; BTCPEscrow.clar - BTCP escrow with quorum, etch-once, dispute fail-closed.
;; Chain-agnostic. Two-state HOLDING -> RELEASED | REVERTED.
;; Release requires: state==HOLDING, count>=quorum-required, !disputed,
;; coherence==stored, execution-bh==stored, freshness (block-time - attestation-time <= 300s).

;; --- Error codes ----------------------------------------------------------
(define-constant MAX-ATTESTATION-AGE u300)  ;; 300 seconds freshness window
(define-constant ESCROW-STATE-HOLDING u0)
(define-constant ESCROW-STATE-RELEASED u1)
(define-constant ESCROW-STATE-REVERTED u2)

;; --- Storage --------------------------------------------------------------
(define-map escrows
  { escrow-id: (buff 32) }
  { route-id: (buff 32), destination: principal, amount: uint, min-coherence: uint,
    lock-height: uint, timeout: uint, state: uint, locked-by: principal }
)

(define-map attestations
  { route-id: (buff 32) }
  { coherence: uint, execution-bh: (buff 32), count: uint, last-time: uint, disputed: bool }
)

;; has-attested: composite key (route-id, validator-principal) -> bool
(define-map has-attested
  { route-id: (buff 32), validator: principal }
  { value: bool }
)

(define-map validators { addr: principal } { active: bool })
(define-data-var validator-count uint u0)
(define-data-var quorum-required uint u3)
(define-data-var spv-verifier principal tx-sender)  ;; default to deployer; settable
(define-data-var owner principal tx-sender)

;; --- Helpers --------------------------------------------------------------
(define-private (is-validator-internal (v principal))
  (is-some (map-get? validators { addr: v }))
)

;; --- Public: validator management -----------------------------------------
(define-public (add-validator (v principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u209))
    (asserts! (< (var-get validator-count) u20) (err u210))
    (asserts! (is-none (map-get? validators { addr: v })) (err u107))
    (map-set validators { addr: v } { active: true })
    (var-set validator-count (+ u1 (var-get validator-count)))
    (ok true)
  )
)

(define-public (set-quorum-required (q uint))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u209))
    (asserts! (> q u0) (err u210))
    (var-set quorum-required q)
    (ok true)
  )
)

(define-public (set-spv-verifier (v principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) (err u209))
    (var-set spv-verifier v)
    (ok true)
  )
)

;; --- Public: lock / attest / release / revert -----------------------------

;; Lock an escrow. Anyone can lock; sets state=HOLDING.
(define-public (lock-escrow (escrow-id (buff 32)) (route-id (buff 32)) (destination principal)
                            (amount uint) (min-coherence uint) (timeout uint))
  (begin
    (asserts! (> amount u0) (err u210))
    (asserts! (is-none (map-get? escrows { escrow-id: escrow-id })) (err u201))
    (map-set escrows
      { escrow-id: escrow-id }
      { route-id: route-id, destination: destination, amount: amount, min-coherence: min-coherence,
        lock-height: tenure-height, timeout: timeout, state: ESCROW-STATE-HOLDING, locked-by: tx-sender }
    )
    (ok true)
  )
)

;; Submit an attestation. Validator-only. Etch-once (first attestation sets coherence + execution-bh).
;; Mismatch -> disputed=true (fail-closed). Tracks has-attested to prevent replay.
(define-public (submit-attestation (route-id (buff 32)) (coherence uint) (execution-bh (buff 32)) (attestation-time uint))
  (begin
    (asserts! (is-validator-internal tx-sender) (err u206))
    ;; Replay prevention: composite key (route-id, validator)
    (asserts! (is-none (map-get? has-attested { route-id: route-id, validator: tx-sender })) (err u207))
    (map-set has-attested { route-id: route-id, validator: tx-sender } { value: true })
    ;; Etch-once: first attestation sets coherence + execution-bh; mismatch -> disputed
    (let ((existing (map-get? attestations { route-id: route-id })))
      (if (is-none existing)
        ;; First attestation: etch the values
        (begin
          (map-set attestations
            { route-id: route-id }
            { coherence: coherence, execution-bh: execution-bh, count: u1, last-time: attestation-time, disputed: false }
          )
        )
        ;; Subsequent attestation: check match
        (let ((att (unwrap-panic existing)))
          (if (and (is-eq coherence (get coherence att)) (is-eq execution-bh (get execution-bh att)))
            (begin
              (map-set attestations
                { route-id: route-id }
                { coherence: (get coherence att), execution-bh: (get execution-bh att),
                  count: (+ u1 (get count att)), last-time: attestation-time, disputed: false }
              )
            )
            ;; Mismatch -> dispute (fail-closed)
            (begin
              (map-set attestations
                { route-id: route-id }
                { coherence: (get coherence att), execution-bh: (get execution-bh att),
                  count: (get count att), last-time: attestation-time, disputed: true }
              )
            )
          )
        )
      )
    )
    (ok true)
  )
)

;; Release an escrow. Requires: state==HOLDING, count>=quorum, !disputed,
;; coherence==stored, execution-bh==stored, freshness (block-time - attestation-time <= 300).
;; NOTE: Clarity doesn't have a block-timestamp builtin in epoch 3.0 - caller passes current-time.
;; For testnet, we use tenure-height as a proxy and accept a caller-provided current-time for freshness.
(define-public (release-escrow (escrow-id (buff 32)) (execution-bh (buff 32)) (coherence uint) (current-time uint))
  (begin
    (let ((e (unwrap! (map-get? escrows { escrow-id: escrow-id }) (err u200))))
      (asserts! (is-eq (get state e) ESCROW-STATE-HOLDING) (err u201))
      (let ((att (unwrap! (map-get? attestations { route-id: (get route-id e) }) (err u202))))
        (asserts! (>= (get count att) (var-get quorum-required)) (err u202))
        (asserts! (not (get disputed att)) (err u203))
        (asserts! (is-eq coherence (get coherence att)) (err u204))
        (asserts! (is-eq execution-bh (get execution-bh att)) (err u204))
        ;; Freshness: attestation-time within MAX-ATTESTATION-AGE of current-time
        (asserts! (<= (- current-time (get last-time att)) MAX-ATTESTATION-AGE) (err u205))
        ;; Update state to RELEASED
        (map-set escrows
          { escrow-id: escrow-id }
          { route-id: (get route-id e), destination: (get destination e), amount: (get amount e),
            min-coherence: (get min-coherence e), lock-height: (get lock-height e),
            timeout: (get timeout e), state: ESCROW-STATE-RELEASED, locked-by: (get locked-by e) }
        )
        (ok true)
      )
    )
  )
)

;; Revert an escrow. Timeout escape hatch - anyone can call if lock-height + timeout < tenure-height.
(define-public (revert-escrow (escrow-id (buff 32)) (reason uint))
  (begin
    (let ((e (unwrap! (map-get? escrows { escrow-id: escrow-id }) (err u200))))
      (asserts! (is-eq (get state e) ESCROW-STATE-HOLDING) (err u201))
      ;; Timeout: anyone can revert if expired
      (if (>= tenure-height (+ (get lock-height e) (get timeout e)))
        (begin
          (map-set escrows
            { escrow-id: escrow-id }
            { route-id: (get route-id e), destination: (get destination e), amount: (get amount e),
              min-coherence: (get min-coherence e), lock-height: (get lock-height e),
              timeout: (get timeout e), state: ESCROW-STATE-REVERTED, locked-by: (get locked-by e) }
          )
          (ok true)
        )
        ;; Not expired: only locked-by or owner can revert
        (begin
          (asserts! (or (is-eq tx-sender (get locked-by e)) (is-eq tx-sender (var-get owner))) (err u209))
          (map-set escrows
            { escrow-id: escrow-id }
            { route-id: (get route-id e), destination: (get destination e), amount: (get amount e),
              min-coherence: (get min-coherence e), lock-height: (get lock-height e),
              timeout: (get timeout e), state: ESCROW-STATE-REVERTED, locked-by: (get locked-by e) }
          )
          (ok true)
        )
      )
    )
  )
)

;; --- Read-only getters ----------------------------------------------------
(define-read-only (get-escrow (escrow-id (buff 32)))
  (map-get? escrows { escrow-id: escrow-id })
)

(define-read-only (get-route-attestation (route-id (buff 32)))
  (map-get? attestations { route-id: route-id })
)

(define-read-only (is-validator (v principal))
  (is-validator-internal v)
)

(define-read-only (get-quorum-required)
  (var-get quorum-required)
)

(define-read-only (get-validator-count)
  (var-get validator-count)
)

(define-read-only (get-spv-verifier)
  (var-get spv-verifier)
)

(define-read-only (get-owner)
  (var-get owner)
)

(define-read-only (get-has-attested (route-id (buff 32)) (v principal))
  (is-some (map-get? has-attested { route-id: route-id, validator: v }))
)
