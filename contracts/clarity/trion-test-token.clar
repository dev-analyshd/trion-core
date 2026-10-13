;; trion-test-token.clar - SIP-010 fungible test token for BTCP escrow + LiquidityOcean flows.
;; Ticker: tTRION  ·  Decimals: 6  ·  Initial supply: 1,000,000,000 tTRION (10^15 micro-tTRION).
;; Owner-mintable / burnable + rate-limited faucet-drip for test setups.

(define-fungible-token ttrion)

(define-constant ERR-NOT-AUTHORIZED (err u3001))
(define-constant ERR-AMOUNT-ZERO (err u3002))
(define-constant ERR-FAUCET-COOLDOWN (err u3003))
(define-constant FAUCET-DRIP-AMOUNT u1000)
(define-constant FAUCET-COOLDOWN-BLOCKS u6)
(define-constant INITIAL-SUPPLY u1000000000000000) ;; 10^9 * 10^6

(define-data-var owner principal tx-sender)
(define-map faucet-last-drip { caller: principal } { height: uint })

;; Mint full initial supply to deployer at deploy time.
(ft-mint? ttrion INITIAL-SUPPLY tx-sender)

;; --- SIP-010 read-only interface ---

(define-read-only (get-total-supply)
  (ft-get-supply ttrion)
)

(define-read-only (get-decimals)
  u6
)

(define-read-only (get-name)
  "TRION Test Token"
)

(define-read-only (get-symbol)
  "tTRION"
)

(define-read-only (get-token-uri)
  none
)

(define-read-only (get-balance (who principal))
  (ft-get-balance ttrion who)
)

;; --- SIP-010 transfer ---

(define-public (transfer (amount uint) (sender principal) (recipient principal) (memo (optional (buff 34))))
  (begin
    (asserts! (is-eq tx-sender sender) ERR-NOT-AUTHORIZED)
    (asserts! (> amount u0) ERR-AMOUNT-ZERO)
    (try! (ft-transfer? ttrion amount sender recipient))
    (match memo
      m (begin (print { event: "transfer-memo", sender: sender, recipient: recipient, amount: amount, memo: m }) true)
      true)
    (ok true)
  )
)

;; --- Owner-only mint / burn for test setup ---

(define-public (mint (amount uint) (to principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (asserts! (> amount u0) ERR-AMOUNT-ZERO)
    (ft-mint? ttrion amount to)
  )
)

(define-public (burn (amount uint) (from principal))
  (begin
    (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-AUTHORIZED)
    (asserts! (> amount u0) ERR-AMOUNT-ZERO)
    (ft-burn? ttrion amount from)
  )
)

;; --- Faucet: anyone can claim once per 6 burn-blocks, 1000 micro-tTRION ---

(define-public (faucet-drip)
  (let ((caller tx-sender))
    (match (map-get? faucet-last-drip { caller: caller })
      entry (asserts! (>= burn-block-height (+ (get height entry) FAUCET-COOLDOWN-BLOCKS)) ERR-FAUCET-COOLDOWN)
      true)
    (map-set faucet-last-drip { caller: caller } { height: burn-block-height })
    (try! (ft-mint? ttrion FAUCET-DRIP-AMOUNT caller))
    (print { event: "faucet-drip", to: caller, amount: FAUCET-DRIP-AMOUNT })
    (ok true)
  )
)

(define-read-only (get-owner) (var-get owner))

(define-read-only (get-faucet-last-drip (who principal))
  (map-get? faucet-last-drip { caller: who })
)
