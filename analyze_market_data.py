import json
import statistics
from collections import defaultdict
from pathlib import Path

INPUT_FILE = Path("market_data.json")
OUTPUT_JSON = Path("analysis_report.json")
OUTPUT_MD = Path("analysis_report.md")

CAPITAL_EUR = 40.0

FEE_SCENARIOS = {
    "standard": {
        "name": "OKX standard EEA + Kraken Tier 1",
        "okx_taker_pct": 0.35,
        "kraken_taker_pct": 0.80,
    },
    "okx_xperps": {
        "name": "OKX X-Perps standard + Kraken Tier 1",
        "okx_taker_pct": 0.10,
        "kraken_taker_pct": 0.80,
    },
}

THRESHOLDS = [
    0.00,
    0.01,
    0.02,
    0.05,
    0.10,
    0.20,
    0.50,
    1.00,
]


def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"No existe {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("market_data.json no contiene una lista")

    return data


def calculate_trade(sample, direction, capital, okx_fee_pct, kraken_fee_pct):
    if direction == "OKX_TO_KRAKEN":
        buy_exchange = "OKX"
        sell_exchange = "Kraken"

        buy_price = sample["okx"]["ask"]
        buy_size = sample["okx"]["ask_size"]

        sell_price = sample["kraken"]["bid"]
        sell_size = sample["kraken"]["bid_size"]

        buy_fee_pct = okx_fee_pct
        sell_fee_pct = kraken_fee_pct

    else:
        buy_exchange = "Kraken"
        sell_exchange = "OKX"

        buy_price = sample["kraken"]["ask"]
        buy_size = sample["kraken"]["ask_size"]

        sell_price = sample["okx"]["bid"]
        sell_size = sample["okx"]["bid_size"]

        buy_fee_pct = kraken_fee_pct
        sell_fee_pct = okx_fee_pct

    if buy_price <= 0 or sell_price <= 0:
        return None

    executable_quantity = min(buy_size, sell_size)

    capital_limited_quantity = capital / buy_price

    quantity = min(
        executable_quantity,
        capital_limited_quantity,
    )

    if quantity <= 0:
        return None

    buy_notional = quantity * buy_price
    sell_notional = quantity * sell_price

    buy_fee = buy_notional * (buy_fee_pct / 100)
    sell_fee = sell_notional * (sell_fee_pct / 100)

    gross_profit = sell_notional - buy_notional
    net_profit = gross_profit - buy_fee - sell_fee

    gross_spread_pct = (
        (sell_price - buy_price) / buy_price
    ) * 100

    net_profit_pct = (
        net_profit / buy_notional
    ) * 100

    return {
        "buy_exchange": buy_exchange,
        "sell_exchange": sell_exchange,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": quantity,
        "capital_used": buy_notional,
        "gross_spread_pct": gross_spread_pct,
        "gross_profit": gross_profit,
        "buy_fee": buy_fee,
        "sell_fee": sell_fee,
        "net_profit": net_profit,
        "net_profit_pct": net_profit_pct,
    }


def percentile(values, percentile):
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered))

    if lower == upper:
        return ordered[lower]

    weight = position - lower

    return (
        ordered[lower] * (1 - weight)
        + ordered[upper] * weight
    )


def analyze_direction(data, direction, fee_scenario):
    okx_fee = fee_scenario["okx_taker_pct"]
    kraken_fee = fee_scenario["kraken_taker_pct"]

    spreads = []
    positive = []
    trades = []

    by_pair = defaultdict(list)

    for sample in data:
        result = calculate_trade(
            sample,
            direction,
            CAPITAL_EUR,
            okx_fee,
            kraken_fee,
        )

        if result is None:
            continue

        spread = result["gross_spread_pct"]
        spreads.append(spread)

        by_pair[sample["pair"]].append(result)

        if spread > 0:
            positive.append(result)

        trades.append(result)

    if not spreads:
        return {
            "samples": 0,
            "positive_samples": 0,
            "max_gross_spread_pct": None,
            "mean_gross_spread_pct": None,
            "median_gross_spread_pct": None,
            "p95_gross_spread_pct": None,
            "best_trade": None,
            "thresholds": {},
            "by_pair": {},
        }

    threshold_results = {}

    for threshold in THRESHOLDS:
        matching = [
            r for r in trades
            if r["gross_spread_pct"] >= threshold
        ]

        threshold_results[f"{threshold:.2f}%"] = {
            "count": len(matching),
            "max_net_profit": (
                max(r["net_profit"] for r in matching)
                if matching
                else None
            ),
        }

    best_trade = max(
        trades,
        key=lambda r: r["gross_spread_pct"],
    )

    pair_results = {}

    for pair, pair_trades in by_pair.items():
        pair_spreads = [
            r["gross_spread_pct"]
            for r in pair_trades
        ]

        best_pair_trade = max(
            pair_trades,
            key=lambda r: r["gross_spread_pct"],
        )

        pair_results[pair] = {
            "samples": len(pair_trades),
            "positive_samples": sum(
                1 for r in pair_trades
                if r["gross_spread_pct"] > 0
            ),
            "max_gross_spread_pct": max(pair_spreads),
            "mean_gross_spread_pct": statistics.mean(pair_spreads),
            "median_gross_spread_pct": statistics.median(pair_spreads),
            "p95_gross_spread_pct": percentile(
                pair_spreads,
                0.95,
            ),
            "best_trade": best_pair_trade,
        }

    return {
        "samples": len(spreads),
        "positive_samples": len(positive),
        "max_gross_spread_pct": max(spreads),
        "mean_gross_spread_pct": statistics.mean(spreads),
        "median_gross_spread_pct": statistics.median(spreads),
        "p95_gross_spread_pct": percentile(
            spreads,
            0.95,
        ),
        "best_trade": best_trade,
        "thresholds": threshold_results,
        "by_pair": pair_results,
    }


def analyze_scenario(data, scenario):
    return {
        "scenario": scenario["name"],
        "okx_taker_fee_pct": scenario["okx_taker_pct"],
        "kraken_taker_fee_pct": scenario["kraken_taker_pct"],
        "total_taker_fee_pct": (
            scenario["okx_taker_pct"]
            + scenario["kraken_taker_pct"]
        ),
        "okx_to_kraken": analyze_direction(
            data,
            "OKX_TO_KRAKEN",
            scenario,
        ),
        "kraken_to_okx": analyze_direction(
            data,
            "KRAKEN_TO_OKX",
            scenario,
        ),
    }


def format_number(value, decimals=6):
    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def generate_markdown(report):
    lines = []

    lines.append("# Atlas #2B — Market Data Analysis")
    lines.append("")
    lines.append(
        f"Capital de prueba: **{CAPITAL_EUR:.2f} €**"
    )
    lines.append("")
    lines.append(
        "El análisis utiliza únicamente el primer nivel del libro "
        "recogido por Atlas. No se descuenta slippage."
    )
    lines.append("")

    lines.append(
        f"Total de muestras: **{report['total_samples']}**"
    )
    lines.append("")

    for scenario_key, scenario in report["scenarios"].items():
        lines.append(f"## {scenario['scenario']}")
        lines.append("")
        lines.append(
            f"- OKX taker: **{scenario['okx_taker_fee_pct']:.3f}%**"
        )
        lines.append(
            f"- Kraken taker: **{scenario['kraken_taker_fee_pct']:.3f}%**"
        )
        lines.append(
            f"- Coste conjunto: **{scenario['total_taker_fee_pct']:.3f}%**"
        )
        lines.append("")

        for direction_key in [
            "okx_to_kraken",
            "kraken_to_okx",
        ]:
            direction = scenario[direction_key]

            lines.append(
                f"### {direction_key.replace('_', ' ').upper()}"
            )
            lines.append("")

            lines.append(
                f"- Muestras: **{direction['samples']}**"
            )
            lines.append(
                f"- Muestras con spread positivo: "
                f"**{direction['positive_samples']}**"
            )
            lines.append(
                f"- Spread máximo: "
                f"**{format_number(direction['max_gross_spread_pct'])}%**"
            )
            lines.append(
                f"- Spread medio: "
                f"**{format_number(direction['mean_gross_spread_pct'])}%**"
            )
            lines.append(
                f"- Spread mediano: "
                f"**{format_number(direction['median_gross_spread_pct'])}%**"
            )
            lines.append(
                f"- Percentil 95: "
                f"**{format_number(direction['p95_gross_spread_pct'])}%**"
            )
            lines.append("")

            best = direction["best_trade"]

            if best:
                lines.append("**Mejor oportunidad bruta:**")
                lines.append("")
                lines.append(
                    f"- Compra: {best['buy_exchange']} "
                    f"@ {best['buy_price']}"
                )
                lines.append(
                    f"- Venta: {best['sell_exchange']} "
                    f"@ {best['sell_price']}"
                )
                lines.append(
                    f"- Capital utilizado: "
                    f"{best['capital_used']:.4f} €"
                )
                lines.append(
                    f"- Spread bruto: "
                    f"{best['gross_spread_pct']:.6f}%"
                )
                lines.append(
                    f"- Beneficio bruto: "
                    f"{best['gross_profit']:.6f} €"
                )
                lines.append(
                    f"- Beneficio neto: "
                    f"{best['net_profit']:.6f} €"
                )
                lines.append(
                    f"- Rentabilidad neta: "
                    f"{best['net_profit_pct']:.6f}%"
                )
                lines.append("")

            lines.append("| Umbral bruto | Nº muestras | Mejor neto (€) |")
            lines.append("|---:|---:|---:|")

            for threshold, result in direction["thresholds"].items():
                max_profit = result["max_net_profit"]

                if max_profit is None:
                    max_profit_text = "—"
                else:
                    max_profit_text = f"{max_profit:.6f}"

                lines.append(
                    f"| {threshold} | "
                    f"{result['count']} | "
                    f"{max_profit_text} |"
                )

            lines.append("")

            lines.append("| Par | Muestras | Positivas | Máx. bruto | Mediana |")
            lines.append("|---|---:|---:|---:|---:|")

            for pair, pair_data in direction["by_pair"].items():
                lines.append(
                    f"| {pair} | "
                    f"{pair_data['samples']} | "
                    f"{pair_data['positive_samples']} | "
                    f"{pair_data['max_gross_spread_pct']:.6f}% | "
                    f"{pair_data['median_gross_spread_pct']:.6f}% |"
                )

            lines.append("")

    return "\n".join(lines)


def main():
    data = load_data()

    report = {
        "capital_eur": CAPITAL_EUR,
        "total_samples": len(data),
        "scenarios": {},
    }

    for key, scenario in FEE_SCENARIOS.items():
        report["scenarios"][key] = analyze_scenario(
            data,
            scenario,
        )

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    OUTPUT_MD.write_text(
        generate_markdown(report),
        encoding="utf-8",
    )

    print("=" * 60)
    print("ATLAS #2B — MARKET DATA ANALYSIS")
    print("=" * 60)
    print(f"Muestras analizadas: {len(data)}")
    print()

    for key, scenario in report["scenarios"].items():
        print(scenario["scenario"])
        print(
            f"Coste conjunto taker: "
            f"{scenario['total_taker_fee_pct']:.3f}%"
        )

        for direction_key in [
            "okx_to_kraken",
            "kraken_to_okx",
        ]:
            direction = scenario[direction_key]

            print(
                f"  {direction_key}: "
                f"max={format_number(direction['max_gross_spread_pct'])}% "
                f"positive={direction['positive_samples']}"
            )

        print()

    print(f"Guardado: {OUTPUT_JSON}")
    print(f"Guardado: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
