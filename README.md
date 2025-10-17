# jlp-realtime-nav

Real-time JLP Net Asset Value (NAV) calculator for Solana.  
It pulls on-chain pool/custody state directly from the JLP program and marks assets to **live spot prices from Kraken**, then computes NAV per share. It also includes the latest adjustment to **add USDC debt plus accrued borrow/lend interest back to the USDC pool** for an accurate AUM/NAV.

> **Why not just read the on-chain AUM?**  
> The on-chain AUM field only updates when the pool processes a transaction. This tool recomputes AUM from each custody in real time, so it keeps tracking even when nothing’s hitting the pool.

---

## Features

- On-chain reads (pool + custodies) via `solana-py`, `solders`, and the Anchor-generated client.
- Live spot prices from **Kraken** (`XXBTZUSD`, `XETHZUSD`, `SOLUSD`, `USDCUSD`); USDT pegged to 1.
- Long/short PnL aware custody valuation:
  - `avg_locked_price = guaranteed_usd / locked`
  - `longPnL = (spot - avg_locked_price) * locked`
  - `shortPnL = (short_qty * spot) - short_notional`, with `short_qty = short_notional / short_avg_price`
  - custody value (volatile) = `owned*spot - longPnL + shortPnL`
  - custody value (stables) = `owned * $1`
- **USDC adjustment:** adds `(debt + borrow_lend_interests_accured) / 1e15` (tokens) back to USDC value at $1 each.
- Clear console report: per-custody rows, totals, computed NAV per JLP, and the gap vs the program’s theoretical price.

---

## Quick start

### 1) Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2) (Optional) Generate/refresh the Anchor client

If you need to regenerate the Python client for the JLP program (package `jlp/`), use `anchorpy`:

```bash
# Fetch the IDL
anchor idl fetch PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu -o PERP.idl

# Generate a Python client into ./jlp (this creates/updates the package used by nav.py)
anchorpy client-gen PERP.idl ./jlp --program-id PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu
```

> The repo includes `jlp/` pre-generated. Re-run the above only if the program or IDL updates.

### 3) Run

```bash
python nav.py
```

You’ll see output like:

```
=== Pool Info ===
Timestamp (ns): 1760743598385145260
Pool AUM (program):    $2106750463.88
Pool Limit (USD):      $3000000000.00
Fee APR (bps):         4061
Realized Fee (USD):    $306112.56
Theoretical JLP Price: $5.325893

Spot (Kraken) used: SOL=182.61, WBTC(BTC)=106785.6, ETH=3843.72, USDC=0.9998, USDT=1.0

=== Custody Breakdown (NAV calc) ===
 SOL | ... -> value=$980525398.73
WBTC | ... -> value=$269228455.37
 ETH | ... -> value=$170118997.91
USDC | ... -> value=$686947768.62
USDT | ... -> value=$184.10

=== Totals (Real-time NAV + USDC add-back) ===
AUM (NAV calc):        $2106820804.74
Fees total (est USD):  $11307.08
Long PnL total:        $60865345.99
Short PnL total:       $9366.92
Supply:                395567535.614754
JLP Price (NAV):       $5.326071
Pool Theoretical:      $5.325893
Total - Theo gap USD:  $70340.86
```

---

## How it works (math)

For each custody:

* Spot price (USD):

  * SOL → `SOLUSD` (Kraken)
  * WBTC → `XXBTZUSD` (BTC/USD on Kraken)
  * ETH → `XETHZUSD`
  * USDC → `USDCUSD` (falls back to 1.0 if needed)
  * USDT → 1.0
* `avg_locked_price = guaranteed_usd / locked` (USD per token)
* Long PnL: `(spot - avg_locked_price) * locked`
* Short PnL: `((short_notional / short_avg_price) * spot) - short_notional`
* Custody value:

  * volatile: `owned*spot - longPnL + shortPnL`
  * stables: `owned * 1.0`
  * **USDC add-back:** `value += (debt + borrow_lend_interests_accured) / 1e15`
* **AUM (realtime)** = sum of custody values
* **NAV per JLP** = `AUM / supply`

---

## Configuration

No required environment variables for the basic run.

If you want to tweak RPC:

* The script defaults to `https://api.mainnet-beta.solana.com`.
  Change `RPC_ENDPOINT` in `nav.py` if you prefer a different RPC (recommended for reliability/rate limits).

---

## Repository layout

```
jlp-realtime-nav/
├─ nav.py                 # Entry point: fetches Kraken prices, reads on-chain, computes NAV, prints report
├─ jlp/                   # Anchor-generated Python client package (you can regen via anchorpy if needed)
├─ PERP.idl               # (optional) Saved IDL used to generate the client
├─ requirements.txt
├─ README.md
└─ LICENSE                # MIT (suggested)
```

---

## Requirements

See `requirements.txt`. Main libs:

* `aiohttp` – Kraken HTTP client
* `solana` + `solders` – Solana RPC & account decoding
* `anchorpy` – Anchor client codegen/runtime (for `jlp/`)
* `python-dotenv` – only needed if you later add env-based config

---

## Troubleshooting

* **Prices look off / zeros:** Kraken sometimes rate-limits or pairs can momentarily fail. The script falls back to `guaranteed_usd/locked` for volatile spots only if Kraken returns `0` (to avoid divide-by-zero), but you’ll want to ensure prices are flowing for best accuracy.
* **AUM (program) vs AUM (NAV calc) mismatch:** Expect small drift. Large gaps usually mean a stale spot price, a zero `short_avg_price`, or RPC desync.
* **IDL changed?** Re-run:

  ```
  anchor idl fetch PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu -o PERP.idl
  anchorpy client-gen PERP.idl ./jlp --program-id PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu
  ```

---

## Contributing

PRs welcome! Please include:

* Repro steps and sample output
* Clear notes on any program/IDL assumptions
* If changing the math, add a short rationale and a comparison run

---

## License

MIT