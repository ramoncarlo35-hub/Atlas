import json
from datetime import datetime, timezone


def detect_opportunities(data):
    opportunities = []

    for item in data:
        reference = item["reference"]
        current = item["current"]

        if reference <= 0 or current < 0:
            continue

        discount = (reference - current) / reference

        if discount >= 0.20:
            # Puntuación inicial:
            # 20% de caída = 20 puntos
            # 50% de caída = 50 puntos
            score = round(discount * 100, 2)

            opportunities.append({
                "name": item["name"],
                "reference": reference,
                "current": current,
                "discount": round(discount, 4),
                "score": score,
                "signal": "PRICE_DROP"
            })

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return opportunities


def run():
    data = [
        {"name": "producto_A", "reference": 100, "current": 95},
        {"name": "producto_B", "reference": 100, "current": 72},
        {"name": "producto_C", "reference": 200, "current": 150},
        {"name": "producto_D", "reference": 80, "current": 78},
        {"name": "producto_E", "reference": 500, "current": 300},
    ]

    opportunities = detect_opportunities(data)

    return {
        "runtime": "ATLAS",
        "mode": "DRY_RUN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "READY",
        "detector": {
            "enabled": True,
            "opportunities_found": len(opportunities),
            "action_taken": False,
            "opportunities": opportunities
        }
    }


if __name__ == "__main__":
    print(json.dumps(run()))
