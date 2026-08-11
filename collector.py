import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PAIRS = {
    "BTC/USDT": {
        "okx": "BTC-USDT",
        "kraken": "XBTUSDT",
    },
    "ETH/USDT": {
        "okx": "ETH-USDT",
        "kraken": "ETHUSDT",
    },
    "SOL/USDT": {
        "okx": "SOL-USDT",
        "kraken": "SOLUSDT",
    },
}

INTERVAL_SECONDS = 2
DURATION_SECONDS = 8 * 60

OUTPUT = Path("market_data.json")


def get_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Atlas/2.0",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_okx(symbol):
    url = (
        "https://www.okx.com/api/v5/market/ticker?"
        + urlencode({"instId": symbol})
    )

    data = get_json(url)

    if data.get("code") != "0" or not data.get("data"):
        raise RuntimeError(f"OKX error: {data}")

    ticker = data["data"][0]

    return {
        "bid": float(ticker["bidPx"]),
        "bid_size": float(ticker["bidSz"]),
        "ask": float(ticker["askPx"]),
        "ask_size": float(ticker["askSz"]),
        "timestamp": int(ticker["ts"]),
    }


def get_kraken(symbol):
    url = (
        "https://api.kraken.com/0/public/Ticker?"
        + urlencode({"pair": symbol})
    )

    data = get_json(url)

    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")

    result = data["result"]

    if not result:
        raise RuntimeError("Kraken returned no ticker data")

    ticker = next(iter(result.values()))

    return {
        "bid": float(ticker["b"][0]),
        "bid_size": float(ticker["b"][2]),
        "ask": float(ticker["a"][0]),
        "ask_size": float(ticker["a"][2]),
        "timestamp": int(time.time() * 1000),
    }


def spread_percent(buy_ask, sell_bid):
    return ((sell_bid - buy_ask) / buy_ask) * 100


def collect():
    samples = []

    start = time.monotonic()
    end = start + DURATION_SECONDS

    while time.monotonic() < end:
        collected_at = datetime.now(timezone.utc).isoformat()

        for pair, symbols in PAIRS.items():
            try:
                okx = get_okx(symbols["okx"])
                kraken = get_kraken(symbols["kraken"])

                okx_to_kraken = spread_percent(
                    okx["ask"],
                    kraken["bid"],
                )

                kraken_to_okx = spread_percent(
                    kraken["ask"],
                    okx["bid"],
                )

                sample = {
                    "collected_at": collected_at,
                    "pair": pair,
                    "okx": okx,
                    "kraken": kraken,
                    "spread_okx_to_kraken_pct": okx_to_kraken,
                    "spread_kraken_to_okx_pct": kraken_to_okx,
                }

                samples.append(sample)

                print(
                    f"{collected_at} | {pair} | "
                    f"OKX -> Kraken: {okx_to_kraken:+.4f}% | "
                    f"Kraken -> OKX: {kraken_to_okx:+.4f}%"
                )

            except Exception as exc:
                print(f"{collected_at} | {pair} | ERROR: {exc}")

        time.sleep(INTERVAL_SECONDS)

    OUTPUT.write_text(
        json.dumps(samples, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Collected {len(samples)} samples.")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    collect()
