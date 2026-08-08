import json
from datetime import datetime, timezone


def detect_opportunities(data):
    opportunities = []

    for item in data:
        reference = item["reference"]
        current = item["current"]
        observations = item["observations"]

        if reference <= 0 or current < 0 or observations < 0:
            continue

        discount = (reference - current) / reference

        if discount >= 0.20:
            # Componente de precio: máximo 60 puntos.
            price_score = discount * 60

            # Componente de recurrencia: máximo 40 puntos.
            # 12 observaciones o más = máxima recurrencia.
            recurrence_score = min(observations / 12, 1) * 40

            total_score = round(
                price_score + recurrence_score,
                2
            )

            opportunities.append({
                "name": item["name"],
                "reference": reference,
                "current": current,
                "discount": round(discount, 4),
                "observations": observations,
                "price_score": round(price_score, 2),
                "recurrence_score": round(recurrence_score, 2),
                "score": total_score,
                "signal": "PRICE_DROP"
            })

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return opportunities


def run():
    data = [
        {
            "name": "producto_A",
            "reference": 100,
            "current": 95,
            "observations": 2
        },
        {
            "name": "producto_B",
            "reference": 100,
            "current": 72,
            "observations": 6
        },
        {
            "name": "producto_C",
            "reference": 200,
            "current": 150,
            "observations": 12
        },
        {
            "name": "producto_D",
            "reference": 80,
            "current": 78,
            "observations": 1
        },
        {
            "name": "producto_E",
            "reference": 500,
            "current": 300,
            "observations": 2
        },
    ]

    opportunities = detect_opportunities(data)

    selected_opportunity = (
        opportunities[0] if opportunities else None
    )

    return {
        "runtime": "ATLAS",
        "mode": "DRY_RUN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "READY",
        "detector": {
            "enabled": True,
            "opportunities_found": len(opportunities),
            "action_taken": False,
            "selected_opportunity": selected_opportunity,
            "opportunities": opportunities
        }
    }


if __name__ == "__main__":
    print(json.dumps(run()))
