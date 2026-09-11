# Compatibility Matrix

Supported versions for each client library and runtime combination.

## Client Libraries

| Library | 1.x runtime | 2.x runtime | 3.x runtime | Notes |
| --- | --- | --- | --- | --- |
| sdk-python | 1.4+ | 2.0+ | 2.3+ | async requires 2.1+ |
| sdk-node | 1.8+ | 2.0+ | 2.0+ | ESM only on 3.x |
| sdk-go | 1.2+ | 1.2+ | 1.9+ | cgo optional |
| sdk-java | 1.6+ | 2.1+ | 2.1+ | JPMS module on 3.x |
| sdk-ruby | 1.1+ | unsupported | 2.0+ | frozen on 1.x line |
| sdk-php | 1.3+ | unsupported | 2.0+ | |
| sdk-rust | — | 1.0+ | 1.0+ | first shipped for 2.x |

## Browsers

| Browser | WebSocket | WebTransport | Notes |
| --- | --- | --- | --- |
| Chrome 120+ | yes | yes | |
| Firefox 121+ | yes | no | WebTransport behind flag |
| Safari 17+ | yes | no | |
| Edge 120+ | yes | yes | follows Chrome |

## Protocols

| Protocol | Wire format | Auth | Multiplexed |
| --- | --- | --- | --- |
| v1 | JSON | bearer | no |
| v2 | protobuf | mTLS | yes |
| v3 | protobuf | mTLS + OIDC | yes |

Deprecations follow the policy in the release notes document.
