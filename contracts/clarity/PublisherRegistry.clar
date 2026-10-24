;; PublisherRegistry.clar -- Decentralized preimage publisher network.
;; Accounting-only (no as-contract, no STX transfers in contract).
;; Bounties tracked in a map. Settlement happens off-chain or via tTRION.
;;
;; Trust model:
;;   - Safety: unchanged (SHA-256 preimage resistance + CSV refund)
;;   - Liveness: requires 1-of-n publishers to be online (not TRION)
;;
;; Bounty split: 40% publisher, 40% relayer, 20% protocol treasury

(define-constant ERR-NOT-AUTHORIZED (err u1000))
(define-constant ERR-INSUFFICIENT-STAKE (err u1001))
(define-constant ERR-ALREADY-REGISTERED (err u1002))
(define-constant ERR-NOT-REGISTERED (err u1003))
(define-constant ERR-STAKE-LOCKED (err u1004))
(define-constant ERR-VAULT-NOT-LIQUIDATING (err u1005))
(define-constant ERR-ALREADY-CLAIMED (err u1006))
(define-constant ERR-NO-STAKE (err u1007))
(define-constant ERR-HEARTBEAT-TOO-EARLY (err u1008))

(define-constant MIN-STAKE u5000000)
(define-constant HEARTBEAT-INTERVAL u12)
(define-constant UNSTAKE-DELAY u144)
(define-constant MAX-MISSED-HEARTBEATS u3)
(define-constant BOUNTY-PUBLISHER-BPS u4000)
(define-constant BOUNTY-RELAYER-BPS u4000)
(define-constant BOUNTY-TREASURY-BPS u2000)

(define-data-var owner principal tx-sender)
(define-data-var treasury principal tx-sender)
(define-data-var publisher-count uint u0)

;; Publisher state -- stake is tracked in the map (accounting only, no actual STX transfer)
(define-map publishers
  { addr: principal }
  { stake: uint, registered-at: uint, last-heartbeat: uint, missed-count: uint, active: bool })

;; Bounty escrow: vault-id -> bounty amount (in microSTX, accounting only)
(define-map bounties
  { vault-id: (buff 32) }
  { amount: uint, funder: principal, claimed: bool, claimer: principal })

;; --- Public functions ---

;; Register as a publisher with minimum stake (accounting only)
(define-public (register-publisher (stake-amount uint))
  (begin
    (asserts! (>= stake-amount MIN-STAKE) ERR-INSUFFICIENT-STAKE)
    (asserts! (is-none (map-get? publishers { addr: tx-sender })) ERR-ALREADY-REGISTERED)
    (map-set publishers { addr: tx-sender }
      { stake: stake-amount, registered-at: burn-block-height, last-heartbeat: burn-block-height, missed-count: u0, active: true })
    (var-set publisher-count (+ u1 (var-get publisher-count)))
    (print { event: "publisher-registered", publisher: tx-sender, stake: stake-amount })
    (ok true)))

;; Heartbeat -- publisher proves liveness
(define-public (heartbeat)
  (let ((p (unwrap! (map-get? publishers { addr: tx-sender }) ERR-NOT-REGISTERED)))
    (asserts! (get active p) ERR-NOT-REGISTERED)
    (asserts! (>= burn-block-height (+ (get last-heartbeat p) HEARTBEAT-INTERVAL)) ERR-HEARTBEAT-TOO-EARLY)
    (map-set publishers { addr: tx-sender }
      { stake: (get stake p), registered-at: (get registered-at p),
        last-heartbeat: burn-block-height, missed-count: u0, active: true })
    (ok true)))

;; Slash a publisher who missed heartbeats (permissionless)
(define-public (slash (publisher principal))
  (let ((p (unwrap! (map-get? publishers { addr: publisher }) ERR-NOT-REGISTERED)))
    (asserts! (get active p) ERR-NOT-REGISTERED)
    (asserts! (> burn-block-height (+ (get last-heartbeat p) (* HEARTBEAT-INTERVAL (+ u1 MAX-MISSED-HEARTBEATS)))) ERR-NOT-AUTHORIZED)
    (map-set publishers { addr: publisher }
      { stake: u0, registered-at: (get registered-at p),
        last-heartbeat: (get last-heartbeat p), missed-count: (+ u1 (get missed-count p)), active: false })
    (print { event: "publisher-slashed", publisher: publisher, stake-slashed: (get stake p) })
    (ok true)))

;; Withdraw stake (after unstake delay -- accounting only, no STX transfer)
(define-public (withdraw-stake)
  (let ((p (unwrap! (map-get? publishers { addr: tx-sender }) ERR-NOT-REGISTERED)))
    (asserts! (not (get active p)) ERR-STAKE-LOCKED)
    (asserts! (> (get stake p) u0) ERR-NO-STAKE)
    (asserts! (>= burn-block-height (+ (get last-heartbeat p) UNSTAKE-DELAY)) ERR-STAKE-LOCKED)
    (let ((amount (get stake p)))
      (map-set publishers { addr: tx-sender }
        { stake: u0, registered-at: (get registered-at p),
          last-heartbeat: (get last-heartbeat p), missed-count: (get missed-count p), active: false })
      (print { event: "stake-withdrawn", publisher: tx-sender, amount: amount })
      (ok true))))

;; Fund a bounty for a vault (accounting only)
(define-public (fund-bounty (vault-id (buff 32)) (amount uint))
  (begin
    (asserts! (> amount u0) ERR-INSUFFICIENT-STAKE)
    (asserts! (is-none (map-get? bounties { vault-id: vault-id })) ERR-ALREADY-CLAIMED)
    (map-set bounties { vault-id: vault-id } { amount: amount, funder: tx-sender, claimed: false, claimer: tx-sender })
    (print { event: "bounty-funded", vault-id: vault-id, amount: amount, funder: tx-sender })
    (ok true)))

;; Claim bounty (called by relayer who broadcast the BTC spend)
(define-public (claim-bounty (vault-id (buff 32)))
  (let ((b (unwrap! (map-get? bounties { vault-id: vault-id }) ERR-VAULT-NOT-LIQUIDATING)))
    (asserts! (not (get claimed b)) ERR-ALREADY-CLAIMED)
    (let ((total (get amount b))
          (relayer-share (/ (* total BOUNTY-RELAYER-BPS) u10000))
          (treasury-share (/ (* total BOUNTY-TREASURY-BPS) u10000))
          (publisher-share (- total (+ relayer-share treasury-share))))
      (map-set bounties { vault-id: vault-id } { amount: (get amount b), funder: (get funder b), claimed: true, claimer: tx-sender })
      (print { event: "bounty-claimed", vault-id: vault-id, relayer: tx-sender, relayer-share: relayer-share, treasury-share: treasury-share, publisher-share: publisher-share })
      (ok true))))

;; Set treasury address (owner-only)
(define-public (set-treasury (new-treasury principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (var-set treasury new-treasury)
    (ok true)))

;; --- Read-only functions ---

(define-read-only (get-publisher (addr principal))
  (map-get? publishers { addr: addr }))

(define-read-only (get-publisher-count)
  (var-get publisher-count))

(define-read-only (get-bounty (vault-id (buff 32)))
  (map-get? bounties { vault-id: vault-id }))

(define-read-only (is-publisher-active (addr principal))
  (let ((p (map-get? publishers { addr: addr })))
    (if (is-none p) false (get active (unwrap-panic p)))))

(define-read-only (get-min-stake)
  MIN-STAKE)

(define-read-only (get-owner)
  (var-get owner))

(define-read-only (get-treasury)
  (var-get treasury))
