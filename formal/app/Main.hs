-- TRION formal-verification executable entry.
-- Audit fix (TEST-2 companion): the original package.yaml declared the
-- executable's main-is as src/TRION/Theorems.hs — a file declaring
-- `module TRION.Theorems where`, which cabal rejects (main-is requires
-- module Main). Only `runghc` ever executed it. This wrapper makes
-- `cabal run trion-verify` equivalent to the CI's runghc invocation.

module Main (main) where

import qualified TRION.Theorems as T (main)

main :: IO ()
main = T.main
