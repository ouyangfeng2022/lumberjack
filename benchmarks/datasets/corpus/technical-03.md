# Release Notes

Quarterly release notes for the streaming platform.

## Release 4.2

### Highlights

The schema registry now validates producers at deploy time, and consumer lag
alerts moved from static thresholds to per-partition baselines.

#### Schema Registry

Deploy-time validation rejects incompatible schemas before they reach the bus.

#### Lag Alerts

Baselines are recomputed hourly from a seven-day rolling window.

### Fixes

- Topic auto-creation respects the namespace quota again.
- The partition rebalancer no longer briefly double-assigns the first
  partition during rolling restarts.

### Deprecations

The legacy `v1/consume` endpoint is removed in this release. Migrate to
`v2/streams`.

## Release 4.1

### Highlights

Exactly-once sinks became generally available, and the dashboard learned to
correlate incidents with deployment markers.

#### Exactly-Once Sinks

Sinks deduplicate on (topic, partition, offset) before writing downstream.

#### Deployment Markers

Markers are exported from the CI pipeline and rendered on every timeline.

### Fixes

- Consumer group metadata no longer grows unboundedly during rebalance storms.
- The metrics exporter survived a serializer regression that dropped labels.

## Release 4.0

### Highlights

The 4.0 line rewrote the control plane on top of the new raft store.

#### Raft Store

Leadership handoff now completes in under a second for clusters of nine
nodes or fewer.

#### Control Plane

All administrative actions are journaled and replayable for audit.
