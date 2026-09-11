# Security Baseline

The minimum every service must meet before production.

## Transport

TLS 1.3 for external traffic, mTLS between services. Certificates rotate
every ninety days.

## Secrets

No secrets in images or environment dumps. Everything lives in the secret
store with per-service scopes.

## Dependencies

Automated scans run on every merge. Critical findings block the release
until patched or formally accepted.

## Access

| Capability | Who grants | Review cadence |
| --- | --- | ---: |
| production read | team lead | 90 days |
| production write | security | 30 days |
| key management | security | 30 days |

## Reporting

Suspected vulnerabilities go to the security inbox, triaged within one
business day.
