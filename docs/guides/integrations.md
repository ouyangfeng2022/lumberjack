# RAG framework integrations

[中文](../zh-CN/guides/integrations.md)

Lumberjack keeps framework dependencies optional. Every adapter uses
`Chunk.body` as the framework object's primary text and preserves headings,
token counts, and source locations as JSON-safe metadata.

There are two integration tiers:

- **Conversion helpers** (eager exports) turn finished Lumberjack `Chunk`s
  into framework objects: `build_*_index`/`build_*_vectorstore`,
  `to_*_document(s)`, `to_llamaindex_node(s)`.
- **Native pipeline components** (lazy exports) plug Lumberjack into each
  framework's own ingestion pipeline, replacing the built-in splitter:
  - LlamaIndex — `LumberjackNodeParser` (a `NodeParser` for
    `IngestionPipeline`/`VectorStoreIndex`) and `LumberjackReader` (a
    `BaseReader` for Markdown/HTML/DOCX).
  - LangChain — `LumberjackTextSplitter` (a `TextSplitter`) and
    `LumberjackDocumentTransformer` (a `BaseDocumentTransformer` for
    `langchain.indexing`).
  - Haystack — `LumberjackDocumentSplitter` (a `@component` replacing the
    built-in `DocumentSplitter`).

Every component keeps Lumberjack provenance (heading path, token counts,
source line ranges) as framework metadata, attaches deterministic chunk ids
so re-indexing stays incremental, and is constructed from the same
`max_tokens` / `splitter` / `tokenizer` / `block_options` options as the CLI.

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

### Complete runnable demo

```bash
uv sync --extra langchain
uv run python examples/langchain_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

The demo runs the full path from `Lumberjack.saw()` through an actual LangChain
`InMemoryVectorStore`, retrieval, and a runnable RAG chain. It uses LangChain's
deterministic fake embedding and LLM so that it remains offline; replace those
with configured production integrations without changing the adapter boundary.

### Replacing LangChain's text splitter

`LumberjackTextSplitter` is a drop-in `TextSplitter` — use it anywhere
`RecursiveCharacterTextSplitter` is accepted. `split_text()` returns
structure-aware chunks, while `create_documents` / `split_documents` keep each
input document's metadata and attach Lumberjack provenance to every produced
document.

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Before:
splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=0)

# After:
from lumberjack.integrations import LumberjackTextSplitter

splitter = LumberjackTextSplitter(max_tokens=800)

documents = splitter.split_documents(loaded_documents)
```

`LumberjackDocumentTransformer` exposes the same splitting through LangChain's
indexing API (`langchain.indexing`), with deterministic document ids
(`<source id>:<chunk id>`) so repeated indexing runs stay incremental.

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

All Lumberjack metadata is excluded from LlamaIndex embedding and LLM content
by default, so the node text remains exactly `Chunk.body` while metadata stays
available for filtering and provenance. `MockEmbedding` and `MockLLM` make the
example self-contained; production code should pass its configured LlamaIndex
embedding model and LLM to the same index/retrieval/query interfaces.

### Complete runnable demo

The repository includes an offline, end-to-end demo: it splits a real file,
builds a `VectorStoreIndex`, retrieves nodes, runs a query engine, and prints
the retrieved source metadata as JSON.

```bash
git clone https://github.com/ouyangfeng2022/lumberjack.git
cd lumberjack
uv sync --extra llama-index
uv run python examples/llama_index_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

It uses LlamaIndex's `MockEmbedding` and `MockLLM` for reproducible offline
execution. Replace those two objects in `examples/llama_index_demo.py` with
your production LlamaIndex provider integrations; the Lumberjack-to-index,
retriever, and query-engine flow stays unchanged.

### Replacing LlamaIndex's node parser

`LumberjackNodeParser` is a native `NodeParser`: put it in
`IngestionPipeline.transformations` (or pass it directly to
`VectorStoreIndex`) instead of `SentenceSplitter` / `MarkdownNodeParser`.
It parses and structure-splits each source node, and its output nodes keep
deterministic ids (`<source id>:<n>`), Lumberjack provenance metadata, and
`SOURCE`/`PREVIOUS`/`NEXT` relationships for retrieval and re-indexing.

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

Set `heading_context=True` to prefix each node text with its rendered heading
breadcrumb so embeddings see the section context.

### Emitting real section parents for `AutoMergingRetriever`

Set `emit_parents=True` to also emit one parent `TextNode` per real heading
section (grouping the leaf chunks under that section) and link leaves to their
parent and parents to their leaves via `PARENT`/`CHILD` relationships. This
replaces LlamaIndex's `HierarchicalNodeParser` (which fakes parents with
mechanical token-window chunks) with the document's actual section boundaries:
the parent text is the full section, so when `AutoMergingRetriever` hits
several chunks of one section it returns the whole section.

```python
from llama_index.core import VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.storage.storage_context import StorageContext
from lumberjack.integrations import LumberjackNodeParser

nodes = LumberjackNodeParser(max_tokens=512, emit_parents=True).get_nodes_from_documents(documents)
storage = StorageContext.from_defaults()
index = VectorStoreIndex(nodes=nodes, storage_context=storage, embed_model=embed_model)
retriever = AutoMergingRetriever(
    vector_retriever=index.as_retriever(similarity_top_k=4),
    storage_context=storage,
)
hits = retriever.retrieve(query)
```

Parent node ids are deterministic (`<source id>:parent:<hash>`), so re-indexing
stays incremental.

### Loading Markdown / HTML / DOCX with one reader

`SimpleDirectoryReader` cannot read DOCX or HTML/XML into structure-aware text.
`LumberjackReader` is a `BaseReader` that parses each supported file with
Lumberjack and re-renders it as canonical Markdown, preserving headings,
tables, lists, and code blocks; front matter is attached as document metadata.
Feed its output straight into `LumberjackNodeParser` so every format flows
through the same structure-aware splitting path:

```python
from lumberjack.integrations import LumberjackNodeParser, LumberjackReader

reader = LumberjackReader()
documents = reader.load_data("handbook.docx")
nodes = LumberjackNodeParser(max_tokens=800).get_nodes_from_documents(documents)
```

### Mixed corpora and pre-flattened sources

For sources whose structure was already destroyed upstream (for example PDF
text extraction), pass a fallback parser plus `fallback_suffixes`; those files
are routed to the fallback while Markdown/HTML stay on the Lumberjack path:

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

### Complete runnable demo

```bash
uv sync --extra haystack
uv run python examples/haystack_demo.py tests/fixtures/markdown/sample.md \
  --query "What does this document explain?"
```

The demo writes final Lumberjack chunks to an actual Haystack
`InMemoryDocumentStore`, runs a `Pipeline` with `InMemoryBM25Retriever`, and
builds the resulting RAG prompt while printing retrieved provenance metadata.

### Replacing Haystack's document splitter

`LumberjackDocumentSplitter` is a `@component` with the same `documents`
input/output contract as the built-in `DocumentSplitter`. Wire it into a
`Pipeline` (for example after `MarkdownToDocument` / `HTMLToDocument`); output
documents keep the source meta, gain Lumberjack provenance, and get ids of the
form `<source id>:<chunk id>`.

```python
from haystack import Pipeline
from haystack.components.converters import MarkdownToDocument
from lumberjack.integrations import LumberjackDocumentSplitter

pipeline = Pipeline()
pipeline.add_component("converter", MarkdownToDocument())
pipeline.add_component("splitter", LumberjackDocumentSplitter(max_tokens=800))
pipeline.connect("converter", "splitter")
```

## Compatibility

CI tests the declared minimums and the current resolver-selected releases on
Python 3.11:

| Framework | Supported and tested minimum | Current locked test version |
| --- | --- | --- |
| LangChain | `langchain-core==0.3.0`, `langchain-text-splitters==0.3.0` | `1.5.6` |
| LlamaIndex | `llama-index-core==0.12.0` | `0.14.24` |
| Haystack | `haystack-ai==2.0.0` | `3.1.0` |

The `langchain` extra now also installs `langchain-text-splitters`, which the
native splitter components import lazily. The core `lumberjack-py` install has
no dependency on any of these frameworks.
