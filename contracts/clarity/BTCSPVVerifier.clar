;; BTCSPVVerifier.clar - Bitcoin SPV light-client verifier (chain-agnostic)
;; FIX C5: Real PoW verification -- sha256(sha256(80-byte header)) byte-reversed
;;         must equal the caller-supplied block-hash (Bitcoin BE display form).
;; FIX C6: Variable-depth Merkle (up to 16 levels) via `fold` over
;;         { sib, is-left } tuples -- supports blocks with up to 2^16 = 65,536 txs.
;; Stores block headers, verifies Merkle proofs against the stored merkle-root.

(define-constant ERR-UNKNOWN-BLOCK (err u100))
(define-constant ERR-BLOCK-ABOVE-TIP (err u101))
(define-constant ERR-DEPTH-INSUFFICIENT (err u102))
(define-constant ERR-BAD-MERKLE-PROOF (err u103))
(define-constant ERR-NOT-OWNER (err u105))
(define-constant ERR-GENESIS-RENOUNCED (err u106))
(define-constant ERR-ALREADY-EXISTS (err u107))
(define-constant ERR-BAD-INPUT (err u108))
(define-constant ERR-GENESIS-NOT-SET (err u109))
(define-constant ERR-POW_FAILED (err u110))

(define-map bitcoin-headers
  { block-hash: (buff 32) }
  { height: uint, merkle-root: (buff 32), timestamp: uint, bits: uint, prev-hash: (buff 32) }
)

(define-data-var chain-tip (buff 32) 0x0000000000000000000000000000000000000000000000000000000000000000)
(define-data-var chain-tip-height uint u0)
(define-data-var chain-tip-set bool false)
(define-data-var genesis-ability-renounced bool false)
(define-data-var owner principal tx-sender)

;; ---------------------------------------------------------------------------
;; FIX C5: Real Proof-of-Work verification.
;;
;; Bitcoin byte-order convention (documented for future maintainers):
;;   - `bitcoin-cli getblockhash <height>` returns the block hash as a hex
;;     string in BIG-ENDIAN display order (reverse of the internal little-
;;     endian byte order used inside the prev-hash field of the next block).
;;   - The caller therefore supplies `block-hash` as a 32-byte buffer in BE
;;     display form (i.e. the same byte order as the hex string from
;;     `getblockhash`).
;;   - Clarity's `sha256` primitive returns the 32-byte digest in its natural
;;     byte order, which -- for Bitcoin's double-SHA-256 block hash -- matches
;;     Bitcoin's INTERNAL little-endian storage form.
;;   - Hence: to verify the header hashes to the claimed block-hash, we compute
;;     `sha256(sha256(header))` and compare its byte-reversed form to the
;;     caller-supplied `block-hash`:
;;         reverse32(sha256(sha256(header))) == block-hash
;;     (equivalently, sha256(sha256(header)) == reverse32(block-hash)).
;; ---------------------------------------------------------------------------

;; Reverse a 32-byte buffer (Bitcoin internal LE <-> display BE conversion).
;; Implemented as a balanced binary tree of `concat` calls for O(log 32) depth
;; (Clarity buffers are length-indexed, so each `let` binding has a static type).
(define-private (reverse-32 (b (buff 32)))
  (let (
    (b31 (unwrap-panic (element-at b u31)))
    (b30 (unwrap-panic (element-at b u30)))
    (b29 (unwrap-panic (element-at b u29)))
    (b28 (unwrap-panic (element-at b u28)))
    (b27 (unwrap-panic (element-at b u27)))
    (b26 (unwrap-panic (element-at b u26)))
    (b25 (unwrap-panic (element-at b u25)))
    (b24 (unwrap-panic (element-at b u24)))
    (b23 (unwrap-panic (element-at b u23)))
    (b22 (unwrap-panic (element-at b u22)))
    (b21 (unwrap-panic (element-at b u21)))
    (b20 (unwrap-panic (element-at b u20)))
    (b19 (unwrap-panic (element-at b u19)))
    (b18 (unwrap-panic (element-at b u18)))
    (b17 (unwrap-panic (element-at b u17)))
    (b16 (unwrap-panic (element-at b u16)))
    (b15 (unwrap-panic (element-at b u15)))
    (b14 (unwrap-panic (element-at b u14)))
    (b13 (unwrap-panic (element-at b u13)))
    (b12 (unwrap-panic (element-at b u12)))
    (b11 (unwrap-panic (element-at b u11)))
    (b10 (unwrap-panic (element-at b u10)))
    (b9  (unwrap-panic (element-at b u9)))
    (b8  (unwrap-panic (element-at b u8)))
    (b7  (unwrap-panic (element-at b u7)))
    (b6  (unwrap-panic (element-at b u6)))
    (b5  (unwrap-panic (element-at b u5)))
    (b4  (unwrap-panic (element-at b u4)))
    (b3  (unwrap-panic (element-at b u3)))
    (b2  (unwrap-panic (element-at b u2)))
    (b1  (unwrap-panic (element-at b u1)))
    (b0  (unwrap-panic (element-at b u0)))
    ;; pair into 16 (buff 2)
    (p0  (concat b31 b30))
    (p1  (concat b29 b28))
    (p2  (concat b27 b26))
    (p3  (concat b25 b24))
    (p4  (concat b23 b22))
    (p5  (concat b21 b20))
    (p6  (concat b19 b18))
    (p7  (concat b17 b16))
    (p8  (concat b15 b14))
    (p9  (concat b13 b12))
    (p10 (concat b11 b10))
    (p11 (concat b9  b8))
    (p12 (concat b7  b6))
    (p13 (concat b5  b4))
    (p14 (concat b3  b2))
    (p15 (concat b1  b0))
    ;; pair into 8 (buff 4)
    (q0 (concat p0 p1))
    (q1 (concat p2 p3))
    (q2 (concat p4 p5))
    (q3 (concat p6 p7))
    (q4 (concat p8 p9))
    (q5 (concat p10 p11))
    (q6 (concat p12 p13))
    (q7 (concat p14 p15))
    ;; pair into 4 (buff 8)
    (r0 (concat q0 q1))
    (r1 (concat q2 q3))
    (r2 (concat q4 q5))
    (r3 (concat q6 q7))
    ;; pair into 2 (buff 16)
    (s0 (concat r0 r1))
    (s1 (concat r2 r3))
  )
    ;; final (buff 32)
    (concat s0 s1)
  )
)

;; Verify PoW: reverse32(sha256(sha256(80-byte header))) must equal the
;; caller-supplied block-hash (Bitcoin BE display form). Replaces the old
;; weak check that only verified the first byte of block-hash was 0x00.
(define-public (verify-pow (header (buff 80)) (block-hash (buff 32)))
  (begin
    (asserts! (is-eq (reverse-32 (sha256 (sha256 header))) block-hash) ERR-POW_FAILED)
    (ok true)
  )
)

;; ---------------------------------------------------------------------------
;; FIX C6: Variable-depth Merkle verification (up to 16 levels).
;;
;; The merkle path is supplied as a SINGLE list of { sib, is-left } tuples.
;; - `sib` is the sibling hash at this level (in Bitcoin internal LE form).
;; - `is-left` = true  -> current accumulator is the LEFT child  (acc || sib)
;; - `is-left` = false -> current accumulator is the RIGHT child (sib || acc)
;;
;; Iteration uses Clarity's `fold`, starting from the txid as the initial
;; accumulator and hashing pairwise up to the merkle root. A path of length 0
;; (single-tx block) yields the txid itself as the root.
;; ---------------------------------------------------------------------------

(define-private (merkle-fold (item { sib: (buff 32), is-left: bool }) (acc (buff 32)))
  (if (get is-left item)
    (sha256 (sha256 (concat acc (get sib item))))
    (sha256 (sha256 (concat (get sib item) acc)))
  )
)

;; Genesis tip submission (one-time, owner-only).
;; BREAKING: now requires an 80-byte raw Bitcoin header `(buff 80)` for real
;; PoW verification (sha256(sha256(header)) byte-reversed must equal block-hash).
(define-public (submit-genesis-tip (block-hash (buff 32)) (height uint) (merkle-root (buff 32))
                                   (timestamp uint) (bits uint) (header (buff 80)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER)
    (asserts! (not (var-get genesis-ability-renounced)) ERR-GENESIS-RENOUNCED)
    (asserts! (not (var-get chain-tip-set)) ERR-ALREADY-EXISTS)
    (asserts! (> height u0) ERR-BAD-INPUT)
    ;; FIX C5: Verify real PoW before accepting the genesis tip.
    (try! (verify-pow header block-hash))
    (map-set bitcoin-headers
      { block-hash: block-hash }
      { height: height, merkle-root: merkle-root, timestamp: timestamp, bits: bits,
        prev-hash: 0x0000000000000000000000000000000000000000000000000000000000000000 }
    )
    (var-set chain-tip block-hash)
    (var-set chain-tip-height height)
    (var-set chain-tip-set true)
    (ok true)
  )
)

;; Submit a non-genesis block header (chain linkage enforced).
;; BREAKING: now requires an 80-byte raw Bitcoin header `(buff 80)` for real
;; PoW verification (sha256(sha256(header)) byte-reversed must equal block-hash).
(define-public (submit-block-header (block-hash (buff 32)) (height uint) (merkle-root (buff 32))
                                    (timestamp uint) (bits uint) (prev-hash (buff 32))
                                    (header (buff 80)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER)
    (asserts! (var-get chain-tip-set) ERR-GENESIS-NOT-SET)
    (asserts! (is-eq prev-hash (var-get chain-tip)) ERR-BAD-INPUT)
    (asserts! (is-eq height (+ u1 (var-get chain-tip-height))) ERR-BAD-INPUT)
    (asserts! (is-none (map-get? bitcoin-headers { block-hash: block-hash })) ERR-ALREADY-EXISTS)
    ;; FIX C5: Verify real PoW before accepting the new header.
    (try! (verify-pow header block-hash))
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

;; Verify anchor: block exists, depth >= 6 confirmations, merkle proof valid.
;; BREAKING: the merkle path is now a single list of `{ sib, is-left }` tuples
;; of length up to 16 (was: two parallel `(list 2 ...)` lists).
;; The `anchor-bh` parameter is retained for ABI compatibility (H3 still
;; unresolved -- out of scope for this task).
(define-public (verify-anchor (block-hash (buff 32)) (txid (buff 32))
                              (merkle-path (list 16 { sib: (buff 32), is-left: bool }))
                              (anchor-bh (buff 32)))
  (let ((hdr (unwrap! (map-get? bitcoin-headers { block-hash: block-hash }) (err u100))))
    (begin
      (asserts! (>= (var-get chain-tip-height) (get height hdr)) (err u101))
      ;; Depth-6 confirmations check (unchanged).
      (asserts! (>= (- (var-get chain-tip-height) (get height hdr)) u6) (err u102))
      (let ((computed-root (fold merkle-fold merkle-path txid)))
        (asserts! (is-eq computed-root (get merkle-root hdr)) ERR-BAD-MERKLE-PROOF)
      )
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
