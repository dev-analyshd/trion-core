/// BTCP Zero-Bridge Escrow — Move VM implementation (Aptos / Sui)
/// =================================================================
/// Two-state atomic escrow: HOLDING -> RELEASED | REVERTED.
///
/// Whitepaper: BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes).
///   • lock_escrow     — entity locks Coin<T> resource in escrow
///   • release_escrow  — relayer + coherence proof releases to destination
///   • revert_escrow   — timeout / coherence-failure returns funds to locker
///   • emergency_revert — 7-day absolute escape hatch, callable by anyone
///
/// Funds stay on the source Move chain at all times. No cross-chain asset
/// movement occurs — this is the BTCP zero-bridge paradigm.
module trion::btcp_escrow {
    use std::signer;
    use std::vector;
    use aptos_framework::coin;
    use aptos_framework::timestamp;
    use aptos_framework::account;

    /// ── Escrow states ───────────────────────────────────────────────────────
    const HOLDING:            u8 = 0;
    const PENDING_AKASHIC:    u8 = 1;
    const RELEASED:           u8 = 2;
    const REVERTED:           u8 = 3;
    const EMERGENCY_REVERTED: u8 = 4;

    /// 7-day absolute escape hatch (Gap 8)
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
    /// 24h PENDING_AKASHIC recovery window (E1)
    const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;

    /// ── Errors ──────────────────────────────────────────────────────────────
    const E_NOT_FOUND:              u64 = 1;
    const E_INVALID_STATE:         u64 = 2;
    const E_COHERENCE_FAIL:        u64 = 3;
    const E_ZERO_AMOUNT:           u64 = 4;
    const E_EMERGENCY_NOT_YET:      u64 = 5;
    const E_AKASHIC_WINDOW_EXPIRED: u64 = 6;
    const E_NOT_RELAYER:            u64 = 7;

    /// ── Escrow resource — held under the escrow's own signer account ────────
    struct Escrow has key {
        route_id:             vector<u8>,
        entity_id:            vector<u8>,
        destination:           address,
        amount:                u64,
        min_coherence:        u64,        // x1e6
        lock_timestamp:       u64,
        timeout_seconds:      u64,
        state:                u8,
        coherence_verified:   bool,
        locked_by:             address,
        relayer:              address,
        // The Coin resource is stored alongside the metadata so that value
        // never leaves the escrow resource until release/revert.
        held_coin:            coin::Coin<TrionToken>,
    }

    /// Placeholder phantom coin type for TRION token (declared elsewhere in
    /// the live system; reproduced here so this module is self-contained).
    struct TrionToken {}

    /// Resource marking the relayer authority. Held under the contract owner.
    struct RelayerAuthority has key {
        relayer: address,
    }

    /// ── Module init ─────────────────────────────────────────────────────────
    public fun initialize(relayer: &signer) {
        move_to(relayer, RelayerAuthority { relayer: signer::address_of(relayer) });
    }

    fun assert_relayer(account: &signer) acquires RelayerAuthority {
        let addr = signer::address_of(account);
        assert!(
            exists<RelayerAuthority>(@trion),
            E_NOT_RELAYER
        );
        let auth = borrow_global<RelayerAuthority>(@trion);
        assert!(auth.relayer == addr, E_NOT_RELAYER);
    }

    /// ── Lock assets in escrow ──────────────────────────────────────────────
    /// Caller (the entity) provides the Coin<T> to lock, the route_id, the
    /// destination address, the min_coherence threshold and the timeout.
    public entry fun lock_escrow(
        admin: &signer,
        route_id: vector<u8>,
        entity_id: vector<u8>,
        destination: address,
        amount: u64,
        min_coherence: u64,
        timeout_seconds: u64,
        to_lock: coin::Coin<TrionToken>,
    ) {
        let addr = signer::address_of(admin);
        assert!(!exists<Escrow>(addr), E_INVALID_STATE);
        assert!(amount > 0, E_ZERO_AMOUNT);
        assert!(coin::value(&to_lock) == amount, E_ZERO_AMOUNT);

        move_to(admin, Escrow {
            route_id,
            entity_id,
            destination,
            amount,
            min_coherence,
            lock_timestamp: timestamp::now_seconds(),
            timeout_seconds,
            state: HOLDING,
            coherence_verified: false,
            locked_by: addr,
            relayer: @trion,
            held_coin: to_lock,
        });
    }

    /// ── Release escrow (requires coherence verification) ───────────────────
    /// Transfers the held Coin to the destination. Caller must be the
    /// registered relayer and coherence must already be verified.
    public entry fun release_escrow(
        relayer: &signer,
        escrow_addr: address,
    ) acquires Escrow, RelayerAuthority {
        assert_relayer(relayer);
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(
            esc.state == HOLDING || esc.state == PENDING_AKASHIC,
            E_INVALID_STATE
        );
        assert!(esc.coherence_verified, E_COHERENCE_FAIL);

        // Extract the coin and deposit it into the destination account.
        let coin_to_send = coin::extract_all(&mut esc.held_coin);
        coin::deposit<TrionToken>(esc.destination, coin_to_send);

        esc.state = RELEASED;
    }

    /// ── Revert escrow ──────────────────────────────────────────────────────
    /// Returns funds to locked_by. Caller can be:
    ///   - anyone, if the escrow has timed out (escape hatch)
    ///   - the relayer, for coherence failure / route invalid / manual
    public entry fun revert_escrow(
        caller: &signer,
        escrow_addr: address,
    ) acquires Escrow, RelayerAuthority {
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(
            esc.state == HOLDING || esc.state == PENDING_AKASHIC,
            E_INVALID_STATE
        );

        let now_ts = timestamp::now_seconds();
        let is_timeout = now_ts > esc.lock_timestamp + esc.timeout_seconds;
        let is_akashic_expired = esc.state == PENDING_AKASHIC
            && now_ts > esc.lock_timestamp + AKASHIC_RECOVERY_SECONDS;

        if (!is_timeout && !is_akashic_expired) {
            // Non-timeout: caller must be the relayer
            assert_relayer(caller);
        }

        // Refund the held coin to locked_by
        let coin_to_refund = coin::extract_all(&mut esc.held_coin);
        coin::deposit<TrionToken>(esc.locked_by, coin_to_refund);

        esc.state = REVERTED;
    }

    /// ── Emergency revert (7-day escape hatch) — callable by ANYONE ─────────
    /// After 7 days, anyone can trigger revert. No relayer, no coherence
    /// proof needed. This is the absolute maximum lockup period (Gap 8).
    public entry fun emergency_revert(
        _caller: &signer,
        escrow_addr: address,
    ) acquires Escrow {
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(
            esc.state == HOLDING || esc.state == PENDING_AKASHIC,
            E_INVALID_STATE
        );
        assert!(
            timestamp::now_seconds() >= esc.lock_timestamp + EMERGENCY_ESCAPE_SECONDS,
            E_EMERGENCY_NOT_YET
        );

        let coin_to_refund = coin::extract_all(&mut esc.held_coin);
        coin::deposit<TrionToken>(esc.locked_by, coin_to_refund);

        esc.state = EMERGENCY_REVERTED;
    }

    /// ── Mark coherence as verified (called by relayer after oracle check) ──
    public entry fun verify_coherence(
        relayer: &signer,
        escrow_addr: address,
    ) acquires Escrow, RelayerAuthority {
        assert_relayer(relayer);
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        esc.coherence_verified = true;
    }

    /// ── Enter PENDING_AKASHIC state (E1) ───────────────────────────────────
    /// Called by the relayer when the Akashic Index is unavailable at
    /// execution time. Opens a 24h recovery window.
    public entry fun enter_pending_akashic(
        relayer: &signer,
        escrow_addr: address,
    ) acquires Escrow, RelayerAuthority {
        assert_relayer(relayer);
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(esc.state == HOLDING, E_INVALID_STATE);
        esc.state = PENDING_AKASHIC;
    }

    /// ── View functions ──────────────────────────────────────────────────────
    public fun get_state(addr: address): (u8, u64, bool) acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global<Escrow>(addr);
        (esc.state, esc.amount, esc.coherence_verified)
    }

    public fun get_destination(addr: address): address acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        borrow_global<Escrow>(addr).destination
    }

    public fun get_lock_timestamp(addr: address): u64 acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        borrow_global<Escrow>(addr).lock_timestamp
    }
}
