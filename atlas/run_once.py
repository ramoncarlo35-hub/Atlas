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


def detect_opportunities(data, history):
    opportunities = []

    for item in data:
        name = item["name"]
        current = item["current"]

        if current < 0:
            continue

        previous = get_previous_observations(
            history,
            name
        )

        if not previous:
            continue

        previous_prices = [
            observation["current"]
            for observation in previous
            if observation["current"] >= 0
        ]

        if not previous_prices:
            continue

        historical_high = max(previous_prices)

        if historical_high <= 0:
            continue

        discount = (
            historical_high - current
        ) / historical_high

        previous_price = previous[-1]["current"]

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

        if discount >= 0.20:
            signal = "PRICE_DROP"

            opportunities.append({
                "name": name,
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
                "score": score,
                "signal": signal
            })

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return opportunities


def run():
    data = load_real_data()
    history = load_history()

    opportunities = detect_opportunities(
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
            "opportunities": opportunities
        }
    }


if __name__ == "__main__":
    print(json.dumps(run()))
