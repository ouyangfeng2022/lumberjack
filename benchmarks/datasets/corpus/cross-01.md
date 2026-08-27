# Observability Guide

How the platform exposes its internal state.

## Metrics

Counters track totals, gauges track current values, and histograms track
distributions. All three carry the same labels: service, region, and shard.

## Traces

Every request receives a trace id at the edge. The id propagates through
every hop and is attached to logs, spans, and any error returned to the
caller.

## Logs

| Level | When to use | Retention |
| --- | --- | ---: |
| debug | local development | 1 day |
| info | routine operation | 14 days |
| warn | recoverable anomalies | 30 days |
| error | failed operations | 90 days |

## Dashboards

The golden dashboard pairs traffic with latency and errors; every service
must appear on it before it takes production traffic.
