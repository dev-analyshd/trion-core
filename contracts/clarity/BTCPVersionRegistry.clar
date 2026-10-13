;; BTCPVersionRegistry.clar - §11 Fix 3: protocol-version gate
(define-constant ERR-NOT-OWNER (err u800))
(define-constant ERR-ALREADY-REGISTERED (err u801))
(define-constant ERR-VERSION-TOO-LOW (err u802))
(define-constant MIN-VERIFIER-VERSION u150)
(define-map adapter-versions { adapter: principal } { version: uint, registered: uint, active: bool })
(define-data-var owner principal tx-sender)
(define-public (register-adapter (adapter principal) (version uint)) (begin (asserts! (is-eq tx-sender (var-get owner)) ERR-NOT-OWNER) (asserts! (>= version MIN-VERIFIER-VERSION) ERR-VERSION-TOO-LOW) (asserts! (is-none (map-get? adapter-versions { adapter: adapter })) ERR-ALREADY-REGISTERED) (map-set adapter-versions { adapter: adapter } { version: version, registered: tenure-height, active: true }) (print { event: "adapter-registered", adapter: adapter, version: version }) (ok true)))
