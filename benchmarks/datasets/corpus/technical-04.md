# Deployment Guide

How to run the collector fleet in production.

## Prerequisites

- Kubernetes 1.29 or newer
- A container registry reachable from the cluster
- Certificates issued by the internal CA

## Installation

### Helm

```bash
helm repo add collectors https://charts.example.com
helm install fleet collectors/fleet --namespace telemetry
```

### Manual Manifests

Apply the rendered manifests in order: namespace, service account, then the
daemon set.

## Configuration

### Resource Limits

| Component | CPU request | Memory limit |
| --- | ---: | ---: |
| agent | 100m | 256 Mi |
| relay | 500m | 1 Gi |
| indexer | 2 | 4 Gi |

### Secrets

Mount the ingest token from a secret; never bake it into the image.

## Upgrades

Run `helm upgrade` with the same values file. The daemon set rolls one node
at a time and waits for drains to settle.

## Rollback

`helm rollback fleet` restores the previous revision. Data written by the
newer version remains readable because the on-disk format is append-only.

## Troubleshooting

Check the relay logs for backpressure first; a stalled relay is the most
common cause of fleet-wide lag.
