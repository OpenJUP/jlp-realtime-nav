# 🧮 jlp-realtime-nav

**Real-time, on-chain JLP Net Asset Value (NAV) engine for Solana — accurate, transparent, and live.**

This tool computes **JLP Net Asset Value (NAV)** per token in real time by reading **on-chain custody and pool state** directly from the **JLP program** and marking assets to **live Kraken spot prices**.
It reproduces and extends the original NAV logic to include the latest refinements — including the critical *USDC debt + borrow/lend interest add-back* correction for a precise, mark-to-market NAV.

> **Why not just read the on-chain AUM?**  
> The on-chain AUM field only updates when the pool processes a transaction. This tool recomputes AUM from each custody in real time, so it keeps tracking even when nothing’s hitting the pool.

---

## 🚀 Overview

Traditional JLP pool AUM is updated only when new transactions occur, leaving traders and risk managers without live pricing.
**jlp-realtime-nav** solves this by recomputing the NAV from **raw custody balances**, **on-chain guarantees**, and **short exposure data**, giving you the most up-to-date pool valuation possible.

This is not an oracle — it’s *your own transparent NAV calculator*.

---

## ✨ Key Features

* 🧾 **On-chain accuracy:** Pulls custody and pool data directly from the Solana blockchain.
* 📊 **Live pricing:** Fetches up-to-date SOL, WBTC, and ETH prices from the **Kraken API**.
* 💵 **Debt-adjusted NAV:** Adds back USDC debt and borrow/lend accrued interest to fix the underreported pool AUM.
* 🧠 **Full asset breakdown:** See exposure, PnL, and utilization per custody.
* ⚡ **Real-time refresh:** Use it to monitor AUM drift vs. the on-chain theoretical price.
* 🧰 **CLI or programmatic use:** Run standalone, or import into your bots and dashboards.

---

## 🧩 Architecture

```text
┌──────────────────────────────┐
│        Kraken API            │
│ (SOL, ETH, WBTC, USDC Spot) │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│   Solana JLP Program (IDL)   │
│  Custody + Pool State Fetch  │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│       NAV Calculator          │
│  (Adds USDC debt + interest) │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│     Console / JSON Output    │
└──────────────────────────────┘
```

---

## 📦 Installation

```bash
git clone https://github.com/OpenJUP/jlp-realtime-nav.git
cd jlp-realtime-nav
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Requirements

* Python ≥ 3.10
* `anchorpy`, `aiohttp`, `solana`, `solders`
* Internet access for Kraken API + Solana RPC
* Optional: MySQL if you want to log results

---

## ⚙️ Usage

### CLI Mode

```bash
python nav.py
```

Outputs human-readable live NAV breakdown:

```
=== Pool Info ===
Pool AUM (program):    $2,106,750,463.88
Fee APR (bps):         4061
Theoretical JLP Price: $5.3259

Spot (Kraken): SOL=182.61, BTC=106,785.6, ETH=3843.72

=== Totals (NAV calc) ===
AUM (NAV calc):        $2,106,820,804.74
JLP Price (NAV):       $5.3261
Total - Theo gap USD:  $+70,340.86
```

### API / Integration Mode

```python
from jlp_nav import get_nav

result = await get_nav()
print(result["jlp_price_nav"])
```

Returns:

```json
{
  "pool_aum": 2106820804.74,
  "supply": 395567535.61,
  "jlp_nav_price": 5.32607,
  "price_gap_usd": 70340.86
}
```

---

## 📚 How It Works

**NAV Calculation Formula:**

```
NAV = (Σ(asset_value + short_PnL - long_PnL + fees_reserve)
      + USDC_debt + accrued_interest) / JLP_supply
```

* **Asset Value** = (owned * price)
* **PnL** = (spot - avg_locked_price) × locked
* **Debt Add-back** = adds USDC borrowings back to AUM for accurate NAV
* **Supply** = on-chain total JLP token supply

---

## 🌐 Updating Anchor IDL

To regenerate your client from the latest on-chain program:

```bash
anchor idl fetch PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu -o PERP.idl
anchorpy client-gen PERP.idl ./jlp --program-id PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu
```

---

## 🧠 Technical Notes

* **Kraken API Pairs:**

  * BTC → `XXBTZUSD`
  * ETH → `XETHZUSD`
  * SOL → `SOLUSD`
  * USDC → `USDCUSD`

* **Solana RPC:**
  Uses `https://api.mainnet-beta.solana.com` (changeable via env vars)

* **Performance:**
  Full NAV computation <1s on standard network latency

---

## ⚠️ Disclaimer

This software provides **real-time analytical NAV data** based on public blockchain and market APIs.
It is **not an oracle**, **not financial advice**, and **not a trading recommendation**.
Use at your own risk — values may drift slightly due to pending Solana updates or Kraken API delays.

---

## 🧭 About OpenJUP

OpenJUP is an open DeFi analytics collective building transparent tools for Solana and beyond.
We believe *on-chain data should be readable, verifiable, and open to everyone*.

🌐 [OpenJUP GitHub](https://github.com/OpenJUP)
💬 Join the community — transparency meets precision.

---

## 🏷️ Badges

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)]()
[![Solana](https://img.shields.io/badge/Solana-Mainnet-black)]()
[![Kraken](https://img.shields.io/badge/Prices-Kraken-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![OpenJUP](https://img.shields.io/badge/OpenJUP-DeFi%20Transparency-purple.svg)]()

---

💡 **“Know your pool. Trust your math.”**
