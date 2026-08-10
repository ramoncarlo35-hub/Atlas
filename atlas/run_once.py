import json
from datetime import datetime, timezone
from pathlib import Path


HISTORY_FILE = Path(__file__).resolve().parent.parent / "history.json"
INPUT_FILE = Path(__file__).resolve().parent.parent / "input.json"


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


def load_input():
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)["products"]


def calculate_direction(previous_price, current_price):
    if previous_price is None:
        return "FLAT"

    if current_price > previous_price:
        return "UP"

    if current_price < previous_price:
        return "DOWN"

    return "FLAT"


def calculate_streak(observations):
    if len(observations) < 2:
        return {
            "direction": "FLAT",
            "streak": 0
        }

    prices = [
        item["current"]
        for item in observations
    ]

    directions = []

    for previous, current in zip(
        prices[:-1],
        prices[1:]
    ):
        directions.append(
            calculate_direction(
                previous,
                current
            )
        )

    if not directions:
        return {
            "direction": "FLAT",
            "streak": 0
        }

    last_direction = directions[-1]

    if last_direction == "FLAT":
        return {
            "direction": "FLAT",
            "streak": 0
        }

    streak = 0

    for direction in reversed(directions):
        if direction != last_direction:
            break

        streak += 1

    return {
        "direction": last_direction,
        "streak": streak
    }


def calculate_acceleration(observations):
    if len(observations) < 3:
        return 0.0

    prices = [
        item["current"]
        for item in observations
    ]

    previous_change = (
        prices[-2] - prices[-3]
    )

    current_change = (
        prices[-1] - prices[-2]
    )

    return round(
        current_change - previous_change,
        6
    )


def detect_opportunities(data, history):
    opportunities = []

    previous = {}

    for observation in history.get(
        "observations",
        []
    ):
        name = observation["name"]

        previous.setdefault(
            name,
            []
        ).append(observation)

    for item in data:
        name = item["name"]
        reference = item["reference"]
        current = item["current"]

        if reference <= 0 or current < 0:
            continue

        observations = previous.get(
            name,
            []
        )

        previous_price = (
            observations[-1]["current"]
            if observations
            else None
        )

        direction = calculate_direction(
            previous_price,
            current
        )

        history_with_current = (
            observations
            + [{
                "current": current
            }]
        )

        streak_data = calculate_streak(
            history_with_current
        )

        acceleration = calculate_acceleration(
            history_with_current
        )

        discount = (
            reference - current
        ) / reference

        # Mantenemos el umbral de oportunidad
        # en el 20%.
        if discount < 0.20:
            continue

        price_score = discount * 60

        recurrence_score = min(
            len(observations) * 5,
            20
        )

        trend_score = min(
            streak_data["streak"] * 4,
            12
        )

        momentum_score = min(
            abs(acceleration) / max(
                abs(current),
                1
            ) * 10000,
            8
        )

        score = round(
            price_score
            + recurrence_score
            + trend_score
            + momentum_score,
            2
        )

        opportunities.append({
            "name": name,
            "reference": reference,
            "current": current,
            "discount": round(
                discount,
                4
            ),
            "observations": len(
                observations
            ) + 1,
            "direction": direction,
            "direction_streak": streak_data[
                "streak"
            ],
            "acceleration": acceleration,
            "price_score": round(
                price_score,
                2
            ),
            "recurrence_score": round(
                recurrence_score,
                2
            ),
            "trend_score": round(
                trend_score,
                2
            ),
            "momentum_score": round(
                momentum_score,
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


def build_market_snapshot(data, history):
    snapshot = []

    previous = {}

    for observation in history.get(
        "observations",
        []
    ):
        previous.setdefault(
            observation["name"],
            []
        ).append(observation)

    for item in data:
        name = item["name"]
        current = item["current"]

        observations = previous.get(
            name,
            []
        )

        if observations:
            reference = observations[-1]["current"]
        else:
            reference = current

        if reference > 0:
            discount = (
                reference - current
            ) / reference
        else:
            discount = 0

        previous_price = (
            observations[-1]["current"]
            if observations
            else None
        )

        movement = (
            (current - previous_price)
            / previous_price
            if previous_price
            else 0
        )

        direction_data = calculate_streak(
            observations + [{
                "current": current
            }]
        )

        acceleration = calculate_acceleration(
            observations + [{
                "current": current
            }]
        )

        snapshot.append({
            "name": name,
            "reference": reference,
            "current": current,
            "discount": round(
                discount,
                4
            ),
            "movement": round(
                movement,
                4
            ),
            "observations": len(
                observations
            ) + 1,
            "direction": direction_data[
                "direction"
            ],
            "direction_streak": direction_data[
                "streak"
            ],
            "acceleration": acceleration
        })

    return snapshot


def run():
    data = load_input()
    history = load_history()

    opportunities = detect_opportunities(
        data,
        history
    )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    market_snapshot = build_market_snapshot(
        data,
        history
    )

    for item in data:
        history["observations"].append({
            "timestamp": timestamp,
            "name": item["name"],
            "reference": item["reference"],
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
    print(
        json.dumps(
            run()
        )
    )
