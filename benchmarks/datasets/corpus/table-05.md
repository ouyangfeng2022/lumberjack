# Audit Log

Selected entries from the change-management system.

## 2026-03

| Time | Actor | Action | Target | Result |
| --- | --- | --- | --- | --- |
| 09:12 | ops-bot | deploy | gateway@2.7.1 | ok |
| 09:40 | m.okafor | rollback | gateway@2.7.0 | ok |
| 11:05 | l.chen | scale-out | relay pool +4 | ok |
| 13:22 | ops-bot | deploy | relay@1.14.0 | ok |
| 16:48 | s.patel | key-rotate | signing keys | ok |

## 2026-04

| Time | Actor | Action | Target | Result |
| --- | --- | --- | --- | --- |
| 08:03 | ops-bot | deploy | indexer@3.2.0 | ok |
| 10:37 | m.okafor | config | lag baselines | ok |
| 12:51 | ops-bot | deploy | indexer@3.2.1 | failed |
| 12:59 | m.okafor | rollback | indexer@3.2.0 | ok |
| 15:14 | a.dubois | drain | node-142 | ok |
| 17:20 | ops-bot | deploy | indexer@3.2.2 | ok |

## 2026-05

| Time | Actor | Action | Target | Result |
| --- | --- | --- | --- | --- |
| 09:00 | ops-bot | deploy | dashboard@5.0.0 | ok |
| 11:11 | a.dubois | replace-disk | node-097 | ok |
| 14:45 | l.chen | scale-in | relay pool -2 | ok |
| 18:30 | ops-bot | deploy | gateway@2.8.0 | ok |

The failed indexer deploy at 12:51 on April 14 was caused by a missing
migration; the fix shipped in 3.2.2 the same day.
