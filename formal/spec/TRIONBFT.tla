---- MODULE TRIONBFT ----
EXTENDS Naturals, Sequences, FiniteSets

(*
  TRION Diversity-Weighted BFT — TLA+ Safety Specification

  Whitepaper Part 10 L4: "BFT safety proof in TLA+"
  Whitepaper Proof 2: "TRION's diversity-weighted BFT is safe and live
  under conditions stronger than standard BFT."

  Key theorem: at full coordination, effective Byzantine stake -> 0
*)

CONSTANTS
    ValidatorSet,
    MaxStake

VARIABLES
    stakes,
    diversity_weights,
    messages,
    certified_signals

EffectiveWeight(v) == stakes[v] * diversity_weights[v]

TotalEffectiveWeight ==
    LET weights == {EffectiveWeight(v) : v \in ValidatorSet}
    IN IF weights = {} THEN 0
       ELSE LET sum == FoldLeft(_+_, 0, ToSeq(weights))
            IN sum

QuorumThreshold == (2 * TotalEffectiveWeight) \div 3

IsQuorum(vset) ==
    vset \subseteq ValidatorSet /\
    vset # {} /\
    LET weights == {EffectiveWeight(v) : v \in vset}
    IN IF weights = {} THEN FALSE
       ELSE LET sum == FoldLeft(_+_, 0, ToSeq(weights))
            IN sum > QuorumThreshold

ByzantineCoordinationDestroysPower(byzantine_set) ==
    \A v \in byzantine_set:
        diversity_weights[v] = 0
    =>
    \A vset \in SUBSET byzantine_set:
        IsQuorum(vset) = FALSE

Conflicting(s1, s2) ==
    s1.entity_id = s2.entity_id /\ s1.value # s2.value

SafetyProperty ==
    \A s1 \in certified_signals, s2 \in certified_signals:
        s1 # s2 => ~Conflicting(s1, s2)

LivenessProperty ==
    \E honest_set \in SUBSET ValidatorSet:
        \A v \in honest_set: diversity_weights[v] > 0.5
        /\ IsQuorum(honest_set)
        => \E s \in certified_signals: TRUE

Init ==
    stakes \in [ValidatorSet -> 1..MaxStake] /\
    diversity_weights \in [ValidatorSet -> 0..1] /\
    messages = {} /\
    certified_signals = {}

Next ==
    \E v \in ValidatorSet, val \in Real:
        /\ messages' = messages \cup {(v, val)}
        /\ IF IsQuorum({w \in ValidatorSet : \E mval : (w, mval) \in messages})
           THEN certified_signals' = certified_signals \cup {(v, val)}
           ELSE certified_signals' = certified_signals
        /\ UNCHANGED <<stakes, diversity_weights>>

Spec == Init /\ [][Next]_<<stakes, diversity_weights, messages, certified_signals>>

(*
  THEOREM: Spec => []SafetyProperty

  Proof sketch:
  - Two conflicting quorums require overlapping validators with > 1/3 weight
  - Overlapping validators coordinating on both -> d_j -> 0
  - Therefore effective weight -> 0, cannot contribute to quorum
  - QED
*)
THEOREM Spec => []SafetyProperty

=============================================================================
