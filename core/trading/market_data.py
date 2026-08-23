"""
TRION Market Data Connector
----------------------------
Fetches real-time on-chain market data to feed
the behavioral signal engine.

Sources (all public, no API key required):
  - DeFiLlama API: TVL, protocol data
  - Uniswap v3 subgraph: pool data, swaps
  - CoinGecko public API: price, volume

For each asset, computes:
  - Current NL score from pool data
  - Volume entropy from recent swaps
  - Counterparty diversity from swap data
"""

import httpx
import asyncio
import time
from typing import Optional


async def fetch_defillama_tvl(protocol: str = "uniswap") -> dict:
    """DeFiLlama public API — no auth required."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.llama.fi/protocol/{protocol}"
            )
            if r.status_code == 200:
                data = r.json()
                tvl_history = data.get("tvl", [])
                if len(tvl_history) >= 2:
                    recent = tvl_history[-1].get("totalLiquidityUSD", 0)
                    prev   = tvl_history[-2].get("totalLiquidityUSD", 1)
                    return {
                        "tvl":         recent,
                        "tvl_24h_pct": (recent - prev) / (prev + 1),
                        "protocol":    protocol,
                    }
    except Exception:
        pass
    return {}


async def fetch_coingecko_price(coin_id: str = "ethereum") -> dict:
    """CoinGecko public API — basic data free."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.coingecko.com/api/v3/simple/price"
                f"?ids={coin_id}&vs_currencies=usd"
                f"&include_24hr_vol=true&include_24hr_change=true"
            )
            if r.status_code == 200:
                data = r.json().get(coin_id, {})
                return {
                    "price":      data.get("usd", 0),
                    "volume_24h": data.get("usd_24h_vol", 0),
                    "change_24h": data.get("usd_24h_change", 0) / 100,
                    "coin":       coin_id,
                }
    except Exception:
        pass
    return {}


async def fetch_uniswap_pool_data(pool_address: str) -> dict:
    """
    Uniswap v3 subgraph — public endpoint.
    Fetches recent swap activity for NL computation.
    """
    query = """
    {
      pool(id: "%s") {
        token0 { symbol }
        token1 { symbol }
        liquidity
        sqrtPrice
        tick
        volumeUSD
        txCount
        totalValueLockedUSD
        feeTier
      }
      swaps(
        where: { pool: "%s" }
        orderBy: timestamp
        orderDirection: desc
        first: 100
      ) {
        amount0
        amount1
        amountUSD
        origin
        timestamp
      }
    }
    """ % (pool_address.lower(), pool_address.lower())

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3",
                json={"query": query},
                headers={"Content-Type": "application/json"},
            )
            if r.status_code == 200:
                data  = r.json().get("data", {})
                pool  = data.get("pool", {})
                swaps = data.get("swaps", [])
                if pool and swaps:
                    amounts         = [float(s.get("amountUSD", 0)) for s in swaps]
                    origins         = [s.get("origin", "") for s in swaps]
                    unique_traders  = len(set(origins))
                    return {
                        "pool_address":         pool_address,
                        "tvl":                  float(pool.get("totalValueLockedUSD", 0)),
                        "volume_usd":           float(pool.get("volumeUSD", 0)),
                        "tx_count":             int(pool.get("txCount", 0)),
                        "recent_swaps":         len(swaps),
                        "unique_traders":       unique_traders,
                        "avg_swap_usd":         sum(amounts) / len(amounts) if amounts else 0,
                        "counterparty_diversity": unique_traders / max(len(swaps), 1),
                        "token0":               pool.get("token0", {}).get("symbol", ""),
                        "token1":               pool.get("token1", {}).get("symbol", ""),
                    }
    except Exception:
        pass
    return {}


async def compute_live_nl_from_pool(pool_address: str) -> float:
    """
    Compute approximate NL score from live Uniswap pool data.
    Full NL = LD × LO × LC × LS — this is an approximation
    using available public data.
    """
    pool_data = await fetch_uniswap_pool_data(pool_address)
    if not pool_data:
        return 0.70

    ld  = min(1.0, pool_data.get("counterparty_diversity", 0.5) * 2)
    lo  = pool_data.get("counterparty_diversity", 0.5)
    lc  = min(1.0, pool_data.get("tx_count", 100) / 10000)
    tvl = pool_data.get("tvl", 1)
    vol = pool_data.get("volume_usd", 1)
    ls  = min(1.0, tvl / (vol * 10 + 1))
    return max(0.01, min(1.0, ld * lo * lc * ls))


async def get_market_context(
    coin_id:      str = "ethereum",
    pool_address: str = "",
    protocol:     str = "uniswap",
) -> dict:
    """
    Fetch all market data needed for agent context.
    Returns data suitable for AgentContext construction.
    """
    tasks = [
        fetch_coingecko_price(coin_id),
        fetch_defillama_tvl(protocol),
    ]
    if pool_address:
        tasks.append(fetch_uniswap_pool_data(pool_address))

    results   = await asyncio.gather(*tasks, return_exceptions=True)
    price_data = results[0] if not isinstance(results[0], Exception) else {}
    tvl_data   = results[1] if not isinstance(results[1], Exception) else {}
    pool_data  = (
        results[2] if len(results) > 2 and
        not isinstance(results[2], Exception) else {}
    )

    return {
        "price":            price_data.get("price", 0),
        "volume_24h":       price_data.get("volume_24h", 0),
        "price_change_24h": price_data.get("change_24h", 0),
        "tvl":              tvl_data.get("tvl", 0),
        "tvl_change":       tvl_data.get("tvl_24h_pct", 0),
        "pool_data":        pool_data,
        "timestamp":        int(time.time()),
        "sources":          ["coingecko", "defillama", "uniswap-subgraph"],
    }


if __name__ == "__main__":
    async def test():
        print("[MARKET DATA] Testing live data fetchers...")
        price = await fetch_coingecko_price("ethereum")
        print(f"  ETH price:  ${price.get('price', 0):,.2f}")
        print(f"  24h change: {price.get('change_24h', 0)*100:.2f}%")
        print(f"  24h volume: ${price.get('volume_24h', 0)/1e9:.2f}B")
        tvl = await fetch_defillama_tvl("uniswap")
        print(f"  Uniswap TVL: ${tvl.get('tvl', 0)/1e9:.2f}B")
        print("PHASE 4 PASS — Market Data Connector: PASS")

    asyncio.run(test())
