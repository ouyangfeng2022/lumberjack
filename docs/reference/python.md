# Python API

[中文](../zh-CN/reference/python.md)

The package root intentionally exports only `Lumberjack` and `Document`. Import other public components from their dedicated modules.

## Orchestration

::: lumberjack.Lumberjack

## Models

::: lumberjack.models
    options:
      members:
        - Document
        - DocTree
        - DocumentBlock
        - DocumentInline
        - SectionNode
        - ChunkDraft
        - Chunk
        - SplitResult

## Built-in components

::: lumberjack.parser

::: lumberjack.splitter

::: lumberjack.tokenizer

::: lumberjack.block

::: lumberjack.finalizer

::: lumberjack.normalizer

::: lumberjack.transformer

## Extension protocols

::: lumberjack.protocols
