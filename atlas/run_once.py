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
        if observation.get("name") == name
    ]


def get_price_series(previous, current):
    prices = [
        observation["current"]
        for observation in previous
        if observation.get("current", -1) >= 0
    ]

    prices.append(current)

    return prices


def calculate_trend_metrics(prices):
    """
    Analiza las últimas variaciones de precio.

    direction_streak:
        positivo = número de movimientos consecutivos al alza
        negativo = número de movimientos consecutivos a la baja

    acceleration:
        compara la magnitud del último movimiento
        con la magnitud media de los movimientos anteriores.
    """

    if len(prices) < 2:
        return {
            "direction": "UNKNOWN",
            "direction_streak": 0,
            "trend_score": 0.0,
            "acceleration": 0.0,
            "acceleration_score": 0.0
        }

    movements = []

    for previous_price, current_price in zip(
        prices[:-1],
        prices[1:]
    ):
        if previous_price <= 0:
            continue

        movements.append(
            (current_price - previous_price)
            / previous_price
        )

    if not movements:
        return {
            "direction": "UNKNOWN",
            "direction_streak": 0,
            "trend_score": 0.0,
            "acceleration": 0.0,
            "acceleration_score": 0.0
        }

    last_movement = movements[-1]

    if last_movement < 0:
        direction = "DOWN"
        direction_streak = 1

        for movement in reversed(movements[:-1]):
            if movement < 0:
                direction_streak += 1
            else:
                break

    elif last_movement > 0:
        direction = "UP"
        direction_streak = 1

        for movement in reversed(movements[:-1]):
            if movement > 0:
                direction_streak += 1
            else:
                break

    else:
        direction = "FLAT"
        direction_streak = 0

    # Solo utilizamos movimientos anteriores al actual
    # para establecer una referencia de velocidad.
    previous_movements = movements[:-1]

    if previous_movements:
        average_abs_movement = mean(
            abs(value)
            for value in previous_movements
        )
    else:
        average_abs_movement = 0.0

    if average_abs_movement > 0:
        acceleration = (
            abs(last_movement)
            / average_abs_movement
        )
    else:
        acceleration = 1.0

    # La persistencia aporta hasta 20 puntos.
    trend_score = min(
        direction_streak * 4,
        20
    )

    # Solo premiamos aceleración cuando existe.
    # No permitimos que este factor domine el sistema.
    acceleration_score = min(
        max(acceleration - 1.0, 0)
        * 10,
        20
    )

    # Si el último movimiento es hacia abajo,
    # la aceleración es relevante para una posible caída.
    # Para movimientos alcistas la información también
    # se conserva, pero no genera una señal de venta.
    if direction == "DOWN":
        acceleration_score = round(
            acceleration_score,
            2
        )
    else:
        acceleration_score = 0.0

    return {
        "direction": direction,
        "direction_streak": direction_streak,
        "trend_score": round(
            trend_score,
            2
        ),
        "acceleration": round(
            acceleration,
            4
        ),
        "acceleration_score": round(
            acceleration_score,
            2
        )
    }


def calculate_metrics(item, previous):
    current = item["current"]
    current_volume = item.get("volume_24h", 0)

    if current < 0:
        return None

    if current_volume < 0:
        current_volume = 0

    prices = get_price_series(
        previous,
        current
    )

    trend = calculate_trend_metrics(prices)

    # Primera observación.
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
            "trend_score": trend["trend_score"],
            "direction": trend["direction"],
            "direction_streak": trend["direction_streak"],
            "acceleration": trend["acceleration"],
            "acceleration_score": trend[
                "acceleration_score"
            ],
            "recurrence_factor": 1.0,
            "score": 0.0
        }

    previous_prices = [
        observation["current"]
        for observation in previous
        if observation.get("current", -1) >= 0
    ]

    previous_volumes = [
        observation.get("volume_24h", 0)
        for observation in previous
        if observation.get("volume_24h", 0) > 0
    ]

    if not previous_prices:
        return None

    historical_high = max(previous_prices)
    previous_price = previous[-1]["current"]

    if historical_high <= 0 or previous_price <= 0:
        return None

    # -----------------------------
    # 1. CAÍDA RESPECTO AL MÁXIMO
    # -----------------------------

    discount = (
        historical_high - current
    ) / historical_high

    drop_score = max(
        0,
        discount * 100
    )

    # -----------------------------
    # 2. MOVIMIENTO RECIENTE
    # -----------------------------

    movement = (
        previous_price - current
    ) / previous_price

    momentum_score = max(
        0,
        movement * 25
    )

    # -----------------------------
    # 3. VOLUMEN
    # -----------------------------

    if previous_volumes and current_volume > 0:
        average_volume = mean(
            previous_volumes
        )

        if average_volume > 0:
            volume_ratio = (
                current_volume
                / average_volume
            )
        else:
            volume_ratio = 1.0
    else:
        volume_ratio = 1.0

    volume_score = max(
        0,
        min(
            (volume_ratio - 1.0) * 20,
            30
        )
    )

    # -----------------------------
    # 4. RECURRENCIA
    # -----------------------------

    observations = len(previous)

    recurrence_factor = min(
        1.0 + (observations * 0.05),
        1.50
    )

    # -----------------------------
    # 5. TENDENCIA
    # -----------------------------

    trend_score = trend["trend_score"]

    acceleration_score = trend[
        "acceleration_score"
    ]

    # -----------------------------
    # 6. SCORE TOTAL
    # -----------------------------

    base_score = (
        drop_score
        + momentum_score
        + volume_score
        + trend_score
        + acceleration_score
    )

    score = round(
        base_score * recurrence_factor,
        2
    )

    return {
        "reference": historical_high,
        "current": current,
        "volume_24h": current_volume,
        "discount": round(
            discount,
            4
        ),
        "movement": round(
            movement,
            4
        ),
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
        "trend_score": round(
            trend_score,
            2
        ),
        "direction": trend["direction"],
        "direction_streak": trend[
            "direction_streak"
        ],
        "acceleration": trend[
            "acceleration"
        ],
        "acceleration_score": round(
            acceleration_score,
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

        # Mantenemos el filtro duro del 20%.
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

    # Guardamos precio y volumen.
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
