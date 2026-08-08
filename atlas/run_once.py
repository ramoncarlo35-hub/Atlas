import json
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
    import subprocess

    result = subprocess.run(
        ["python", str(SOURCE_FILE)],
        capture_output=True,
        text=True,
        check=True
    )

    return json.loads(result.stdout)


def detect_opportunities(data, history):
    opportunities = []

    previous = {}

    for observation in history.get("observations", []):
        name = observation["name"]
        previous.setdefault(name, []).append(observation)

    for item in data:
        current = item["current"]

        if current < 0:
            continue

        observations = previous.get(item["name"], [])

        if observations:
            reference = observations[-1]["current"]
        else:
            reference = current

        if reference <= 0:
            continue

        discount = (reference - current) / reference

        if discount >= 0.20:
            recurrence_score = min(
                len(observations) * 20,
                40
            )

            price_score = discount * 60

            score = round(
                price_score + recurrence_score,
                2
            )

            opportunities.append({
                "name": item["name"],
                "reference": reference,
                "current": current,
                "discount": round(discount, 4),
                "observations": len(observations) + 1,
                "price_score": round(price_score, 2),
                "recurrence_score": round(
                    recurrence_score,
                    2
                ),
                "score": score,
                "signal": "PRICE_DROP"
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
            "reference": item["current"],
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
