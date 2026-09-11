# tokenizer 差异说明

## 背景

ApproxByteTokenizer 按 UTF-8 字节数除以三估算词元数,而 tiktoken 对中文的
编码密度明显不同。When the splitter budget is tight, the difference between
the estimate and the authoritative count becomes visible in the chunk sizes.

## 实验设置

同一份文档分别用三种 tokenizer 切分,预算固定。The same document is split
three times with the budget held constant.

## 观察

- 中文段落的估算误差通常大于英文段落。Estimation error on Chinese
  paragraphs is usually larger.
- exact 计量会把误差压到零,但 tokenizer 调用次数上升。Exact counting
  drives the error to zero at the cost of more tokenizer calls.

## 建议

预算紧张时优先选择 tiktoken 加 exact 组合。Prefer tiktoken with exact
counting when the budget is tight; the incremental estimate is adequate for
English-heavy corpora.
