import json
from pathlib import Path
from statistics import mean, pstdev


# backtest.py está en la raíz del repositorio Atlas.
ROOT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = ROOT_DIR / "history.json"

WINDOW_SIZE = 12

ANOMALY_Z_THRESHOLD = -1.5
VOLUME_CONFIRMATION_RATIO = 1.20

FORWARD_WINDOW = 3

MIN_OBSERVATIONS_FOR_BACKTEST = 12


def load_history():
    if not HISTORY_FILE.exists():
        return {
            "observations": [],
            "market_observations": []
        }

    with open(
        HISTORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        history = json.load(file)

    history.setdefault(
        "observations",
        []
    )

    history.setdefault(
        "market_observations",
        []
    )

    return history


def group_by_asset(observations):
    grouped = {}

    for observation in observations:
        name = observation["name"]

        grouped.setdefault(
            name,
            []
        ).append(observation)

    return grouped


def calculate_z_score(prices, current):
    if len(prices) < 3:
        return 0.0

    average = mean(prices)
    deviation = pstdev(prices)

    if deviation == 0:
        return 0.0

    return (
        current - average
    ) / deviation


def calculate_volume_ratio(
    volumes,
    current_volume
):
    valid_volumes = [
        float(volume)
        for volume in volumes
        if float(volume) > 0
    ]

    if not valid_volumes:
        return 1.0

    average_volume = mean(
        valid_volumes
    )

    if average_volume <= 0:
        return 1.0

    return (
        current_volume
        / average_volume
    )


def reconstruct_signal(
    observations,
    index
):
    """
    Reconstruye retrospectivamente
    la señal que Atlas habría generado.
    """

    if index < 3:
        return None

    start = max(
        0,
        index - WINDOW_SIZE
    )

    previous = observations[
        start:index
    ]

    prices = [
        float(item["current"])
        for item in previous
    ]

    volumes = [
        float(
            item.get(
                "volume_24h",
                0
            )
        )
        for item in previous
    ]

    current = float(
        observations[index]["current"]
    )

    current_volume = float(
        observations[index].get(
            "volume_24h",
            0
        )
    )

    z_score = calculate_z_score(
        prices,
        current
    )

    volume_ratio = calculate_volume_ratio(
        volumes,
        current_volume
    )

    if (
        z_score <= ANOMALY_Z_THRESHOLD
        and volume_ratio >= VOLUME_CONFIRMATION_RATIO
    ):
        return {
            "signal": "ANOMALOUS_DROP",
            "z_score": round(
                z_score,
                3
            ),
            "volume_ratio": round(
                volume_ratio,
                3
            )
        }

    return {
        "signal": "NORMAL_MOVEMENT",
        "z_score": round(
            z_score,
            3
        ),
        "volume_ratio": round(
            volume_ratio,
            3
        )
    }


def calculate_future_return(
    observations,
    signal_index
):
    """
    Calcula el rendimiento posterior
    utilizando FORWARD_WINDOW observaciones.
    """

    future_index = (
        signal_index
        + FORWARD_WINDOW
    )

    # No evaluamos señales que todavía
    # no tienen suficientes datos futuros.
    if future_index >= len(observations):
        return None

    current_price = float(
        observations[
            signal_index
        ]["current"]
    )

    future_price = float(
        observations[
            future_index
        ]["current"]
    )

    if current_price <= 0:
        return None

    return (
        future_price - current_price
    ) / current_price


def analyze_asset(
    name,
    observations
):
    signal_counts = {
        "NORMAL_MOVEMENT": 0,
        "ANOMALOUS_DROP": 0
    }

    signals = []

    usable_observations = 0

    signals_with_valid_forward_window = 0

    for index in range(
        len(observations)
    ):
        result = reconstruct_signal(
            observations,
            index
        )

        if result is None:
            continue

        usable_observations += 1

        signal = result["signal"]

        signal_counts[
            signal
        ] += 1

        if signal == "ANOMALOUS_DROP":

            future_return = (
                calculate_future_return(
                    observations,
                    index
                )
            )

            if future_return is not None:
                signals_with_valid_forward_window += 1

            signals.append({
                "index": index,
                "timestamp": observations[
                    index
                ].get(
                    "timestamp"
                ),
                "price": observations[
                    index
                ]["current"],
                "z_score": result[
                    "z_score"
                ],
                "volume_ratio": result[
                    "volume_ratio"
                ],
                "future_return": (
                    round(
                        future_return,
                        6
                    )
                    if future_return is not None
                    else None
                )
            })

    valid_returns = [
        item["future_return"]
        for item in signals
        if item["future_return"] is not None
    ]

    if valid_returns:

        average_future_return = mean(
            valid_returns
        )

        positive_outcomes = sum(
            1
            for value in valid_returns
            if value > 0
        )

        success_rate = (
            positive_outcomes
            / len(valid_returns)
        )

    else:

        average_future_return = None
        success_rate = None

    observations_count = len(
        observations
    )

    if (
        observations_count
        < MIN_OBSERVATIONS_FOR_BACKTEST
    ):
        sample_status = (
            "INSUFFICIENT_SAMPLE"
        )

    elif signals_with_valid_forward_window < 3:
        sample_status = (
            "TOO_FEW_VALID_SIGNALS"
        )

    else:
        sample_status = (
            "SAMPLE_AVAILABLE"
        )

    return {
        "name": name,

        "observations_analyzed": (
            observations_count
        ),

        "usable_observations": (
            usable_observations
        ),

        "signals_found": len(
            signals
        ),

        "signals_with_valid_forward_window": (
            signals_with_valid_forward_window
        ),

        "signal_counts": signal_counts,

        "sample_status": sample_status,

        "average_future_return": (
            round(
                average_future_return,
                6
            )
            if average_future_return is not None
            else None
        ),

        "positive_outcome_rate": (
            round(
                success_rate,
                4
            )
            if success_rate is not None
            else None
        ),

        "signals": signals
    }


def run():

    history = load_history()

    observations = history.get(
        "market_observations",
        []
    )

    grouped = group_by_asset(
        observations
    )

    assets = []

    total_observations = 0

    total_usable_observations = 0

    total_signals = 0

    total_valid_signals = 0

    all_returns = []

    for name, asset_observations in grouped.items():

        result = analyze_asset(
            name,
            asset_observations
        )

        assets.append(
            result
        )

        total_observations += (
            result[
                "observations_analyzed"
            ]
        )

        total_usable_observations += (
            result[
                "usable_observations"
            ]
        )

        total_signals += (
            result[
                "signals_found"
            ]
        )

        total_valid_signals += (
            result[
                "signals_with_valid_forward_window"
            ]
        )

        for signal in result[
            "signals"
        ]:

            if (
                signal[
                    "future_return"
                ] is not None
            ):
                all_returns.append(
                    signal[
                        "future_return"
                    ]
                )

    if all_returns:

        overall_average_return = mean(
            all_returns
        )

        overall_positive_rate = (
            sum(
                1
                for value in all_returns
                if value > 0
            )
            / len(all_returns)
        )

    else:

        overall_average_return = None

        overall_positive_rate = None

    if not assets:

        sample_status = "NO_DATA"

        explanation = (
            "No market data available."
        )

    elif any(
        asset["sample_status"]
        == "INSUFFICIENT_SAMPLE"
        for asset in assets
    ):

        sample_status = (
            "INSUFFICIENT_SAMPLE"
        )

        explanation = (
            "Atlas needs more historical "
            "observations before signal "
            "performance can be evaluated."
        )

    elif total_valid_signals < 3:

        sample_status = (
            "TOO_FEW_VALID_SIGNALS"
        )

        explanation = (
            "Atlas has too few signals "
            "with a valid forward window "
            "to evaluate performance."
        )

    else:

        sample_status = (
            "SAMPLE_AVAILABLE"
        )

        explanation = (
            "Atlas has enough observations "
            "and valid signals to evaluate "
            "performance."
        )

    return {
        "runtime": "ATLAS",

        "mode": "BACKTEST",

        "status": "READY",

        "parameters": {
            "window_size": WINDOW_SIZE,

            "anomaly_z_threshold": (
                ANOMALY_Z_THRESHOLD
            ),

            "volume_confirmation_ratio": (
                VOLUME_CONFIRMATION_RATIO
            ),

            "forward_window": (
                FORWARD_WINDOW
            ),

            "minimum_observations_for_backtest": (
                MIN_OBSERVATIONS_FOR_BACKTEST
            )
        },

        "sample_quality": {
            "status": sample_status,

            "ready_for_signal_evaluation": (
                sample_status
                == "SAMPLE_AVAILABLE"
            ),

            "explanation": explanation
        },

        "summary": {
            "assets_analyzed": len(
                assets
            ),

            "observations_analyzed": (
                total_observations
            ),

            "usable_observations": (
                total_usable_observations
            ),

            "signals_found": (
                total_signals
            ),

            "signals_with_valid_forward_window": (
                total_valid_signals
            ),

            "overall_average_future_return": (
                round(
                    overall_average_return,
                    6
                )
                if overall_average_return is not None
                else None
            ),

            "overall_positive_outcome_rate": (
                round(
                    overall_positive_rate,
                    4
                )
                if overall_positive_rate is not None
                else None
            )
        },

        "assets": assets
    }


if __name__ == "__main__":
    print(
        json.dumps(
            run(),
            ensure_ascii=False,
            indent=2
        )
    )
