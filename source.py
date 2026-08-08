import json
from urllib.request import urlopen


SOURCE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"


def fetch_data():
    with urlopen(SOURCE_URL, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_data(raw):
    return [
        {
            "name": name,
            "current": values["usd"]
        }
        for name, values in raw.items()
    ]


if __name__ == "__main__":
    raw = fetch_data()
    data = normalize_data(raw)
    print(json.dumps(data))
