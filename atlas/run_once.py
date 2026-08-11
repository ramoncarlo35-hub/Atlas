import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT_DIR / "history.json"
SOURCE_FILE = ROOT_DIR / "source.py"


def load_history():
    if not HISTORY_FILE.exists():
        return {
            "observations": [],
            "market_observations": []
        }

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    # Compatibilidad con el history.json que ya tenemos
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
        raise RuntimeError("source.py no devolvió datos.")

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


def get_previous_market_observations(history, name):
    return [
        observation
        for observation in history["market_observations"]
        if observation["name"] == name
    ]


def calculate_metrics(item, previous):
    current = float(item["current"])
    volume_24h = float(item.get("volume_24h", 0))

    if previous:
        reference = max(
            [float(observation["current"]) for observation in previous]
            + [current]
        )

        previous_current = float(previous[-1]["current"])

        movement = (
            (current - previous_current)
            / previous_current
            if previous_current > 0
            else 0
        )

        observations = len(previous) + 1

    else:
        reference = current
        movement = 0
        observations = 1

    discount = (
        (reference - current) / reference
        if reference > 0
        else 0
    )

    # Caída respecto al máximo histórico observado
    drop_score = min(discount * 100, 40)

    # Movimiento reciente.
    # Se pondera moderadamente para no confundir volatilidad
    # puntual con una oportunidad real.
    momentum_score = min(abs(movement) * 100, 20)

    # Más observaciones = más confianza en la serie histórica.
    recurrence_factor = min(
        1 + observations * 0.02,
        1.5
    )

    score = round(
        (drop_score + momentum_score)
        * recurrence_factor,
        2
    )

    if movement > 0.001:
        direction = "UP"
    elif movement < -0.001:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return {
        "name": item["name"],
        "reference": round(reference, 2),
        "current": round(current, 2),
        "volume_24h": round(volume_24h, 2),
        "discount": round(discount, 4),
        "movement": round(movement, 4),
        "observations": observations,
        "direction": direction,
        "drop_score": round(drop_score, 2),
        "momentum_score": round(momentum_score, 2),
        "recurrence_factor": round(recurrence_factor, 2),
        "score": score
    }


def detect_opportunities(metrics):
    opportunities = []

    for item in metrics:
        # Por ahora exigimos una caída mínima del 5%.
        # Esto evita convertir pequeñas oscilaciones normales
        # de BTC/ETH en falsas oportunidades.
        if item["discount"] >= 0.05:
            opportunities.append({
                **item,
                "signal": "PRICE_DROP"
            })

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

    # 1. Obtener datos reales
    market_data = load_real_market_data()

    # 2. Calcular métricas utilizando exclusivamente
    #    el histórico real de mercado
    metrics = []

    for item in market_data:
        previous = get_previous_market_observations(
            history,
            item["name"]
        )

        metrics.append(
            calculate_metrics(
                item,
                previous
            )
        )

    # 3. Detectar oportunidades
    opportunities = detect_opportunities(metrics)

    # 4. Guardar observaciones reales
    for item in market_data:
        history["market_observations"].append({
            "timestamp": timestamp,
            "name": item["name"],
            "current": item["current"],
            "volume_24h": item.get("volume_24h", 0)
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
