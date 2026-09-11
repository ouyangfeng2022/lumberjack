# Service Configuration

Reference configuration for the relay service.

## Main Config

```yaml
listen: "0.0.0.0:9611"
workers: 8

ingest:
  max_body_bytes: 8388608
  flush_interval_ms: 250

downstream:
  kind: kafka
  brokers:
    - broker-1.internal:9092
    - broker-2.internal:9092
  topic_prefix: telemetry.
  compression: zstd
```

## Feature Flags

```toml
[features]
exactly_once_sinks = true
webtransport = false

[features.baselines]
window_days = 7
recompute_interval_hours = 1
```

## Validation

```python
from pathlib import Path

import yaml


def load(path: str) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if int(config["ingest"]["max_body_bytes"]) <= 0:
        raise ValueError("ingest.max_body_bytes must be positive")
    if int(config["workers"]) < 1:
        raise ValueError("workers must be at least 1")
    return config
```

The validator runs as a pre-deploy check; a config that fails validation is
never pushed to the fleet.
