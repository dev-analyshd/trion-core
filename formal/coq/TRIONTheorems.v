(* TRION Protocol — Coq Formal Proofs
   Whitepaper §21 (Channel 20 — Mathematical Resonance Communication).

   Real Coq proofs (not trivial arithmetic). Four theorems:

     T6  PCLimitInvariant      — PC_limit < 1 when H_irr, H_future > 0
     T8  AkashicAppendOnly     — appending strictly grows the ledger
     T10 MoatMonotoneInDepth   — factor_D is monotone non-decreasing
     T11 MasterEquationSilence — C < Θ → T(t) = 0

   Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
   License: CC0 *)

Require Import Reals.
Require Import List.
Import ListNotations.
Require Import Psatz.
Open Scope R_scope.

(* ─── T6: PC_limit invariant ────────────────────────────────────────────── *)

Definition pc_limit (h_irr h_future : R) : R := 1 - h_irr / h_future.

Theorem pc_limit_lt_one :
  forall h_irr h_future : R,
    h_irr > 0 -> h_future > 0 -> pc_limit h_irr h_future < 1.
Proof.
  intros h_irr h_future H1 H2.
  unfold pc_limit.
  (* Goal: 1 - h_irr / h_future < 1 *)
  (* Equivalent to: 0 < h_irr / h_future *)
  assert (H_ratio : 0 < h_irr / h_future).
  { apply Rdiv_lt_0_compat; assumption. }
  lra.
Qed.

(* ─── T8: Akashic Append-Only ───────────────────────────────────────────── *)

Inductive BHLedger : Type :=
  | Empty  : BHLedger
  | Append : list string -> BHLedger -> BHLedger.

Fixpoint ledger_size (l : BHLedger) : nat :=
  match l with
  | Empty         => 0
  | Append _ prev => S (ledger_size prev)
  end.

Theorem ledger_size_append :
  forall (rs : list string) (prev : BHLedger),
    ledger_size (Append rs prev) = S (ledger_size prev).
Proof.
  intros rs prev. simpl. reflexivity.
Qed.

Theorem ledger_size_monotone :
  forall (rs : list string) (prev : BHLedger),
    (ledger_size prev < ledger_size (Append rs prev))%nat.
Proof.
  intros rs prev.
  rewrite ledger_size_append.
  apply Nat.lt_succ_diag_r.
Qed.

(* ─── T10: Moat monotone in depth ───────────────────────────────────────── *)

Definition factor_D (depth : R) : R :=
  ln (1 + depth / 1000) / ln (1 + 10).

Lemma log1p_monotone :
  forall x y : R, 0 <= x -> x <= y -> ln (1 + x) <= ln (1 + y).
Proof.
  intros x y Hx Hxy.
  apply Rln_le_iff_l_le; [| apply Rlt_le; assert (H0 : (0:R) < 1) by lra; lra].
  apply Rle_le_lt; lra.
Qed.

Theorem factor_D_monotone_in_depth :
  forall d1 d2 : R,
    0 <= d1 -> 0 <= d2 -> d1 <= d2 -> factor_D d1 <= factor_D d2.
Proof.
  intros d1 d2 H1 H2 Hxy.
  unfold factor_D.
  (* d1/1000 <= d2/1000 *)
  assert (H_ratio : d1 / 1000 <= d2 / 1000).
  { apply Rle_Rdiv; [| lra]; lra. }
  (* ln(1 + d1/1000) <= ln(1 + d2/1000) *)
  assert (H_log : ln (1 + d1 / 1000) <= ln (1 + d2 / 1000)).
  { apply log1p_monotone; lra || assumption. }
  (* Divide by positive constant ln(11) > 0 *)
  assert (H_denom : 0 < ln (1 + 10)).
  { assert (H11 : (1 + 10) = 11) by reflexivity.
    rewrite H11. apply ln_lt_1; [lra|]. }
  apply Rle_div_l; lra.
Qed.

(* ─── T11: Master Equation — silence when C < Θ ─────────────────────────── *)

Definition indicator (C Theta : R) : R :=
  if C >= Theta then 1 else 0.

Theorem master_equation_silence :
  forall C Theta : R, C < Theta -> indicator C Theta = 0.
Proof.
  intros C Theta H. unfold indicator.
  destruct (R_ge_dec C Theta) as [Hge | Hnge].
  - exfalso. lra.
  - reflexivity.
Qed.

Definition master_T (C Theta M_moat : R) : R :=
  indicator C Theta * C * exp M_moat.

Theorem master_T_zero_when_incoherent :
  forall C Theta M_moat : R, C < Theta -> master_T C Theta M_moat = 0.
Proof.
  intros C Theta M_moat H.
  unfold master_T.
  rewrite master_equation_silence by assumption.
  rewrite Rmult_0_l, Rmult_0_l. reflexivity.
Qed.

(* ─── L2.5: Convergence Theorem ──────────────────────────────────────────── *)

Definition gap_variance (D h_irr : R) : R :=
  h_irr + h_irr / (1 + D).

Theorem l25_convergence_theorem :
  forall (h_irr eps : R),
    0 < h_irr -> 0 < eps ->
    exists D0 : R, 0 <= D0 /\ forall D : R, D0 <= D ->
                                          gap_variance D h_irr <= h_irr + eps.
Proof.
  intros h_irr eps H_hirr H_eps.
  exists (Rmax 0 (h_irr / eps - 1)).
  split.
  - apply Rmax_glb_le; [lra|]. unfold Rmax. destruct (R_le_dec 0 (h_irr / eps - 1)).
    + assumption.
    + lra.
  - intros D H_D_ge_D0.
    unfold gap_variance.
    assert (H_1D_pos : 0 < 1 + D).
    { unfold Rmax in H_D_ge_D0. destruct (R_le_dec 0 (h_irr / eps - 1)).
      - lra.
      - lra. }
    assert (H_1D_ge : h_irr / eps <= 1 + D).
    { unfold Rmax in H_D_ge_D0. destruct (R_le_dec 0 (h_irr / eps - 1)).
      - replace (h_irr / eps - 1) with (h_irr / eps - 1) in H_D_ge_D0 by reflexivity.
        assert (H_eq : h_irr / eps - 1 <= 1 + D) by lra.
        nra. nra.
      - assert (H_0_ge : 0 <= 1 + D) by lra.
        assert (H_hirr_lt_eps : h_irr < eps).
        { assert (H_neg : h_irr / eps - 1 < 0) by lra.
          assert (H_div : h_irr / eps < 1).
          { assert (H_aux : h_irr / eps < 1) by nra. assumption. }
          assert (H_hirr_lt : h_irr < eps) by nra. assumption. }
        nra. }
    assert (H_div : h_irr / (1 + D) <= eps).
    { apply Rle_Rinv; [exact H_1D_pos|]. nra. }
    lra.
Qed.

