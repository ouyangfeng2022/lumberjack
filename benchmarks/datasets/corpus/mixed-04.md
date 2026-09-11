# Bilingual Release Brief

发布摘要 / release summary for build 2.7.

## 性能 / Performance

P95 延迟从 412ms 降到 388ms。P95 latency moved from 412ms to 388ms after the
connection-pool fix.

## 稳定性 / Stability

重连风暴不再扩散到相邻节点。Reconnect storms no longer spread to neighbor
nodes.

## 变更 / Changes

- 连接池上限调整 / raised the connection pool ceiling
- 空闲超时缩短 / shortened the idle timeout
- 日志脱敏 / redacted tokens from access logs

## 已知问题 / Known Issues

高并发下的内存峰值仍在观察中。The memory peak under high concurrency is
still under observation.

## 下一步 / Next Steps

下周发布 2.8,包含新的健康检查与指标。Ship 2.8 next week with the new
health checks and gauges.
