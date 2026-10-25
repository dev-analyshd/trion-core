;; CoherenceGate.clar -- On-chain coherence gate for liquidation decisions.
;;
;; Gates liquidation: if C(t) < threshold, liquidation is BLOCKED (fail-closed).
;; The coherence score is published by the DW-BFT validator quorum (off-chain)
;; and recorded on-chain via publish-coherence-score.
;;
;; Threshold: dynamic, between 0.55 (low volatility) and 0.92 (high volatility).
;; Formula: threshold = THETA_MIN + (THETA_MAX - THETA_MIN) * volatility

(define-constant ERR-NOT-AUTHORIZED (err u1100))
(define-constant ERR-COHERENCE-BELOW-THRESHOLD (err u1101))
(define-constant ERR-NO-SCORE-PUBLISHED (err u1102))
(define-constant ERR-STALE-SCORE (err u1103))
(define-constant ERR-ALREADY-PUBLISHED (err u1104))

(define-constant THETA-MIN u550000)     ;; 0.55
(define-constant THETA-MAX u920000)     ;; 0.92
(define-constant SCALE u1000000)
(define-constant MAX-SCORE-AGE u144)    ;; 144 BTC blocks (~24h) before score is stale

(define-data-var owner principal tx-sender)

;; Latest coherence score (published by validator quorum)
(define-data-var latest-coherence uint u0)
(define-data-var latest-threshold uint THETA-MIN)
(define-data-var latest-volatility uint u0)
(define-data-var latest-published-at uint u0)
(define-data-var latest-publisher principal tx-sender)

;; Authorized publishers (validator set)
(define-map authorized-publishers { addr: principal } { active: bool })

;; --- publish-coherence-score: validator publishes C(t) and V(t) ---
(define-public (publish-coherence-score (coherence uint) (volatility uint))
  (begin
    (asserts! (is-some (map-get? authorized-publishers { addr: tx-sender })) ERR-NOT-AUTHORIZED)
    (asserts! (<= coherence SCALE) (err u1105))
    (asserts! (<= volatility SCALE) (err u1105))
    ;; Compute dynamic threshold: theta = theta_min + (theta_max - theta_min) * volatility
    (let ((threshold (+ THETA-MIN (/ (* (- THETA-MAX THETA-MIN) volatility) SCALE))))
      (var-set latest-coherence coherence)
      (var-set latest-volatility volatility)
      (var-set latest-threshold threshold)
      (var-set latest-published-at burn-block-height)
      (var-set latest-publisher tx-sender)
      (print { event: "coherence-published", coherence: coherence, volatility: volatility, threshold: threshold, publisher: tx-sender })
      (ok true))))

;; --- gate-liquidation: check if liquidation is allowed ---
;; Returns (ok true) if C(t) >= threshold AND score is fresh
;; Returns (err ...) if C(t) < threshold OR score is stale
(define-public (gate-liquidation (vault-id (buff 32)))
  (begin
    (asserts! (> (var-get latest-coherence) u0) ERR-NO-SCORE-PUBLISHED)
    (asserts! (<= (- burn-block-height (var-get latest-published-at)) MAX-SCORE-AGE) ERR-STALE-SCORE)
    (asserts! (>= (var-get latest-coherence) (var-get latest-threshold)) ERR-COHERENCE-BELOW-THRESHOLD)
    (print { event: "liquidation-gated", vault-id: vault-id, coherence: (var-get latest-coherence), threshold: (var-get latest-threshold) })
    (ok true)))

;; --- Admin ---
(define-public (add-publisher (addr principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (map-set authorized-publishers { addr: addr } { active: true })
    (ok true)))

(define-public (remove-publisher (addr principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (map-set authorized-publishers { addr: addr } { active: false })
    (ok true)))

;; --- Read-only ---
(define-read-only (get-coherence) (var-get latest-coherence))
(define-read-only (get-threshold) (var-get latest-threshold))
(define-read-only (get-volatility) (var-get latest-volatility))
(define-read-only (get-score-age) (- burn-block-height (var-get latest-published-at)))
(define-read-only (is-score-fresh) (<= (- burn-block-height (var-get latest-published-at)) MAX-SCORE-AGE))
(define-read-only (can-liquidate) (and (> (var-get latest-coherence) u0) (>= (var-get latest-coherence) (var-get latest-threshold)) (<= (- burn-block-height (var-get latest-published-at)) MAX-SCORE-AGE)))
(define-read-only (get-owner) (var-get owner))
