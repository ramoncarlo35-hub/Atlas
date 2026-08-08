import json
from datetime import datetime, timezone


def detect_opportunities(data):
    opportunities = []

    for item in data:
        if item["current"] < item["reference"]:
            drop = (item["reference"] - item["current"]) / item["reference"]

            if drop >= 0.20:
                opportunities.append({
                    "name": item["name"],
                    "reference": item["reference"],
                    "current": item["current"],
                    "discount": round(drop, 4),
                    "signal": "PRICE_DROP"
                })

    return opportunities


def run():
    # Datos de prueba. Todavía no usamos ninguna fuente externa.
    data = [
        {"name": "producto_A", "reference": 100, "current": 95},
        {"name": "producto_B", "reference": 100, "current": 72},
        {"name": "producto_C", "reference": 200, "current": 150},
        {"name": "producto_D", "reference": 80, "current": 78},
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
