# Why Idempotency Is a Storage Concern

## The Usual Story

Idempotency is usually presented as a property of handlers: make the operation safe to retry, and delivery duplicates stop mattering. That framing is correct but incomplete, because the hard part of idempotency is rarely the operation itself; it is remembering, durably and atomically, that the operation already happened. A handler that checks a flag and then writes is idempotent only if the check and the write are one transaction, and the moment those two steps live in different systems, the guarantee quietly evaporates under exactly the conditions that produce retries: timeouts, partial failures, and rebalances.

## Where It Breaks

Consider a consumer that acknowledges a message, then commits its projection. If the process dies between those two steps, the message is never reprocessed and the projection is permanently behind. Reverse the order and you get the opposite disease: the projection is written twice for any redelivery. Both failure modes come from splitting one logical step across two durability domains, and no amount of defensive coding in the handler fixes that; only moving the boundary does.

## The Resolution

The durable answer is to make the side effect and the deduplication key live in the same transactional store, so that the second attempt becomes a no-op by construction rather than by hope. Where that is impossible, the fallback is reconciliation: accept that the two domains will drift, measure the drift continuously, and repair it on a schedule. The drift-then-repair design is not a defeat; it is an honest accounting of what the architecture can actually promise, and it is far cheaper than the outages that come from assuming a guarantee nobody implemented.
