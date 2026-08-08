import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


HISTORY_FILE = Path(__file__).resolve().parent.parent / "history.json"
SOURCE_FILE = Path(__file__).resolve().parent.parent / "source.py"


def load_history():
    if not HISTORY_FILE.exists():
        return {"observations": []}

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


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

    if current < 0:
        return None

    if not previous:
        return {
            "reference": current,
            "current": current,
            "discount": 0.0,
            "movement": 0.0,
            "observations": 1,
            "recurrence_score": 0.0,
            "drop_score": 0.0,
            "momentum_score": 0.0,
            "score": 0.0
        }

    previous_prices = [
        observation["current"]
        for observation in previous
        if observation["current"] >= 0
    ]

    if not previous_prices:
        return None

    historical_high = max(previous_prices)
    previous_price = previous[-1]["current"]

    if historical_high <= 0 or previous_price <= 0:
        return None

    discount = (
        historical_high - current
    ) / historical_high

    movement = (
        previous_price - current
    ) / previous_price

    recurrence_score = min(
        len(previous) * 10,
        30
    )

    drop_score = max(
        0,
        discount * 50
    )

    momentum_score = max(
        0,
        movement * 20
    )

    score = round(
        recurrence_score
        + drop_score
        + momentum_score,
        2
    )

    return {
        "reference": historical_high,
        "current": current,
        "discount": round(discount, 4),
        "movement": round(movement, 4),
        "observations": len(previous) + 1,
        "recurrence_score": round(
            recurrence_score,
            2
        ),
        "drop_score": round(
            drop_score,
            2
        ),
        "momentum_score": round(
            momentum_score,
            2
        ),
        "score": score
    }


def detect_opportunities(data, history):
    opportunities = []

    for item in data:
        metrics = calculate_metrics(
            item,
            get_previous_observations(
                history,
                item["name"]
            )
        )

        if metrics is None:
            continue

        # La señal PRICE_DROP requiere una caída
        # mínima del 20 % respecto al máximo histórico.
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

    for item in data:
        history["observations"].append({
            "timestamp": timestamp,
            "name": item["name"],
            "current": item["current"]
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
