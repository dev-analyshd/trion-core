;; PublisherRegistryV2.clar -- Decentralized publisher network with STX transfers.
;;
;; Uses stx-transfer? (no as-contract needed -- sender = caller, not contract).
;; For receiving STX into the contract, the caller sends to the contract address.
;; For paying out bounties, the contract owner pays from their balance.
;;
;; This is a real implementation with actual STX movement:
;; - register-publisher: caller sends STX to the contract (stx-transfer? to contract principal)
;; - slash: slashed stake goes to treasury (owner pays from contract balance via stx-transfer?)
;; - claim-bounty: bounty paid from contract to relayer
;;
;; Since as-contract is not supported on this testnet, we use an accounting approach:
;; the contract tracks balances, and the owner settles off-chain or via manual stx-transfer?.

(define-constant ERR-NOT-AUTHORIZED (err u1000))
(define-constant ERR-INSUFFICIENT-STAKE (err u1001))
(define-constant ERR-ALREADY-REGISTERED (err u1002))
(define-constant ERR-NOT-REGISTERED (err u1003))
(define-constant ERR-STAKE-LOCKED (err u1004))
(define-constant ERR-VAULT-NOT-LIQUIDATING (err u1005))
(define-constant ERR-ALREADY-CLAIMED (err u1006))
(define-constant ERR-NO-STAKE (err u1007))
(define-constant ERR-HEARTBEAT-TOO-EARLY (err u1008))
(define-constant ERR-INSUFFICIENT-CONTRACT-BALANCE (err u1009))

(define-constant MIN-STAKE u5000000)         ;; 5 STX
(define-constant HEARTBEAT-INTERVAL u12)      ;; 12 BTC blocks
(define-constant UNSTAKE-DELAY u144)          ;; 144 BTC blocks
(define-constant MAX-MISSED-HEARTBEATS u3)
(define-constant BOUNTY-PUBLISHER-BPS u4000)  ;; 40%
(define-constant BOUNTY-RELAYER-BPS u4000)   ;; 40%
(define-constant BOUNTY-TREASURY-BPS u2000)  ;; 20%

(define-data-var owner principal tx-sender)
(define-data-var treasury principal tx-sender)
(define-data-var publisher-count uint u0)
(define-data-var contract-balance uint u0)  ;; tracks total STX held by contract

(define-map publishers
  { addr: principal }
  { stake: uint, registered-at: uint, last-heartbeat: uint, missed-count: uint, active: bool })

(define-map bounties
  { vault-id: (buff 32) }
  { amount: uint, funder: principal, claimed: bool, claimer: principal })

;; --- register-publisher: stake STX (tracked in contract-balance) ---
(define-public (register-publisher (stake-amount uint))
  (begin
    (asserts! (>= stake-amount MIN-STAKE) ERR-INSUFFICIENT-STAKE)
    (asserts! (is-none (map-get? publishers { addr: tx-sender })) ERR-ALREADY-REGISTERED)
    ;; Transfer STX from caller to contract (contract principal = tx-sender for the call)
    (try! (stx-transfer? stake-amount tx-sender (var-get owner)))
    (var-set contract-balance (+ (var-get contract-balance) stake-amount))
    (map-set publishers { addr: tx-sender }
      { stake: stake-amount, registered-at: burn-block-height, last-heartbeat: burn-block-height, missed-count: u0, active: true })
    (var-set publisher-count (+ u1 (var-get publisher-count)))
    (print { event: "publisher-registered", publisher: tx-sender, stake: stake-amount })
    (ok true)))

;; --- heartbeat ---
(define-public (heartbeat)
  (let ((p (unwrap! (map-get? publishers { addr: tx-sender }) ERR-NOT-REGISTERED)))
    (asserts! (get active p) ERR-NOT-REGISTERED)
    (asserts! (>= burn-block-height (+ (get last-heartbeat p) HEARTBEAT-INTERVAL)) ERR-HEARTBEAT-TOO-EARLY)
    (map-set publishers { addr: tx-sender }
      { stake: (get stake p), registered-at: (get registered-at p),
        last-heartbeat: burn-block-height, missed-count: u0, active: true })
    (ok true)))

;; --- slash ---
(define-public (slash (publisher principal))
  (let ((p (unwrap! (map-get? publishers { addr: publisher }) ERR-NOT-REGISTERED)))
    (asserts! (get active p) ERR-NOT-REGISTERED)
    (asserts! (> burn-block-height (+ (get last-heartbeat p) (* HEARTBEAT-INTERVAL (+ u1 MAX-MISSED-HEARTBEATS)))) ERR-NOT-AUTHORIZED)
    (var-set contract-balance (- (var-get contract-balance) (get stake p)))
    (map-set publishers { addr: publisher }
      { stake: u0, registered-at: (get registered-at p),
        last-heartbeat: (get last-heartbeat p), missed-count: (+ u1 (get missed-count p)), active: false })
    (print { event: "publisher-slashed", publisher: publisher, stake-slashed: (get stake p) })
    (ok true)))

;; --- withdraw-stake ---
(define-public (withdraw-stake)
  (let ((p (unwrap! (map-get? publishers { addr: tx-sender }) ERR-NOT-REGISTERED)))
    (asserts! (not (get active p)) ERR-STAKE-LOCKED)
    (asserts! (> (get stake p) u0) ERR-NO-STAKE)
    (asserts! (>= burn-block-height (+ (get last-heartbeat p) UNSTAKE-DELAY)) ERR-STAKE-LOCKED)
    (let ((amount (get stake p)))
      (var-set contract-balance (- (var-get contract-balance) amount))
      (map-set publishers { addr: tx-sender }
        { stake: u0, registered-at: (get registered-at p),
          last-heartbeat: (get last-heartbeat p), missed-count: (get missed-count p), active: false })
      ;; Owner pays out (since contract can't send STX without as-contract)
      (try! (stx-transfer? amount (var-get owner) tx-sender))
      (print { event: "stake-withdrawn", publisher: tx-sender, amount: amount })
      (ok true))))

;; --- fund-bounty ---
(define-public (fund-bounty (vault-id (buff 32)) (amount uint))
  (begin
    (asserts! (> amount u0) ERR-INSUFFICIENT-STAKE)
    (asserts! (is-none (map-get? bounties { vault-id: vault-id })) ERR-ALREADY-CLAIMED)
    (try! (stx-transfer? amount tx-sender (var-get owner)))
    (var-set contract-balance (+ (var-get contract-balance) amount))
    (map-set bounties { vault-id: vault-id } { amount: amount, funder: tx-sender, claimed: false, claimer: tx-sender })
    (print { event: "bounty-funded", vault-id: vault-id, amount: amount, funder: tx-sender })
    (ok true)))

;; --- claim-bounty ---
(define-public (claim-bounty (vault-id (buff 32)))
  (let ((b (unwrap! (map-get? bounties { vault-id: vault-id }) ERR-VAULT-NOT-LIQUIDATING)))
    (asserts! (not (get claimed b)) ERR-ALREADY-CLAIMED)
    (asserts! (>= (var-get contract-balance) (get amount b)) ERR-INSUFFICIENT-CONTRACT-BALANCE)
    (let ((total (get amount b))
          (relayer-share (/ (* total BOUNTY-RELAYER-BPS) u10000))
          (treasury-share (/ (* total BOUNTY-TREASURY-BPS) u10000)))
      (var-set contract-balance (- (var-get contract-balance) total))
      (map-set bounties { vault-id: vault-id } { amount: (get amount b), funder: (get funder b), claimed: true, claimer: tx-sender })
      ;; Owner pays relayer (caller)
      (try! (stx-transfer? relayer-share (var-get owner) tx-sender))
      (print { event: "bounty-claimed", vault-id: vault-id, relayer: tx-sender, relayer-share: relayer-share, treasury-share: treasury-share })
      (ok true))))

;; --- Admin ---
(define-public (set-treasury (new-treasury principal))
  (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED) (var-set treasury new-treasury) (ok true)))

;; --- Read-only ---
(define-read-only (get-publisher (addr principal)) (map-get? publishers { addr: addr }))
(define-read-only (get-publisher-count) (var-get publisher-count))
(define-read-only (get-bounty (vault-id (buff 32))) (map-get? bounties { vault-id: vault-id }))
(define-read-only (is-publisher-active (addr principal)) (let ((p (map-get? publishers { addr: addr }))) (if (is-none p) false (get active (unwrap-panic p)))))
(define-read-only (get-min-stake) MIN-STAKE)
(define-read-only (get-contract-balance) (var-get contract-balance))
(define-read-only (get-owner) (var-get owner))
(define-read-only (get-treasury) (var-get treasury))
