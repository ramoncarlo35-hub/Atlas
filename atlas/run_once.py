import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


HISTORY_FILE = Path(__file__).resolve().parent.parent / "history.json"
SOURCE_FILE = Path(__file__).resolve().parent.parent / "source.py"


def load_history():
    if not HISTORY_FILE.exists():
        return {"observations": []}

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            ensure_ascii=False,
            indent=2
        )


def load_real_data():
    result = subprocess.run(
        ["python", str(SOURCE_FILE)],
        capture_output=True,
        text=True,
        check=True
    )

    return json.loads(result.stdout)


def get_previous_observations(history, name):
    return [
        observation
        for observation in history.get("observations", [])
        if observation["name"] == name
    ]


def calculate_metrics(item, previous):
    current = item["current"]
    current_volume = item.get("volume_24h", 0)

    if current < 0:
        return None

    if current_volume < 0:
        current_volume = 0

    # Primera observación:
    # todavía no tenemos histórico suficiente
    # para calcular movimiento o anomalía de volumen.
    if not previous:
        return {
            "reference": current,
            "current": current,
            "volume_24h": current_volume,
            "discount": 0.0,
            "movement": 0.0,
            "volume_ratio": 1.0,
            "observations": 1,
            "drop_score": 0.0,
            "momentum_score": 0.0,
            "volume_score": 0.0,
            "recurrence_factor": 1.0,
            "score": 0.0
        }

    previous_prices = [
        observation["current"]
        for observation in previous
        if observation.get("current", -1) >= 0
    ]

    previous_volumes = [
        observation["volume_24h"]
        for observation in previous
        if observation.get("volume_24h", 0) > 0
    ]

    if not previous_prices:
        return None

    historical_high = max(previous_prices)
    previous_price = previous[-1]["current"]

    if historical_high <= 0 or previous_price <= 0:
        return None

    # -------------------------------------------------
    # 1. PRECIO
    # -------------------------------------------------

    discount = (
        historical_high - current
    ) / historical_high

    movement = (
        previous_price - current
    ) / previous_price

    # La caída respecto al máximo es la señal principal.
    drop_score = max(
        0,
        discount * 100
    )

    # Movimiento entre observaciones consecutivas.
    momentum_score = max(
        0,
        movement * 25
    )

    # -------------------------------------------------
    # 2. VOLUMEN
    # -------------------------------------------------

    if previous_volumes and current_volume > 0:
        average_volume = mean(previous_volumes)

        if average_volume > 0:
            volume_ratio = (
                current_volume / average_volume
            )
        else:
            volume_ratio = 1.0
    else:
        volume_ratio = 1.0

    # Solo premiamos volumen por encima de su media.
    # 1.0 = volumen normal.
    # 2.0 = el doble de la media.
    volume_score = max(
        0,
        min(
            (volume_ratio - 1.0) * 20,
            30
        )
    )

    # -------------------------------------------------
    # 3. RECURRENCIA
    # -------------------------------------------------

    observations = len(previous)

    # La recurrencia refuerza, pero nunca crea,
    # una señal por sí sola.
    recurrence_factor = min(
        1.0 + (observations * 0.05),
        1.50
    )

    # -------------------------------------------------
    # 4. SCORE
    # -------------------------------------------------

    base_score = (
        drop_score
        + momentum_score
        + volume_score
    )

    score = round(
        base_score * recurrence_factor,
        2
    )

    return {
        "reference": historical_high,
        "current": current,
        "volume_24h": current_volume,
        "discount": round(discount, 4),
        "movement": round(movement, 4),
        "volume_ratio": round(
            volume_ratio,
            4
        ),
        "observations": observations + 1,
        "drop_score": round(
            drop_score,
            2
        ),
        "momentum_score": round(
            momentum_score,
            2
        ),
        "volume_score": round(
            volume_score,
            2
        ),
        "recurrence_factor": round(
            recurrence_factor,
            2
        ),
        "score": score
    }


def detect_opportunities(data, history):
    opportunities = []

    for item in data:
        previous = get_previous_observations(
            history,
            item["name"]
        )

        metrics = calculate_metrics(
            item,
            previous
        )

        if metrics is None:
            continue

        # Mantenemos el umbral de seguridad:
        # no existe oportunidad PRICE_DROP
        # hasta una caída mínima del 20 %.
        if metrics["discount"] >= 0.20:
            opportunities.append({
                "name": item["name"],
                **metrics,
                "signal": "PRICE_DROP"
            })

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return opportunities


def build_market_snapshot(data, history):
    snapshot = []

    for item in data:
        previous = get_previous_observations(
            history,
            item["name"]
        )

        metrics = calculate_metrics(
            item,
            previous
        )

        if metrics is None:
            continue

        snapshot.append({
            "name": item["name"],
            **metrics
        })

    snapshot.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return snapshot


def run():
    data = load_real_data()
    history = load_history()

    opportunities = detect_opportunities(
        data,
        history
    )

    market_snapshot = build_market_snapshot(
        data,
        history
    )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    # Guardamos precio Y volumen.
    for item in data:
        history["observations"].append({
            "timestamp": timestamp,
            "name": item["name"],
            "current": item["current"],
            "volume_24h": item.get(
                "volume_24h",
                0
            )
        })

    save_history(history)

    selected = (
        opportunities[0]
        if opportunities
        else None
    )

    return {
        "runtime": "ATLAS",
        "mode": "DRY_RUN",
        "timestamp": timestamp,
        "status": "READY",
        "detector": {
            "enabled": True,
            "opportunities_found": len(
                opportunities
            ),
            "action_taken": False,
            "selected_opportunity": selected,
            "opportunities": opportunities,
            "market_snapshot": market_snapshot
        }
    }


if __name__ == "__main__":
    print(json.dumps(run()))
