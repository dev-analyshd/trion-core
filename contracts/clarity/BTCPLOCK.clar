;; BTCPLOCK.clar - Bitcoin UTXO Lock Registry (Observation-Only Anchoring).
;; Records BTC UTXOs "locked" via OOA. The BTC never moves -- this contract
;; just records the anchor. Three-state lifecycle: LOCKED -> RELEASED | REVERTED.
;;
;; lock-btc    -- permissionless; anyone can register a UTXO anchor.
;; release-btc -- owner-only; marks Stacks-side escrow released (UTXO spendable).
;; revert-btc  -- owner anytime; anyone after unlock-height (timelock expired).

;; --- Error codes ----------------------------------------------------------
(define-constant ERR-NOT-AUTHORIZED (err u920))
(define-constant ERR-LOCK-NOT-FOUND (err u921))
(define-constant ERR-ALREADY-PROCESSED (err u922))
(define-constant ERR-TIMELOCK-NOT-EXPIRED (err u923))
(define-constant ERR-INVALID-SATS (err u924))
(define-constant ERR-INVALID-LOCK-ID (err u925))

;; --- Status enum ----------------------------------------------------------
(define-constant STATUS-LOCKED u0)    ;; UTXO is locked (recorded)
(define-constant STATUS-RELEASED u1)   ;; escrow on Stacks side released
(define-constant STATUS-REVERTED u2)   ;; escrow reverted, BTC UTXO returned to locker

;; --- Storage --------------------------------------------------------------
(define-map locks
  { lock-id: (buff 32) }
  { btc-txid: (buff 32), btc-block-height: uint, sats: uint, anchor-bh: (buff 32),
    locker: principal, status: uint, lock-height: uint, unlock-height: uint }
)

(define-data-var next-lock-id uint u0)
(define-data-var owner principal tx-sender)

;; --- Helpers --------------------------------------------------------------
;; lock-id = sha256(btc-txid || sender || burn-block-height)
;; Uses to-consensus-buff? to serialize principal and uint into buffers.
(define-private (compute-lock-id (btc-txid (buff 32)) (locker principal) (bh uint))
  (sha256 (concat btc-txid
           (concat (unwrap-panic (to-consensus-buff? locker))
                   (unwrap-panic (to-consensus-buff? bh)))))
)

;; --- Public: lock / release / revert --------------------------------------

;; lock-btc -- permissionless. Locker registers a BTC UTXO via OOA.
;; Generates lock-id = sha256(btc-txid || sender || burn-block-height).
;; Sets status=LOCKED, unlock-height = burn-block-height + timelock-blocks.
(define-public (lock-btc (btc-txid (buff 32)) (btc-block-height uint) (sats uint)
                          (anchor-bh (buff 32)) (timelock-blocks uint))
  (begin
    (asserts! (> sats u0) ERR-INVALID-SATS)
    (asserts! (is-eq (len btc-txid) u32) ERR-INVALID-LOCK-ID)
    (let ((lock-id (compute-lock-id btc-txid tx-sender burn-block-height)))
      (asserts! (is-none (map-get? locks { lock-id: lock-id })) ERR-ALREADY-PROCESSED)
      (map-set locks
        { lock-id: lock-id }
        { btc-txid: btc-txid, btc-block-height: btc-block-height, sats: sats,
          anchor-bh: anchor-bh, locker: tx-sender, status: STATUS-LOCKED,
          lock-height: burn-block-height,
          unlock-height: (+ burn-block-height timelock-blocks) })
      (var-set next-lock-id (+ u1 (var-get next-lock-id)))
      (print { type: "btc-lock", lock-id: lock-id, locker: tx-sender,
              sats: sats, btc-txid: btc-txid, anchor-bh: anchor-bh,
              unlock-height: (+ burn-block-height timelock-blocks) })
      (ok lock-id)
    )
  )
)

;; release-btc -- owner-only. Marks lock as STATUS-RELEASED.
;; After release, the BTC UTXO is "unlocked" (locker can spend it).
(define-public (release-btc (lock-id (buff 32)))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (let ((l (unwrap! (map-get? locks { lock-id: lock-id }) ERR-LOCK-NOT-FOUND)))
      (asserts! (is-eq (get status l) STATUS-LOCKED) ERR-ALREADY-PROCESSED)
      (map-set locks
        { lock-id: lock-id }
        { btc-txid: (get btc-txid l), btc-block-height: (get btc-block-height l),
          sats: (get sats l), anchor-bh: (get anchor-bh l), locker: (get locker l),
          status: STATUS-RELEASED, lock-height: (get lock-height l),
          unlock-height: (get unlock-height l) })
      (print { type: "btc-release", lock-id: lock-id, locker: (get locker l),
              sats: (get sats l), btc-txid: (get btc-txid l) })
      (ok true)
    )
  )
)

;; revert-btc -- owner anytime; anyone after unlock-height (timelock expired).
;; Marks lock as STATUS-REVERTED (BTC UTXO returned to locker).
(define-public (revert-btc (lock-id (buff 32)))
  (begin
    (let ((l (unwrap! (map-get? locks { lock-id: lock-id }) ERR-LOCK-NOT-FOUND)))
      (asserts! (is-eq (get status l) STATUS-LOCKED) ERR-ALREADY-PROCESSED)
      (let ((is-owner (is-eq tx-sender (var-get owner))))
        (asserts! (or is-owner (>= burn-block-height (get unlock-height l)))
                  ERR-TIMELOCK-NOT-EXPIRED)
        (map-set locks
          { lock-id: lock-id }
          { btc-txid: (get btc-txid l), btc-block-height: (get btc-block-height l),
            sats: (get sats l), anchor-bh: (get anchor-bh l), locker: (get locker l),
            status: STATUS-REVERTED, lock-height: (get lock-height l),
            unlock-height: (get unlock-height l) })
        (print { type: "btc-revert", lock-id: lock-id, locker: (get locker l),
                sats: (get sats l), caller: tx-sender,
                reason: (if is-owner "owner" "timelock-expired") })
        (ok true))
    )
  )
)

;; --- Read-only getters ----------------------------------------------------
(define-read-only (get-lock (lock-id (buff 32)))
  (map-get? locks { lock-id: lock-id })
)

(define-read-only (get-lock-status (lock-id (buff 32)))
  (match (map-get? locks { lock-id: lock-id })
    l (some (get status l))
    none)
)

(define-read-only (get-locker (lock-id (buff 32)))
  (match (map-get? locks { lock-id: lock-id })
    l (some (get locker l))
    none)
)

(define-read-only (get-anchor-bh (lock-id (buff 32)))
  (match (map-get? locks { lock-id: lock-id })
    l (some (get anchor-bh l))
    none)
)

(define-read-only (get-next-lock-id)
  (var-get next-lock-id)
)

(define-read-only (get-owner)
  (var-get owner)
)
