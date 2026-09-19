---- MODULE TRIONBFT_TTrace_1789787660 ----
EXTENDS Sequences, TLCExt, Toolbox, TRIONBFT_TEConstants, TRIONBFT, Naturals, TLC

_expression ==
    LET TRIONBFT_TEExpression == INSTANCE TRIONBFT_TEExpression
    IN TRIONBFT_TEExpression!expression
----

_trace ==
    LET TRIONBFT_TETrace == INSTANCE TRIONBFT_TETrace
    IN TRIONBFT_TETrace!trace
----

_inv ==
    ~(
        TLCGet("level") = Len(_TETrace)
        /\
        stakes = ((v1 :> 100 @@ v2 :> 100 @@ v3 :> 100 @@ v4 :> 100))
        /\
        heights = ((v1 :> 1 @@ v2 :> 0 @@ v3 :> 0 @@ v4 :> 0))
        /\
        frozen = (FALSE)
        /\
        diversities = ((v1 :> 10 @@ v2 :> 10 @@ v3 :> 10 @@ v4 :> 10))
    )
----

_init ==
    /\ diversities = _TETrace[1].diversities
    /\ frozen = _TETrace[1].frozen
    /\ heights = _TETrace[1].heights
    /\ stakes = _TETrace[1].stakes
----

_next ==
    /\ \E i,j \in DOMAIN _TETrace:
        /\ \/ /\ j = i + 1
              /\ i = TLCGet("level")
        /\ diversities  = _TETrace[i].diversities
        /\ diversities' = _TETrace[j].diversities
        /\ frozen  = _TETrace[i].frozen
        /\ frozen' = _TETrace[j].frozen
        /\ heights  = _TETrace[i].heights
        /\ heights' = _TETrace[j].heights
        /\ stakes  = _TETrace[i].stakes
        /\ stakes' = _TETrace[j].stakes

\* Uncomment the ASSUME below to write the states of the error trace
\* to the given file in Json format. Note that you can pass any tuple
\* to `JsonSerialize`. For example, a sub-sequence of _TETrace.
    \* ASSUME
    \*     LET J == INSTANCE Json
    \*         IN J!JsonSerialize("TRIONBFT_TTrace_1789787660.json", _TETrace)

=============================================================================

 Note that you can extract this module `TRIONBFT_TEExpression`
  to a dedicated file to reuse `expression` (the module in the 
  dedicated `TRIONBFT_TEExpression.tla` file takes precedence 
  over the module `TRIONBFT_TEExpression` below).

---- MODULE TRIONBFT_TEExpression ----
EXTENDS Sequences, TLCExt, Toolbox, TRIONBFT_TEConstants, TRIONBFT, Naturals, TLC

expression == 
    [
        \* To hide variables of the `TRIONBFT` spec from the error trace,
        \* remove the variables below.  The trace will be written in the order
        \* of the fields of this record.
        diversities |-> diversities
        ,frozen |-> frozen
        ,heights |-> heights
        ,stakes |-> stakes
        
        \* Put additional constant-, state-, and action-level expressions here:
        \* ,_stateNumber |-> _TEPosition
        \* ,_diversitiesUnchanged |-> diversities = diversities'
        
        \* Format the `diversities` variable as Json value.
        \* ,_diversitiesJson |->
        \*     LET J == INSTANCE Json
        \*     IN J!ToJson(diversities)
        
        \* Lastly, you may build expressions over arbitrary sets of states by
        \* leveraging the _TETrace operator.  For example, this is how to
        \* count the number of times a spec variable changed up to the current
        \* state in the trace.
        \* ,_diversitiesModCount |->
        \*     LET F[s \in DOMAIN _TETrace] ==
        \*         IF s = 1 THEN 0
        \*         ELSE IF _TETrace[s].diversities # _TETrace[s-1].diversities
        \*             THEN 1 + F[s-1] ELSE F[s-1]
        \*     IN F[_TEPosition - 1]
    ]

=============================================================================



Parsing and semantic processing can take forever if the trace below is long.
 In this case, it is advised to uncomment the module below to deserialize the
 trace from a generated binary file.

\*
\*---- MODULE TRIONBFT_TETrace ----
\*EXTENDS IOUtils, TRIONBFT_TEConstants, TRIONBFT, TLC
\*
\*trace == IODeserialize("TRIONBFT_TTrace_1789787660.bin", TRUE)
\*
\*=============================================================================
\*

---- MODULE TRIONBFT_TETrace ----
EXTENDS TRIONBFT_TEConstants, TRIONBFT, TLC

trace == 
    <<
    ([stakes |-> (v1 :> 100 @@ v2 :> 100 @@ v3 :> 100 @@ v4 :> 100),heights |-> (v1 :> 0 @@ v2 :> 0 @@ v3 :> 0 @@ v4 :> 0),frozen |-> FALSE,diversities |-> (v1 :> 10 @@ v2 :> 10 @@ v3 :> 10 @@ v4 :> 10)]),
    ([stakes |-> (v1 :> 100 @@ v2 :> 100 @@ v3 :> 100 @@ v4 :> 100),heights |-> (v1 :> 1 @@ v2 :> 0 @@ v3 :> 0 @@ v4 :> 0),frozen |-> FALSE,diversities |-> (v1 :> 10 @@ v2 :> 10 @@ v3 :> 10 @@ v4 :> 10)])
    >>
----


=============================================================================

---- MODULE TRIONBFT_TEConstants ----
EXTENDS TRIONBFT

CONSTANTS v1, v2, v3, v4

=============================================================================

---- CONFIG TRIONBFT_TTrace_1789787660 ----
CONSTANTS
    ValidatorSet = { v1 , v2 , v3 , v4 }
    MaxStake = 100
    MaxDiversity = 10
    v3 = v3
    v4 = v4
    v2 = v2
    v1 = v1

INVARIANT
    _inv

CHECK_DEADLOCK
    \* CHECK_DEADLOCK off because of PROPERTY or INVARIANT above.
    FALSE

INIT
    _init

NEXT
    _next

CONSTANT
    _TETrace <- _trace

ALIAS
    _expression
=============================================================================
\* Generated on Sat Sep 19 03:14:21 UTC 2026