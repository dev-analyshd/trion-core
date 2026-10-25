import Lake
open Lake DSL

package trion_proofs where
  leanOptions := #[]

lean_lib TrionProofs where
  srcDir := "."

lean_exe trion_check where
  srcDir := "."
  root := `check
