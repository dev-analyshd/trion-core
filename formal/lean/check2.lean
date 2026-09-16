-- Find the right lemma
#check @Nat.add_lt_add_right
-- add_lt_add_right : n < m → n + k < m + k
-- So we need 0 < rest → 0 + t*rest < rest + t*rest
-- Hmm, not quite.

-- Actually we want: t*rest < t*rest + rest when rest > 0
-- This is: a < a + b when b > 0
-- In Lean: Nat.lt_add_self or Nat.add_lt_add_left
#check @Nat.add_lt_add_left
-- add_lt_add_left : n < m → k + n < k + m
-- So 0 < rest → t*rest + 0 < t*rest + rest → t*rest < t*rest + rest

-- Actually simpler: just use Nat.lt_of_lt_of_le or direct omega after rewriting
