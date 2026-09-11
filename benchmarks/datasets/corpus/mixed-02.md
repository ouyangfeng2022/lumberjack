# 部署手册 / Deployment Runbook

本文档同时提供中文和英文,便于值班同学快速定位。

## 环境准备 / Prerequisites

准备一个干净的 namespace 和有效的服务账号。Prepare a clean namespace and a
valid service account before continuing.

## 步骤 / Steps

### 一、安装 / Install

使用 Helm 安装基础组件。Install the base chart with Helm.

### 二、配置 / Configure

按需覆盖 `workers` 与 `max_body_bytes`。Override `workers` and
`max_body_bytes` as needed.

### 三、验证 / Verify

检查 readiness 端点,然后观察五分钟的延迟指标。Check the readiness
endpoint, then watch the latency gauges for five minutes.

## 回滚 / Rollback

执行回滚前先确认当前版本号。Confirm the current revision before running the
rollback command.

## 常见问题 / Common Issues

**问:pod 一直 Pending 怎么办?**
Check the node selector first; it is the most common cause.

**问:指标缺失正常吗?**
缺失超过两分钟即不正常。Missing for more than two minutes is not normal.
