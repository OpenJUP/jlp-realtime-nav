import asyncio
import time
from typing import Dict, Tuple

import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solders.pubkey import Pubkey

from jlp.accounts import Pool, Custody

# ----------------------------
# Chain constants & endpoints
# ----------------------------
USD_DECIMALS = 6
JLP_TOKEN_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
POOL_PUBKEY = "5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq"
RPC_ENDPOINT = "https://api.mainnet-beta.solana.com"

# Custody mapping (symbol -> pubkey)
# Use 'WBTC' label to match your MySQL/legacy naming; we price it with BTC/USD from Kraken.
CUSTODIES: Tuple[Tuple[str, str], ...] = (
    ("SOL",  "7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz"),
    ("WBTC", "5Pv3gM9JrFFH883SWAhvJC9RPYmo8UNxuFtv5bMMALkm"),
    ("ETH",  "AQCGyheWPLeo6Qp9WpYS9m3Qj479t7R636N9ey1rEjEn"),
    ("USDC", "G18jKKXQwBbrHeiK3C9MRXhkHsLHf7XgCSisykV46EZa"),
    ("USDT", "4vkNeXiYEUizLdrpdPS1eC2mccyM4NUPRtERrk6ZETkk"),
)

VOLATILE = {"SOL", "WBTC", "ETH"}
STABLES = {"USDC", "USDT"}


# ----------------------------
# Kraken price fetch (matches your style)
# ----------------------------
async def fetch_prices_from_kraken() -> Dict[str, float]:
    """
    Fetch current token prices using Kraken's public API.
    Mapping:
      - BTC: XXBTZUSD
      - ETH: XETHZUSD
      - SOL: SOLUSD
      - USDC: USDCUSD
      - USDT: fixed to 1
    Returns a dict with keys: BTC, ETH, SOL, USDC, USDT
    """
    kraken_mapping = {
        "BTC": "XXBTZUSD",
        "ETH": "XETHZUSD",
        "SOL": "SOLUSD",
        "USDC": "USDCUSD",
        "USDT": None,  # USDT pegged to 1
    }

    prices: Dict[str, float] = {"USDT": 1.0}
    pairs = [pair for pair in kraken_mapping.values() if pair is not None]
    url = "https://api.kraken.com/0/public/Ticker?pair=" + ",".join(pairs)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    # Populate zeros for non-USDT on error
                    for token, pair in kraken_mapping.items():
                        if pair is not None:
                            prices[token] = 0.0
                    return prices

                data = await resp.json()
                if data.get("error"):
                    for token, pair in kraken_mapping.items():
                        if pair is not None:
                            prices[token] = 0.0
                    return prices

                result = data.get("result", {})
                for token, pair in kraken_mapping.items():
                    if pair is None:
                        continue
                    if pair in result and "c" in result[pair]:
                        # "c": [last_trade_price, lot_volume]
                        prices[token] = float(result[pair]["c"][0])
                    else:
                        prices[token] = 0.0

        except Exception:
            # Network or parse error → zeros (except USDT=1)
            for token, pair in kraken_mapping.items():
                if pair is not None:
                    prices[token] = 0.0

    return prices


# ----------------------------
# Helpers
# ----------------------------
def scale(val, decimals) -> float:
    return float(val) / float(10 ** decimals)


def safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    return a / b if b else fallback


# ----------------------------
# On-chain fetch
# ----------------------------
async def fetch_chain_state():
    client = AsyncClient(RPC_ENDPOINT)

    try:
        # JLP supply
        supply_resp = await client.get_token_supply(Pubkey.from_string(JLP_TOKEN_MINT))
        supply = float(supply_resp.value.ui_amount)  # human units

        # Pool
        pool = await Pool.fetch(client, Pubkey.from_string(POOL_PUBKEY))
        ts_ns = time.time_ns()

        pool_aum_usd = scale(pool.aum_usd, USD_DECIMALS)
        pool_limit_usd = scale(pool.limit.max_aum_usd, USD_DECIMALS)
        pool_apr_bps = float(pool.pool_apr.fee_apr_bps)
        pool_realized_fee_usd = scale(pool.pool_apr.realized_fee_usd, USD_DECIMALS)
        theo_price = safe_div(pool_aum_usd, supply, 0.0)

        # Custodies
        pubkeys = [Pubkey.from_string(pk) for _, pk in CUSTODIES]
        custody_accs = await Custody.fetch_multiple(client, pubkeys, commitment=Processed)

        return {
            "timestamp_ns": ts_ns,
            "supply": supply,
            "pool": {
                "aum_usd": pool_aum_usd,
                "limit_usd": pool_limit_usd,
                "apr_bps": pool_apr_bps,
                "realized_fee_usd": pool_realized_fee_usd,
                "theo_price": theo_price,
            },
            "custodies": {sym: acc for (sym, _), acc in zip(CUSTODIES, custody_accs)},
        }

    finally:
        await client.close()


# ----------------------------
# NAV calc (PHP parity + USDC add-back)
# ----------------------------
def compute_nav(state: Dict, kraken_prices: Dict[str, float]) -> Dict:
    """
    NAV using real spot prices from Kraken:
      - For WBTC we use BTC/USD price.
      - longPnL = (spot - avg_locked_price) * locked
      - shortPnL = (short_qty * spot) - short_notional
      - value = owned*spot - longPnL + shortPnL   (volatile)
      - stables = owned * 1
      - USDC: add (debt + accrued_interest)/1e15 back at $1
    """
    supply = state["supply"]
    custodies: Dict[str, Custody] = state["custodies"]

    # Map custody symbol -> spot price using Kraken output
    # WBTC uses BTC price from Kraken
    spot: Dict[str, float] = {
        "SOL": kraken_prices.get("SOL", 0.0),
        "WBTC": kraken_prices.get("BTC", 0.0),
        "ETH": kraken_prices.get("ETH", 0.0),
        "USDC": kraken_prices.get("USDC", 1.0),
        "USDT": kraken_prices.get("USDT", 1.0),
    }

    total_value_usd = 0.0
    long_pnl_total = 0.0
    short_pnl_total = 0.0
    fees_total_usd = 0.0

    rows = []

    for symbol, custody in custodies.items():
        dec = int(custody.decimals)

        owned = scale(custody.assets.owned, dec)
        locked = scale(custody.assets.locked, dec)

        guaranteed_usd = scale(custody.assets.guaranteed_usd, USD_DECIMALS)
        short_sizes_usd = scale(custody.assets.global_short_sizes, USD_DECIMALS)
        short_avg_price_usd = scale(custody.assets.global_short_average_prices, USD_DECIMALS)

        fees_reserves_tokens = scale(custody.assets.fees_reserves, dec)

        s = spot.get(symbol, 0.0)
        # If Kraken returned 0 (temporary issue), fall back to ratio for volatile tokens only
        if symbol in VOLATILE and s <= 0.0:
            s = safe_div(guaranteed_usd, locked, 1.0)

        if symbol in VOLATILE:
            avg_locked_price = safe_div(guaranteed_usd, locked, 0.0)
            long_pnl = (s - avg_locked_price) * locked

            short_qty = safe_div(short_sizes_usd, short_avg_price_usd, 0.0)
            short_pnl = (short_qty * s) - short_sizes_usd

            value_usd = (owned * s) - long_pnl + short_pnl

            long_pnl_total += long_pnl
            short_pnl_total += short_pnl

        elif symbol in STABLES:
            # mark stables at $1
            value_usd = owned * 1.0
            if symbol == "USDC":
                # Add debt + accrued interest back (convert from 1e15 fixed-point to tokens)
                debt_tokens = 0.0
                accrued_tokens = 0.0
                try:
                    debt_tokens = float(getattr(custody, "debt", 0) or 0) / 1e15
                except Exception:
                    pass
                try:
                    accrued_tokens = float(getattr(custody, "borrow_lend_interests_accured", 0) or 0) / 1e15
                except Exception:
                    pass
                value_usd += (debt_tokens + accrued_tokens)  # $1 each

        else:
            # Unknowns treated conservatively at $1
            value_usd = owned * 1.0

        # Fees reserves valued at current spot
        fees_total_usd += fees_reserves_tokens * (1.0 if symbol in STABLES else s)
        total_value_usd += value_usd

        rows.append({
            "token": symbol,
            "owned": owned,
            "locked": locked,
            "spot": s,
            "avg_locked_price": safe_div(guaranteed_usd, locked, 0.0),
            "guaranteed_usd": guaranteed_usd,
            "short_sizes_usd": short_sizes_usd,
            "short_avg_price_usd": short_avg_price_usd,
            "value_usd": value_usd,
        })

    jlp_price_nav = safe_div(total_value_usd, supply, 0.0)

    return {
        "per_token": rows,
        "totals": {
            "aum_nav_usd": total_value_usd,
            "fees_total_usd": fees_total_usd,
            "long_pnl_total_usd": long_pnl_total,
            "short_pnl_total_usd": short_pnl_total,
            "supply": supply,
            "jlp_price_nav": jlp_price_nav,
        }
    }


def print_report(state: Dict, nav: Dict, spot_used: Dict[str, float]):
    pool = state["pool"]
    ts = state["timestamp_ns"]

    print("\n=== Pool Info ===")
    print(f"Timestamp (ns): {ts}")
    print(f"Pool AUM (program):    ${pool['aum_usd']:.2f}")
    print(f"Pool Limit (USD):      ${pool['limit_usd']:.2f}")
    print(f"Fee APR (bps):         {pool['apr_bps']:.0f}")
    print(f"Realized Fee (USD):    ${pool['realized_fee_usd']:.2f}")
    print(f"Theoretical JLP Price: ${pool['theo_price']:.6f}")

    print("\nSpot (Kraken) used: " + ", ".join(f"{k}={v}" for k, v in spot_used.items()))

    print("\n=== Custody Breakdown (NAV calc) ===")
    for r in nav["per_token"]:
        print(
            f"{r['token']:>4} | owned={r['owned']:.6f} "
            f"locked={r['locked']:.6f} "
            f"spot=${r['spot']:.6f} "
            f"avg_locked=${r['avg_locked_price']:.6f} "
            f"guaranteed_usd=${r['guaranteed_usd']:.2f} "
            f"short_sizes_usd=${r['short_sizes_usd']:.2f} "
            f"short_avg_price=${r['short_avg_price_usd']:.6f} "
            f"-> value=${r['value_usd']:.2f}"
        )

    t = nav["totals"]
    print("\n=== Totals (PHP-style NAV + USDC debt add-back) ===")
    print(f"AUM (NAV calc):        ${t['aum_nav_usd']:.2f}")
    print(f"Fees total (est USD):  ${t['fees_total_usd']:.2f}")
    print(f"Long PnL total:        ${t['long_pnl_total_usd']:.2f}")
    print(f"Short PnL total:       ${t['short_pnl_total_usd']:.2f}")
    print(f"Supply:                {t['supply']:.6f}")
    print(f"JLP Price (NAV):       ${t['jlp_price_nav']:.6f}")
    print(f"Pool Theoretical:      ${pool['theo_price']:.6f}")
    gap_usd = (t['jlp_price_nav'] - pool['theo_price']) * t['supply']
    print(f"Total - Theo gap USD:  ${gap_usd:.2f}")


# ----------------------------
# main
# ----------------------------
async def main():
    # 1) Fetch Kraken prices
    k = await fetch_prices_from_kraken()

    # 2) Fetch chain state
    state = await fetch_chain_state()

    # 3) Compute NAV with those prices
    nav = compute_nav(state, k)

    # 4) Report
    # Expose the exact spot set used for clarity, including WBTC->BTC mapping
    spot_used = {
        "SOL": k.get("SOL", 0.0),
        "WBTC(BTC)": k.get("BTC", 0.0),
        "ETH": k.get("ETH", 0.0),
        "USDC": k.get("USDC", 1.0),
        "USDT": k.get("USDT", 1.0),
    }
    print_report(state, nav, spot_used)


if __name__ == "__main__":
    asyncio.run(main())
