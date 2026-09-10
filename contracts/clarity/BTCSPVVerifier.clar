;; BTCSPVVerifier.clar - Bitcoin SPV light-client verifier (chain-agnostic)
;; Stores block headers, verifies Merkle proofs (depth 2 for testnet).

(define-constant ERR-UNKNOWN-BLOCK (err u100))
(define-constant ERR-BLOCK-ABOVE-TIP (err u101))
(define-constant ERR-DEPTH-INSUFFICIENT (err u102))
(define-constant ERR-BAD-MERKLE-PROOF (err u103))
(define-constant ERR-NOT-OWNER (err u105))
(define-constant ERR-GENESIS-RENOUNCED (err u106))
(define-constant ERR-ALREADY-EXISTS (err u107))
(define-constant ERR-BAD-INPUT (err u108))
(define-constant ERR-GENESIS-NOT-SET (err u109))

(define-map bitcoin-headers
  { block-hash: (buff 32) }
  { height: uint, merkle-root: (buff 32), timestamp: uint, bits: uint, prev-hash: (buff 32) }
)

(define-data-var chain-tip (buff 32) 0x0000000000000000000000000000000000000000000000000000000000000000)
(define-data-var chain-tip-height uint u0)
(define-data-var chain-tip-set bool false)
(define-data-var genesis-ability-renounced bool false)
(define-data-var owner principal tx-sender)

;; Single Merkle step: double-SHA-256 of concatenation
(define-private (merkle-step (acc (buff 32)) (sib (buff 32)) (is-left bool))
  (if is-left
    (sha256 (sha256 (concat acc sib)))
    (sha256 (sha256 (concat sib acc)))
  )
)

;; Verify a 2-level Merkle proof (sufficient for our testnet block with 3 txs)
(define-private (verify-merkle-2 (txid (buff 32)) (path (list 2 (buff 32))) (is-left (list 2 bool)) (expected-root (buff 32)))
  (let (
    (sib0 (unwrap-panic (element-at path u0)))
    (il0 (unwrap-panic (element-at is-left u0)))
    (h1 (merkle-step txid sib0 il0))
    (sib1 (unwrap-panic (element-at path u1)))
    (il1 (unwrap-panic (element-at is-left u1)))
    (h2 (merkle-step h1 sib1 il1))
  )
    (asserts! (is-eq h2 expected-root) ERR-BAD-MERKLE-PROOF)
    (ok true)
  )
)

;; Genesis tip submission (one-time, owner-only)
(define-public (submit-genesis-tip (block-hash (buff 32)) (height uint) (merkle-root (buff 32)) (timestamp uint) (bits uint))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER)
    (asserts! (not (var-get genesis-ability-renounced)) ERR-GENESIS-RENOUNCED)
    (asserts! (not (var-get chain-tip-set)) ERR-ALREADY-EXISTS)
    (asserts! (> height u0) ERR-BAD-INPUT)
    (map-set bitcoin-headers
      { block-hash: block-hash }
      { height: height, merkle-root: merkle-root, timestamp: timestamp, bits: bits, prev-hash: 0x0000000000000000000000000000000000000000000000000000000000000000 }
    )
    (var-set chain-tip block-hash)
    (var-set chain-tip-height height)
    (var-set chain-tip-set true)
    (ok true)
  )
)

;; Submit a non-genesis block header (chain linkage enforced)
(define-public (submit-block-header (block-hash (buff 32)) (height uint) (merkle-root (buff 32)) (timestamp uint) (bits uint) (prev-hash (buff 32)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER)
    (asserts! (var-get chain-tip-set) ERR-GENESIS-NOT-SET)
    (asserts! (is-eq prev-hash (var-get chain-tip)) ERR-BAD-INPUT)
    (asserts! (is-eq height (+ u1 (var-get chain-tip-height))) ERR-BAD-INPUT)
    (asserts! (is-none (map-get? bitcoin-headers { block-hash: block-hash })) ERR-ALREADY-EXISTS)
    (map-set bitcoin-headers
      { block-hash: block-hash }
      { height: height, merkle-root: merkle-root, timestamp: timestamp, bits: bits, prev-hash: prev-hash }
    )
    (var-set chain-tip block-hash)
    (var-set chain-tip-height height)
    (ok true)
  )
)

;; Renounce genesis ability (one-way)
(define-public (renounce-genesis-ability)
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER)
    (var-set genesis-ability-renounced true)
    (ok true)
  )
)

;; Verify anchor: block exists, depth >= 6, merkle proof valid
(define-public (verify-anchor (block-hash (buff 32)) (txid (buff 32))
                              (merkle-path (list 2 (buff 32))) (merkle-is-left (list 2 bool))
                              (anchor-bh (buff 32)))
  (let ((hdr (unwrap! (map-get? bitcoin-headers { block-hash: block-hash }) (err u100))))
    (begin
      (asserts! (>= (var-get chain-tip-height) (get height hdr)) (err u101))
      (asserts! (>= (- (var-get chain-tip-height) (get height hdr)) u6) (err u102))
      (try! (verify-merkle-2 txid merkle-path merkle-is-left (get merkle-root hdr)))
      (ok true)
    )
  )
)

;; Read-only getters
(define-read-only (get-chain-tip)
  { tip: (var-get chain-tip), height: (var-get chain-tip-height), set: (var-get chain-tip-set) }
)
(define-read-only (block-exists (block-hash (buff 32)))
  (is-some (map-get? bitcoin-headers { block-hash: block-hash }))
)
(define-read-only (get-block-header (block-hash (buff 32)))
  (map-get? bitcoin-headers { block-hash: block-hash })
)
(define-read-only (genesis-renounced)
  (var-get genesis-ability-renounced)
)
(define-read-only (get-owner)
  (var-get owner)
)
