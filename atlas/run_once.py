import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev


ROOT_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT_DIR / "history.json"
SOURCE_FILE = ROOT_DIR / "source.py"

# Ventana de análisis.
# Con 12 observaciones tenemos suficiente para empezar
# sin hacer que el histórico antiguo domine el cálculo.
WINDOW_SIZE = 12

# Umbral de anomalía.
# -1.5 significa que el precio está 1,5 desviaciones
# estándar por debajo de la media reciente.
ANOMALY_Z_THRESHOLD = -1.5

# Exigimos que el volumen sea al menos un 20% superior
# a su media reciente para considerarlo confirmación.
VOLUME_CONFIRMATION_RATIO = 1.20


def load_history():
    if not HISTORY_FILE.exists():
        return {
            "observations": [],
            "market_observations": []
        }

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    history.setdefault("observations", [])
    history.setdefault("market_observations", [])

    return history


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            ensure_ascii=False,
            indent=2
        )


def load_real_market_data():
    result = subprocess.run(
        ["python", str(SOURCE_FILE)],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=True
    )

    output = result.stdout.strip()

    if not output:
        raise RuntimeError(
            "source.py no devolvió datos."
        )

    try:
        data = json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"source.py devolvió un JSON inválido:\n{output}"
        ) from error

    if not isinstance(data, list):
        raise RuntimeError(
            "source.py debe devolver una lista de activos."
        )

    return data


def get_previous_market_observations(
    history,
    name
):
    observations = [
        observation
        for observation in history["market_observations"]
        if observation["name"] == name
    ]

    return observations[-WINDOW_SIZE:]


def calculate_direction(
    previous_price,
    current_price
):
    if previous_price is None:
        return "FLAT"

    if current_price > previous_price:
        return "UP"

    if current_price < previous_price:
        return "DOWN"

    return "FLAT"


def calculate_streak(
    observations
):
    if len(observations) < 2:
        return {
            "direction": "FLAT",
            "streak": 0
        }

    prices = [
        float(item["current"])
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


def calculate_acceleration(
    observations
):
    if len(observations) < 3:
        return 0.0

    prices = [
        float(item["current"])
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


def calculate_anomaly(
    prices,
    current
):
    if len(prices) < 3:
        return {
            "mean": current,
            "std_dev": 0.0,
            "z_score": 0.0
        }

    average = mean(prices)
    deviation = pstdev(prices)

    if deviation == 0:
        z_score = 0.0
    else:
        z_score = (
            current - average
        ) / deviation

    return {
        "mean": round(average, 2),
        "std_dev": round(deviation, 2),
        "z_score": round(z_score, 3)
    }


def calculate_volume_ratio(
    volumes,
    current_volume
):
    valid_volumes = [
        volume
        for volume in volumes
        if volume > 0
    ]

    if not valid_volumes:
        return 1.0

    average_volume = mean(
        valid_volumes
    )

    if average_volume <= 0:
        return 1.0

    return round(
        current_volume / average_volume,
        3
    )


def calculate_metrics(
    item,
    previous
):
    current = float(
        item["current"]
    )

    current_volume = float(
        item.get("volume_24h", 0)
    )

    previous_prices = [
        float(observation["current"])
        for observation in previous
    ]

    previous_volumes = [
        float(
            observation.get(
                "volume_24h",
                0
            )
        )
        for observation in previous
    ]

    # --------------------------------------------------
    # Precio de referencia
    # --------------------------------------------------

    if previous_prices:
        reference = mean(
            previous_prices
        )
    else:
        reference = current

    discount = (
        (reference - current)
        / reference
        if reference > 0
        else 0
    )

    # --------------------------------------------------
    # Movimiento reciente
    # --------------------------------------------------

    if previous_prices:
        previous_price = previous_prices[-1]

        movement = (
            (current - previous_price)
            / previous_price
            if previous_price > 0
            else 0
        )
    else:
        previous_price = None
        movement = 0

    direction_data = calculate_streak(
        previous
        + [{
            "current": current
        }]
    )

    acceleration = calculate_acceleration(
        previous
        + [{
            "current": current
        }]
    )

    # --------------------------------------------------
    # Anomalía estadística
    # --------------------------------------------------

    anomaly = calculate_anomaly(
        previous_prices,
        current
    )

    # --------------------------------------------------
    # Volumen relativo
    # --------------------------------------------------

    volume_ratio = calculate_volume_ratio(
        previous_volumes,
        current_volume
    )

    # --------------------------------------------------
    # Scores
    # --------------------------------------------------

    # Cuanto más negativo sea el z-score,
    # mayor será la anomalía bajista.
    if anomaly["z_score"] < 0:
        anomaly_score = min(
            abs(anomaly["z_score"]) * 15,
            30
        )
    else:
        anomaly_score = 0.0

    # El movimiento reciente aporta como máximo 20 puntos.
    momentum_score = min(
        abs(movement) * 100,
        20
    )

    # Confirmación de volumen:
    # 1.0 = volumen normal
    # 1.2 = 20% superior
    # 2.0 = doble del volumen habitual
    volume_score = min(
        max(volume_ratio - 1, 0) * 20,
        20
    )

    # Persistencia de la dirección.
    trend_score = min(
        direction_data["streak"] * 4,
        12
    )

    # La recurrencia ya NO domina la puntuación.
    recurrence_factor = min(
        1 + len(previous) * 0.02,
        1.5
    )

    base_score = (
        anomaly_score
        + momentum_score
        + volume_score
        + trend_score
    )

    score = round(
        base_score * recurrence_factor,
        2
    )

    # --------------------------------------------------
    # Señal
    # --------------------------------------------------

    if (
        anomaly["z_score"]
        <= ANOMALY_Z_THRESHOLD
        and volume_ratio
        >= VOLUME_CONFIRMATION_RATIO
    ):
        signal = "ANOMALOUS_DROP"

    else:
        signal = "NORMAL_MOVEMENT"

    return {
        "name": item["name"],
        "reference": round(
            reference,
            2
        ),
        "current": round(
            current,
            2
        ),
        "volume_24h": round(
            current_volume,
            2
        ),
        "discount": round(
            discount,
            4
        ),
        "movement": round(
            movement,
            4
        ),
        "direction": direction_data[
            "direction"
        ],
        "direction_streak": direction_data[
            "streak"
        ],
        "acceleration": acceleration,
        "observations": len(previous) + 1,
        "mean_price": anomaly[
            "mean"
        ],
        "std_dev": anomaly[
            "std_dev"
        ],
        "z_score": anomaly[
            "z_score"
        ],
        "volume_ratio": volume_ratio,
        "anomaly_score": round(
            anomaly_score,
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
        "recurrence_factor": round(
            recurrence_factor,
            2
        ),
        "score": score,
        "signal": signal
    }


def detect_opportunities(
    metrics
):
    opportunities = []

    for item in metrics:

        # Una oportunidad ahora requiere:
        #
        # 1. anomalía estadística bajista
        # 2. confirmación de volumen
        #
        # No basta con que el precio esté un poco por
        # debajo de la referencia.
        if (
            item["signal"]
            == "ANOMALOUS_DROP"
        ):
            opportunities.append(
                item
            )

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return opportunities


def run():
    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    history = load_history()

    # --------------------------------------------------
    # 1. DATOS REALES
    # --------------------------------------------------

    market_data = load_real_market_data()

    # --------------------------------------------------
    # 2. ANALISIS
    # --------------------------------------------------

    metrics = []

    for item in market_data:

        previous = (
            get_previous_market_observations(
                history,
                item["name"]
            )
        )

        metrics.append(
            calculate_metrics(
                item,
                previous
            )
        )

    # --------------------------------------------------
    # 3. OPORTUNIDADES
    # --------------------------------------------------

    opportunities = detect_opportunities(
        metrics
    )

    selected = (
        opportunities[0]
        if opportunities
        else None
    )

    # --------------------------------------------------
    # 4. GUARDAR HISTORICO
    # --------------------------------------------------

    for item in market_data:
        history[
            "market_observations"
        ].append({
            "timestamp": timestamp,
            "name": item["name"],
            "current": item["current"],
            "volume_24h": item.get(
                "volume_24h",
                0
            )
        })

    save_history(history)

    # --------------------------------------------------
    # 5. RESULTADO
    # --------------------------------------------------

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
            "market_snapshot": metrics
        }
    }


if __name__ == "__main__":
    print(
        json.dumps(
            run(),
            ensure_ascii=False
        )
    )
