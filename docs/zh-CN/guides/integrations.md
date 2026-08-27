# RAG 框架集成

[English](../../guides/integrations.md)

Lumberjack 将框架依赖保持为可选项。所有 adapter 使用 `Chunk.body` 作为框架对象的主文本，并将标题、token 计数和来源位置以 JSON 安全的 metadata 保留。

集成分为两层：

- **转换助手**（急切导出）将切分完成的 `Chunk` 转成框架对象：
  `build_*_index`/`build_*_vectorstore`、`to_*_document(s)`、
  `to_llamaindex_node(s)`。
- **原生管线组件**（惰性导出）把 Lumberjack 接入各框架自己的摄取管线，替换内置切分器：
  - LlamaIndex —— `LumberjackNodeParser`（用于 `IngestionPipeline`/`VectorStoreIndex` 的 `NodeParser`）与 `LumberjackReader`（用于 Markdown/HTML/DOCX 的 `BaseReader`）。
  - LangChain —— `LumberjackTextSplitter`（`TextSplitter`）与 `LumberjackDocumentTransformer`（用于 `langchain.indexing` 的 `BaseDocumentTransformer`）。
  - Haystack —— `LumberjackDocumentSplitter`（替换内置 `DocumentSplitter` 的 `@component`）。

每个组件都将 Lumberjack provenance（标题路径、token 计数、来源行号）作为框架 metadata 保留，生成确定性 chunk id 以便增量重建索引，并沿用与 CLI 相同的 `max_tokens` / `splitter` / `tokenizer` / `block_options` 配置。

## LangChain

```bash
pip install 'lumberjack-py[langchain]'
```

```python
from langchain_core.embeddings import DeterministicFakeEmbedding
from lumberjack import Lumberjack
from lumberjack.integrations import build_langchain_vectorstore

chunks = Lumberjack().saw("# Guide\n\nAdapter body").chunks
vector_store = build_langchain_vectorstore(
    chunks, embeddings=DeterministicFakeEmbedding(size=8)
)
documents = vector_store.similarity_search("adapter", k=1)
```

### 可直接运行的完整 Demo

```bash
uv sync --extra langchain
uv run python examples/langchain_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

该 Demo 覆盖从 `Lumberjack.saw()` 到真实 LangChain `InMemoryVectorStore`、检索以及 runnable RAG chain 的完整路径。它使用 LangChain 的确定性 fake embedding 与 LLM，因此可离线运行；替换为已配置的生产 integration 时无需改变 adapter 边界。

### 替换 LangChain 的文本切分器

`LumberjackTextSplitter` 是 `TextSplitter` 的即插即用替代 —— 可在任何接受 `RecursiveCharacterTextSplitter` 的位置使用。`split_text()` 返回结构感知的 chunk；`create_documents` / `split_documents` 保留每个输入文档的 metadata，并为每个产出的文档附加 Lumberjack provenance。

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 之前：
splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=0)

# 之后：
from lumberjack.integrations import LumberjackTextSplitter

splitter = LumberjackTextSplitter(max_tokens=800)

documents = splitter.split_documents(loaded_documents)
```

`LumberjackDocumentTransformer` 通过 LangChain 的 indexing API（`langchain.indexing`）暴露同样的切分能力，并生成确定性文档 id（`<source id>:<chunk id>`），使重复的 indexing 保持增量。

## LlamaIndex

```bash
pip install 'lumberjack-py[llama-index]'
```

```python
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms.mock import MockLLM
from lumberjack import Lumberjack
from lumberjack.integrations import build_llamaindex_index

chunks = Lumberjack().saw("# Guide\n\nAdapter body").chunks
index = build_llamaindex_index(chunks, embed_model=MockEmbedding(embed_dim=8))
hits = index.as_retriever(similarity_top_k=1).retrieve("adapter")
response = index.as_query_engine(llm=MockLLM()).query("What is this about?")
```

默认会将全部 Lumberjack metadata 排除在 LlamaIndex 的 embedding 与 LLM 内容之外，因此 node 文本严格保持为 `Chunk.body`；metadata 仍可用于过滤和来源追踪。`MockEmbedding` 与 `MockLLM` 使示例可离线运行；生产环境只需在相同的 index、retriever 与 query 接口中传入已配置的 LlamaIndex embedding model 和 LLM。

### 可直接运行的完整 Demo

仓库提供了离线端到端 Demo：它拆分真实文件，构建 `VectorStoreIndex`，检索 node，执行 query engine，并将命中的来源 metadata 以 JSON 输出。

```bash
git clone https://github.com/ouyangfeng2022/lumberjack.git
cd lumberjack
uv sync --extra llama-index
uv run python examples/llama_index_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

它使用 LlamaIndex 的 `MockEmbedding` 与 `MockLLM`，因此可离线、可复现地运行。生产环境只需在 `examples/llama_index_demo.py` 中替换这两个对象为已配置的 LlamaIndex provider integration；Lumberjack 到 index、retriever、query engine 的流程无需改变。

### 替换 LlamaIndex 的 node parser

`LumberjackNodeParser` 是原生 `NodeParser`：把它放进 `IngestionPipeline.transformations`（或直接传给 `VectorStoreIndex`）即可替代 `SentenceSplitter` / `MarkdownNodeParser`。它逐个解析并结构切分源 node，产出的 node 带有确定性 id（`<source id>:<n>`）、Lumberjack provenance metadata，以及用于检索与重建索引的 `SOURCE`/`PREVIOUS`/`NEXT` 关系。

```python
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.embeddings import MockEmbedding
from lumberjack.integrations import LumberjackNodeParser

pipeline = IngestionPipeline(
    transformations=[
        LumberjackNodeParser(max_tokens=800, heading_context=True),
        MockEmbedding(embed_dim=8),
    ],
)
nodes = pipeline.run(documents=loaded_documents)
```

设置 `heading_context=True` 会在每个 node 文本前加渲染后的标题面包屑，让 embedding 看到章节上下文。

### 用同一个 reader 加载 Markdown / HTML / DOCX

`SimpleDirectoryReader` 无法把 DOCX 或 HTML/XML 读成结构感知的文本。`LumberjackReader` 是一个 `BaseReader`，用 Lumberjack 解析每个受支持的文件并重新渲染为规范 Markdown，保留标题、表格、列表和代码块；front matter 作为文档 metadata 附加。把它的输出直接喂给 `LumberjackNodeParser`，即可让所有格式走同一条结构感知切分路径：

```python
from lumberjack.integrations import LumberjackNodeParser, LumberjackReader

reader = LumberjackReader()
documents = reader.load_data("handbook.docx")
nodes = LumberjackNodeParser(max_tokens=800).get_nodes_from_documents(documents)
```

### 混合语料与已拍平来源

对结构已被上游破坏的来源（例如 PDF 文本抽取），可传入 fallback parser 与 `fallback_suffixes`；这些文件走 fallback，Markdown/HTML 仍走 Lumberjack 路径：

```python
from llama_index.core.node_parser import SentenceSplitter
from lumberjack.integrations import LumberjackNodeParser

parser = LumberjackNodeParser(
    max_tokens=800,
    fallback=SentenceSplitter(chunk_size=800, chunk_overlap=0),
    fallback_suffixes=(".pdf", ".txt"),
)
```

## Haystack

```bash
pip install 'lumberjack-py[haystack]'
```

```python
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from lumberjack import Lumberjack
from lumberjack.integrations import build_haystack_document_store

chunks = Lumberjack().saw("# Guide\n\nAdapter body").chunks
store = build_haystack_document_store(chunks)
documents = InMemoryBM25Retriever(document_store=store).run(query="adapter")["documents"]
```

### 可直接运行的完整 Demo

```bash
uv sync --extra haystack
uv run python examples/haystack_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

该 Demo 将最终 Lumberjack Chunk 写入真实 Haystack `InMemoryDocumentStore`，运行包含 `InMemoryBM25Retriever` 的 `Pipeline`，并构建 RAG prompt，同时输出命中内容的 provenance metadata。

### 替换 Haystack 的 document splitter

`LumberjackDocumentSplitter` 是与内置 `DocumentSplitter` 相同 `documents` 输入/输出约定的 `@component`。把它接入 `Pipeline`（例如放在 `MarkdownToDocument` / `HTMLToDocument` 之后）；输出文档保留源 meta，附加 Lumberjack provenance，id 形如 `<source id>:<chunk id>`。

```python
from haystack import Pipeline
from haystack.components.converters import MarkdownToDocument
from lumberjack.integrations import LumberjackDocumentSplitter

pipeline = Pipeline()
pipeline.add_component("converter", MarkdownToDocument())
pipeline.add_component("splitter", LumberjackDocumentSplitter(max_tokens=800))
pipeline.connect("converter", "splitter")
```

## 兼容性

CI 在 Python 3.11 上同时测试声明的最低版本和当前 resolver 选定版本：

| 框架 | 已支持且已测试的最低版本 | 当前锁定的测试版本 |
| --- | --- | --- |
| LangChain | `langchain-core==0.3.0`、`langchain-text-splitters==0.3.0` | `1.5.6` |
| LlamaIndex | `llama-index-core==0.12.0` | `0.14.24` |
| Haystack | `haystack-ai==2.0.0` | `3.1.0` |

`langchain` extra 现在还会安装 `langchain-text-splitters`，原生切分组件惰性导入它。核心 `lumberjack-py` 安装不依赖这些框架。
