import json
from datetime import datetime, timezone
print(json.dumps({"runtime":"ATLAS","mode":"DRY_RUN",
"timestamp":datetime.now(timezone.utc).isoformat(),"status":"READY"}))
