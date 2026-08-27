export interface BuiltInSample {
  id: string;
  labelKey: string;
  text: string;
}

export const BUILT_IN_SAMPLES: BuiltInSample[] = [
  {
    id: 'technical',
    labelKey: 'sample_technical',
    text: `# Getting Started

This guide walks you through the basics of using our platform.

## Installation

First, install the required packages using your preferred package manager.

\`\`\`bash
npm install my-package
\`\`\`

## Configuration

Create a config file in your project root:

\`\`\`json
{
  "theme": "dark",
  "language": "en"
}
\`\`\`

### Advanced Settings

For production deployments, you should also set the following environment variables:

- \`API_KEY\`: Your API key
- \`BASE_URL\`: The base URL of your instance
- \`LOG_LEVEL\`: Logging verbosity (debug, info, warn, error)

## Usage

Import the library and initialize it with your configuration:

\`\`\`javascript
import { createClient } from 'my-package';

const client = createClient({
  apiKey: 'your-api-key',
});
\`\`\`

### Making Requests

Once initialized, you can make requests to the API:

\`\`\`javascript
const result = await client.query({
  text: "Hello, world!",
  maxTokens: 100,
});
\`\`\`

## Troubleshooting

If you encounter issues, check the following:

1. Verify your API key is valid
2. Ensure your network allows outbound HTTPS connections
3. Check the service status page for any ongoing incidents

For more help, consult the FAQ or open a GitHub issue.
`,
  },
  {
    id: 'table',
    labelKey: 'sample_table',
    text: `# Service Catalog

An overview of the services we operate, their regions, and quotas.

## Compute Services

| Name | Region | vCPU | Memory | Monthly Quota | Owner |
| --- | --- | ---: | ---: | ---: | --- |
| api-gateway | us-east-1 | 16 | 64 GiB | 12000 | platform |
| auth-service | us-east-1 | 8 | 32 GiB | 8000 | identity |
| billing-worker | eu-west-1 | 32 | 128 GiB | 30000 | finance |
| search-indexer | eu-west-1 | 16 | 64 GiB | 15000 | discovery |
| ml-inference | ap-south-1 | 64 | 256 GiB | 90000 | research |
| stream-processor | ap-south-1 | 16 | 64 GiB | 20000 | platform |
| edge-cache | global | 8 | 16 GiB | 5000 | platform |
| vault-proxy | us-west-2 | 4 | 16 GiB | 3000 | identity |

## Storage Services

| Name | Type | Capacity | Replication | Snapshot Policy |
| --- | --- | ---: | --- | --- |
| primary-db | postgres | 4 TiB | sync 3AZ | hourly, 7d retention |
| analytics-db | clickhouse | 16 TiB | async 2AZ | daily, 30d retention |
| object-store | s3 | 80 TiB | cross-region | versioned, 90d |
| backup-vault | s3 | 20 TiB | cross-account | immutable, 365d |
| queue-store | kafka | 8 TiB | 3 replicas | 7d retention |
| cache-tier | redis | 512 GiB | 2 replicas | none |

## Notes

Quotas reset on the first day of each calendar month. Contact the owning team
before requesting increases above the listed values.
`,
  },
  {
    id: 'long-paragraph',
    labelKey: 'sample_long_paragraph',
    text: `# System Design Retrospective

## Background

When we started rebuilding the ingestion pipeline, the team agreed on three principles: every component must be independently deployable, every message on the bus must be idempotent to replay, and every transformation must be observable end to end. The first principle pushed us toward small services with narrow contracts. The second forced us to think carefully about ordering guarantees, because replaying a stream out of order can resurrect stale state if consumers are not careful about versioning their writes. The third principle turned out to be the most expensive one, since observability is not a feature you can bolt on after the fact; it has to be designed into the data model itself, which is why every record now carries a trace identifier from the moment it enters the system.

## What Worked

The event-carried state transfer pattern worked far better than we expected. Consumers that needed a local projection of upstream data stopped making synchronous calls entirely, and the p99 latency of the aggregation service dropped from four hundred milliseconds to under twenty. Schema evolution also went more smoothly than in previous projects because we committed to additive-only changes for two release cycles, which gave every consumer time to migrate at their own pace. The on-call rotation reported that incidents became easier to triage once the dashboards grouped errors by trace identifier instead of by host.

## What Hurt

The biggest surprise was the cost of partial failures. When a consumer acknowledges a message and then fails to commit its local transaction, the divergence is invisible until the next audit, and reconciling it requires a full replay of the affected partition. We mitigated this by making the commit the last step of every handler and by adding a reconciliation job that runs nightly, but the fundamental tension between throughput and consistency did not go away; it just moved from the request path to the background. Another painful lesson was that idempotency keys based on content hashes break when upstream producers retry with slightly different timestamps embedded in the payload.

## Conclusions

Would we make the same choices again? Mostly yes. We would invest earlier in the reconciliation tooling, and we would think harder about which projections truly need to be derived from the event stream rather than queried on demand. The architecture is not simpler than the one it replaced, but it is more legible: every failure mode now has a name, an owner, and a dashboard.
`,
  },
  {
    id: 'mixed-language',
    labelKey: 'sample_mixed',
    text: `# 混合语言文档 / Mixed-Language Document

This document mixes Chinese and English to show how token estimation behaves
when the tokenizer is swapped between approx, tiktoken, and transformers.

## 安装 / Installation

运行以下命令安装软件包：

\`\`\`bash
pip install lumberjack-py
\`\`\`

Install the package with the command above. 中文段落和 English paragraphs are
counted by the same tokenizer, but the estimated token counts can differ
noticeably for CJK text.

## 配置示例 / Configuration

默认预算为 1200 tokens。The default budget is 1200 tokens. 你可以调整
\`max_tokens\`、\`ideal_max_tokens_ratio\` 和 \`merge_below_ratio\` 来改变切分行为。
You can tune these three knobs to change how aggressively sections are merged.

## 常见问题 / FAQ

**问:为什么中文的 token 估算偏差更大?**
Why is the estimation error larger for Chinese text? Because the approx
tokenizer estimates tokens from UTF-8 byte counts, and CJK characters encode
to three bytes each.

**问:什么时候应该用 exact 计量?**
Use exact counting when every budget decision must fully recount the rendered
candidate text, at the cost of more tokenizer calls.
`,
  },
  {
    id: 'code-heavy',
    labelKey: 'sample_code',
    text: `# Parser Internals

The parser turns a token stream into the shared document tree.

## Tokenizer Loop

\`\`\`python
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def lex(source: str) -> Iterator[Token]:
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            yield Token("heading", stripped)
        elif stripped.startswith("|"):
            yield Token("row", stripped)
        else:
            yield Token("text", stripped)
\`\`\`

## Tree Construction

\`\`\`python
def build_tree(tokens):
    root = Node(kind="root")
    stack = [root]
    for token in tokens:
        if token.kind == "heading":
            level = token.value.count("#")
            while len(stack) > level:
                stack.pop()
            node = Node(kind="section", value=token.value)
            stack[-1].children.append(node)
            stack.append(node)
        else:
            stack[-1].children.append(Node(kind=token.kind, value=token.value))
    return root
\`\`\`

## Fallback Splitting

When a block exceeds the budget and cannot be split structurally, the splitter
falls back through paragraph breaks, line breaks, sentences, words, and finally
a hard character split:

\`\`\`text
paragraph break -> line break -> sentence -> word -> hard split
\`\`\`
`,
  },
];
