"""
TRION Trading Signal Tests
"""
import sys
import numpy as np
import pytest
sys.path.insert(0, '.')


def test_pattern_archetypes_complete():
    from core.trading.pattern_archetypes import ARCHETYPES, match_archetype, TradingSignal
    assert len(ARCHETYPES) == 8
    for a in ARCHETYPES:
        assert len(a.phi_vector) == 9
        assert all(0 <= v <= 1 for v in a.phi_vector)
        assert 0 < a.confidence <= 1
        assert a.signal in list(TradingSignal)


def test_accumulation_detection():
    from core.trading.pattern_archetypes import match_archetype, TradingSignal
    vec = np.array([0.82, 0.90, 0.85, 0.75, 0.22, 0.70, 0.80, 0.62, 0.91])
    result = match_archetype(vec, coherence=0.65, akashic_depth=500)
    assert result['signal'] == TradingSignal.ACCUMULATION.name


def test_reversal_short_detection():
    from core.trading.pattern_archetypes import match_archetype, TradingSignal
    vec = np.array([0.50, 0.35, 0.30, 0.45, 0.15, 0.40, 0.35, 0.30, 0.25])
    result = match_archetype(vec, coherence=0.50, akashic_depth=400)
    assert result['signal'] in [
        TradingSignal.REVERSAL_SHORT.name,
        TradingSignal.STRONG_SELL.name,
        TradingSignal.DISTRIBUTION.name,
    ]


def test_signal_engine_silence():
    from core.trading.signal_engine import TradingSignalEngine
    engine = TradingSignalEngine()
    phi = np.array([0.5] * 9)
    sig = engine.generate_signal(
        "0xTEST", phi,
        coherence=0.40, threshold=0.58,
        akashic_depth=100,
    )
    assert sig['signal'] == 'SILENCE'
    assert not sig['tradeable']


def test_signal_engine_manipulation_block():
    from core.trading.signal_engine import TradingSignalEngine
    engine = TradingSignalEngine()
    phi = np.array([0.82, 0.90, 0.85, 0.75, 0.22, 0.70, 0.80, 0.62, 0.91])
    sig = engine.generate_signal(
        "0xATTACKER", phi,
        coherence=0.72, threshold=0.58,
        akashic_depth=500,
        mf_score=0.95,
    )
    assert sig['signal'] == 'MANIPULATION_ALERT'
    assert not sig['tradeable']


def test_agent_decision_long():
    from core.trading.signal_engine import TradingSignalEngine
    from core.trading.agent_interface import TRIONAgent, AgentContext
    engine = TradingSignalEngine()
    agent  = TRIONAgent(min_confidence=0.35)

    accum_phi = np.array([0.82, 0.90, 0.85, 0.76, 0.22, 0.71, 0.80, 0.61, 0.91])
    trion_sig = engine.generate_signal(
        "0xWHALE", accum_phi,
        coherence=0.72, threshold=0.58,
        akashic_depth=800,
        nl_score=0.75, mf_score=0.02,
    )
    context = AgentContext(
        market_price=2450, volume_24h=5e7,
        price_change_24h=0.03, rsi_14=55,
        volume_sma_ratio=1.8, spread_bps=3,
    )
    decision = agent.decide(trion_sig, context)
    assert decision['action'] in ['LONG', 'STRONG_LONG']
    assert decision['size_pct'] > 0
    assert decision['agreement'] >= 0


def test_agent_decision_wait_on_silence():
    from core.trading.signal_engine import TradingSignalEngine
    from core.trading.agent_interface import TRIONAgent, AgentContext
    engine = TradingSignalEngine()
    agent  = TRIONAgent()

    phi = np.array([0.5] * 9)
    silence_sig = engine.generate_signal(
        "0xSILENCE", phi,
        coherence=0.40, threshold=0.58,
        akashic_depth=50,
    )
    context = AgentContext(
        market_price=2400, volume_24h=1e7,
        price_change_24h=0.01, rsi_14=50,
        volume_sma_ratio=1.0, spread_bps=5,
    )
    decision = agent.decide(silence_sig, context)
    assert decision['action'] == 'WAIT'
    assert decision['size_pct'] == 0.0


def test_agent_vector_alignment():
    from core.trading.agent_interface import AgentContext
    bull_ctx = AgentContext(
        market_price=3000, volume_24h=1e8,
        price_change_24h=0.08,
        rsi_14=65, volume_sma_ratio=2.5, spread_bps=2,
    )
    bear_ctx = AgentContext(
        market_price=1800, volume_24h=2e8,
        price_change_24h=-0.08,
        rsi_14=28, volume_sma_ratio=3.0, spread_bps=15,
    )
    bull_vec = bull_ctx.to_faiss_vector()
    bear_vec = bear_ctx.to_faiss_vector()
    assert bull_vec[4] != bear_vec[4]
    assert all(0 <= v <= 1 for v in bull_vec)
    assert all(0 <= v <= 1 for v in bear_vec)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
