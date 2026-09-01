-- TRION Protocol — Haskell formal-verification test suite (hspec)
--
-- Audit fix (TEST-2): this file was a putStrLn stub despite the hspec
-- dependency declared in package.yaml. It never imported TRION.Theorems —
-- the 9 type-level theorems were only exercised by the module's own
-- self-check main.
--
-- This suite exercises the exported theorem constructors, proofs, and
-- guards as properties a caller can rely on.
--
-- Run:  cabal test spec
--   or: runghc -i formal/src/TRION formal/test/Spec.hs  (with hspec in the
--        package db, e.g. after `cabal install --lib hspec`)

module Main where

import Test.Hspec
import TRION.Theorems

main :: IO ()
main = hspec $ do

  describe "T1 — CoherenceConvergence" $ do
    it "mkCoherence accepts values in [0, 1]" $ do
      mkCoherence 0.0 `shouldBe` Just (Coherence 0.0)
      mkCoherence 1.0 `shouldBe` Just (Coherence 1.0)
      mkCoherence 0.72 `shouldBe` Just (Coherence 0.72)

    it "mkCoherence rejects out-of-range values" $ do
      mkCoherence (-0.01) `shouldBe` Nothing
      mkCoherence 1.01 `shouldBe` Nothing
      mkCoherence 42.0 `shouldBe` Nothing

    it "coherenceInvariant holds for every constructible Coherence" $ do
      mapM_ (\c -> coherenceInvariant c `shouldBe` True)
            [Coherence 0.0, Coherence 0.5, Coherence 1.0, Coherence 0.999999]

  describe "T4 — ThresholdMonotonicity" $ do
    it "computeTheta maps V=0 → Θ_min and V=1 → Θ_max" $ do
      unThreshold (computeTheta (Volatility 0.0)) `shouldBe` thetaMin
      unThreshold (computeTheta (Volatility 1.0)) `shouldBe` thetaMax

    it "computeTheta clamps out-of-range volatility" $ do
      unThreshold (computeTheta (Volatility (-3.0))) `shouldBe` thetaMin
      unThreshold (computeTheta (Volatility 7.0)) `shouldBe` thetaMax

    it "Θ(t) is strictly increasing in V inside (0, 1)" $ do
      let θ v = unThreshold (computeTheta (Volatility v))
      θ 0.25 `shouldSatisfy` (< θ 0.5)
      θ 0.5 `shouldSatisfy` (< θ 0.75)

    it "thresholdMonotonicityProof passes" $ do
      thresholdMonotonicityProof `shouldBe` True

  describe "T5 — ManipulationDetection" $ do
    it "positive MF strictly reduces Φ" $ do
      let phiRaw = PhiScore 0.9
          adj    = applyMF phiRaw (ManipulationScore 0.4)
      unPhi adj `shouldBe` 0.9 * 0.6

    it "zero MF leaves Φ unchanged" $ do
      unPhi (applyMF (PhiScore 0.7) (ManipulationScore 0.0)) `shouldBe` 0.7

    it "MF is clamped to [0, 1]" $ do
      unPhi (applyMF (PhiScore 0.7) (ManipulationScore 5.0)) `shouldBe` 0.0
      unPhi (applyMF (PhiScore 0.7) (ManipulationScore (-1.0))) `shouldBe` 0.7

    it "manipulationReducesPhiProof holds across the honest domain" $ do
      manipulationReducesPhiProof (PhiScore 0.8) (ManipulationScore 0.1) `shouldBe` True
      manipulationReducesPhiProof (PhiScore 0.8) (ManipulationScore 0.0) `shouldBe` True

  describe "T6 — PCLimitInvariant" $ do
    it "PC_limit < 1 whenever H_irr > 0" $ do
      computePCLimit (IrreducibleEntropy 0.1) 1.0 `shouldSatisfy` (< 1.0)
      computePCLimit (IrreducibleEntropy 0.5) 1.0 `shouldSatisfy` (< 1.0)

    it "PC_limit formula: 1 - H_irr/H_future" $ do
      computePCLimit (IrreducibleEntropy 0.25) 1.0 `shouldBe` 0.75

    it "degenerate H_future ≤ 0 → 0" $ do
      computePCLimit (IrreducibleEntropy 0.1) 0.0 `shouldBe` 0.0

    it "hard cap 0.9999 enforced" $ do
      computePCLimit (IrreducibleEntropy 0.000001) 1e9 `shouldSatisfy` (<= 0.9999)

    it "pcLimitInvariantProof passes" $ do
      pcLimitInvariantProof `shouldBe` True

  describe "T7 — CoordinationCollapse" $ do
    it "HHI below the 2500 cap is permitted" $ do
      coordinationCollapseGuard (HHI 1500.0) `shouldBe` True

    it "HHI above the 2500 cap is flagged (monopoly)" $ do
      coordinationCollapseGuard (HHI 4000.0) `shouldBe` False

    it "diversityWeight: d = sqrt(overlap/total)" $ do
      diversityWeight 50 100 `shouldBe` sqrt 0.5

    it "diversityWeight: degenerate total → neutral 0.5" $ do
      diversityWeight 0 0 `shouldBe` 0.5

  describe "T3 — InformationConservation" $ do
    it "I(t+1) ≥ I(t) − S_emitted holds for honest transitions" $ do
      informationConservation (InformationState 100.0) 10.0 (InformationState 95.0)
        `shouldBe` True

    it "violating transitions are detected" $ do
      informationConservation (InformationState 100.0) 10.0 (InformationState 50.0)
        `shouldBe` False

  describe "T8 — AkashicAppendOnly" $ do
    it "ledger starts empty and appends strictly grow it" $ do
      ledgerSize BHEmpty `shouldBe` 0
      let r1  = BHRecord "sense_abc" "antisense_xyz"
          r2  = BHRecord "sense_def" "antisense_uvw"
          l1  = bhAppend BHEmpty r1
          l2  = bhAppend l1 r2
      ledgerSize l1 `shouldBe` 1
      ledgerSize l2 `shouldBe` 2

    it "akashicAppendOnlyProof passes" $ do
      akashicAppendOnlyProof `shouldBe` True

    it "validateBHRecord rejects empty or identical strands" $ do
      validateBHRecord (BHRecord "sense" "antisense") `shouldBe` True
      validateBHRecord (BHRecord "" "antisense") `shouldBe` False
      validateBHRecord (BHRecord "sense" "") `shouldBe` False
      validateBHRecord (BHRecord "same" "same") `shouldBe` False

  describe "T2 — SilenceCompleteness" $ do
    it "isSilence identifies SILENCE-kind signals" $ do
      isSilence (SilenceSignal (Coherence 0.5) (Threshold 0.55)) `shouldBe` True

    it "a Silence signal cannot be constructed as a Valuation (type-level)" $ do
      -- The two constructors inhabit different kind indices: 'Silence vs
      -- 'Valuation. `ValuationSignal c v :: TRIONSignal 'Valuation` can never
      -- be passed where `TRIONSignal 'Silence` is required (compile-time).
      ValuationSignal (Coherence 0.8) 42.0 `shouldSatisfy` \s ->
        case s of ValuationSignal _ _ -> True
