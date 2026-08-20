"""
Module appended into adapters/__init__.py — adds execute_swap / execute_transfer
/ execute_liquidity methods to every VM adapter (EVM, SVM, Cosmos, Move,
CosmWasm, OOA), plus shared RPC + ExecutionResult infrastructure.

Injected by FIX-2 (vm-chain-implementer) to close AUDIT-1 gap #3.
"""
