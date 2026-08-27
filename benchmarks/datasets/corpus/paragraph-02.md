# On Backpressure

## The Problem

Every queue in a data system eventually meets a producer that is faster than its consumer. When that happens the honest options are few: buffer, shed, or slow the producer down. Buffering is the default reflex and the most dangerous one, because memory is finite and queues that grow without bound do not fail politely; they fail at the worst possible moment, taking with them everything that shares the process. Shedding load is honest but needs a policy that users can live with, which usually means deciding in advance which requests matter most, a decision that is easier to defer than to make.

## The Middle Path

Backpressure is the third option: propagate the slowdown upstream until the producer feels it. Done well, it is invisible; the system simply runs at the speed of its slowest stage and stays there. Done badly, it amplifies the original problem, because a producer that is throttled may retry aggressively, converting a slowdown into a stampede. The difference between the two outcomes is almost always timeout discipline: how quickly a stalled consumer reports its stall, and how calmly the producer reacts to the report.

## In Practice

Our relay exposes two gauges to make this observable: queue depth on the ingest side and downstream flush latency on the other. The alert that matters fires when depth rises while flush latency stays flat, which is the signature of a consumer that stopped consuming rather than one that is merely slow. When that fires, the runbook says to check the sink first, the network second, and the relay itself last, in that order, because the historical distribution of causes is heavily weighted toward the first item.
