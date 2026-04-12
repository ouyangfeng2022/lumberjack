# ruff: noqa
from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


class TiktokenTokenizer:
    pass


tokenizer = TiktokenTokenizer()


@dataclass
class MkTreeNode:
    level: int = 0
    text: str = ""
    content: str = ""
    path: list[tuple[int, str]] = field(default_factory=list)
    children: dict[tuple[int, str], MkTreeNode] = field(default_factory=dict)
    text_tokens: int = 0
    content_tokens: int = 0
    children_tokens: int = 0
    index: int = 0

    @property
    def tokens(self) -> int:
        return self.text_tokens + self.content_tokens + self.children_tokens


@dataclass
class Chunk:
    navigation: str = ""
    content: str = ""
    tokens: int = 0

    def __add__(self, other):
        if not isinstance(other, Chunk):
            return NotImplemented
        if self.navigation != other.navigation:
            raise ValueError("Cannot add Chunks with different navigation")
        return Chunk(
            navigation=self.navigation,
            content=self.content + other.content,
            tokens=self.tokens + other.tokens,
        )


class MkTree:
    """Markdown 文档树结构

    将扁平的 LangChain Document 列表转换为嵌套的树状结构。
    使用文件名作为单一 root 节点，结构更统一。

    使用示例:
        tree = MkTree(document_title="test_md.md")
        for doc in documents:
            tree.insert(doc.metadata, doc.page_content)
        tree.calculate_tokens()

        # 遍历节点
        for node in tree.traverse():
            print(f"{node.text}: {node.tokens} tokens")

        # 按 tokens 拆分
        chunks = tree.split_by_max_tokens(max_tokens=1000)
    """

    def __init__(self, document_title: str) -> None:
        self.root = MkTreeNode(text=document_title, level=0)

    def insert(self, header_path: dict[str, str], content: str) -> None:
        """根据标题路径插入内容

        Args:
            header_path: LangChain metadata: {"Header 1": "标题1", "Header 2": "标题2"}
            content: 要插入的内容文本
        """
        if not content.strip():
            return

        path = self._extract_path(header_path)
        if not path:
            # 没有标题路径，说明是第一个标题之前的内容，添加到 root
            self.root.content += content
        else:
            # 有标题路径，从 root.children 开始查找/创建
            node = self._find_or_create_path(self.root.children, path)
            node.content += content

    def _extract_path(self, headers: dict[str, str]) -> list[tuple[int, str]]:
        """从 metadata 中提取 (层级, 标题) 的路径

        Args:
            headers: LangChain metadata

        Returns:
            [(1, "H1标题"), (2, "H2标题"), ...] 格式的路径
        """
        path = []
        for level in range(1, 7):  # Header 1 到 Header 6
            key = f"Header {level}"
            if key in headers:
                path.append((level, headers[key]))
            else:
                break
        return path

    def _find_or_create_path(
        self,
        current_level: dict[tuple[int, str], MkTreeNode],
        path: list[tuple[int, str]],
    ) -> MkTreeNode:
        """完全路径匹配，查找或创建节点

        Args:
            current_level: 当前层的子节点字典
            path: [(1, "H1"), (2, "H2"), ...] 格式的路径

        Returns:
            路径末端的节点
        """
        for i, key in enumerate(path):
            if key not in current_level:
                level, title = key
                current_level[key] = MkTreeNode(
                    text=title,
                    level=level,
                    index=len(current_level),
                    path=path[:i],
                )

            node = current_level[key]

            if i < len(path) - 1:
                current_level = node.children
            else:
                return node

        raise RuntimeError("Invalid path")

    def calculate_tokens(self) -> None:
        """计算所有节点的 token 数量和路径（从 root 开始递归）"""

        def _calc_node(node: MkTreeNode, current_path: list[tuple[int, str]] = []) -> int:
            # 设置节点的完整路径
            node.path = current_path.copy()

            # 计算 token 数量
            node.text_tokens = len(tokenizer.encode(node.text))
            node.content_tokens = len(tokenizer.encode(node.content))

            # 递归处理子节点
            child_tokens_sum = 0
            for key, child in node.children.items():
                child_path = current_path + [key]
                child_tokens_sum += _calc_node(child, child_path)

            node.children_tokens = child_tokens_sum
            return node.tokens

        _calc_node(self.root, [])

    def find(self, path: list[str]) -> MkTreeNode | None:
        """根据标题路径查找节点

        Args:
            path: ["H1标题", "H2标题", ...] 格式的路径（不包含 root）

        Returns:
            找到的节点，未找到返回 None
        """
        # 从 root.children 开始查找
        current_level = self.root.children

        for i, title in enumerate(path):
            # 在当前层查找匹配 title 的节点
            found = None
            for _, node in current_level.items():
                if node.text == title:
                    found = node
                    break

            if not found:
                return None

            if i == len(path) - 1:
                return found

            current_level = found.children

        return None

    def find_by_key(self, path: list[tuple[int, str]]) -> MkTreeNode | None:
        """根据完整 key (level, text) 路径查找节点（O(1) 每层查找）

        Args:
            path: [(1, "H1标题"), (2, "H2标题"), ...] 格式的路径（不包含 root）

        Returns:
            找到的节点，未找到返回 None
        """
        current_level = self.root.children

        for i, key in enumerate(path):
            if key not in current_level:
                return None

            node = current_level[key]

            if i == len(path) - 1:
                return node

            current_level = node.children

        return None

    def traverse(self) -> Iterator[MkTreeNode]:
        """深度优先遍历所有节点（从 root 开始）

        Yields:
            树中的每个节点（包含 root）
        """

        def _dfs(node: MkTreeNode) -> Iterator[MkTreeNode]:
            yield node
            for child in node.children.values():
                yield from _dfs(child)

        yield from _dfs(self.root)

    def to_dict(self) -> dict:
        """转换为字典格式（用于 JSON 序列化）

        Returns:
            包含完整树结构的字典（root 作为顶层）
        """

        def _node_to_dict(node: MkTreeNode) -> dict:
            return {
                "level": node.level,
                "text": node.text,
                "content": node.content,
                "text_tokens": node.text_tokens,
                "content_tokens": node.content_tokens,
                "path": node.path,
                "tokens": node.tokens,
                "index": node.index,
                "children": {
                    f"{key[0]}|{key[1]}": _node_to_dict(child)
                    for key, child in node.children.items()
                },
            }

        return _node_to_dict(self.root)

    def _merge_node_by_tokens(
        self,
        nodes: Sequence[MkTreeNode],
        max_tokens: int,
        current_chunk: Chunk | None = None,
    ) -> list[Chunk]:
        return_chunks = []
        if current_chunk is None:
            current_chunk = Chunk(
                navigation="",
                content="",
                tokens=0,
            )
        for node in nodes:
            # 每个 node 都是同一等级的标题
            if node.tokens + current_chunk.tokens <= max_tokens:
                text_chunk = self._node_to_text(node)
                current_chunk.content += text_chunk
                current_chunk.tokens += node.tokens
            else:
                if current_chunk.tokens > 0:
                    return_chunks.append(current_chunk)
                if node.tokens > max_tokens:
                    current_chunk = Chunk(
                        navigation="",
                        content="",
                        tokens=0,
                    )

                    return_chunks.append(
                        Chunk(
                            navigation="",
                            content=f"{'#' * node.level} {node.text}\n\n{node.content}",
                            tokens=node.text_tokens + node.content_tokens,
                        )
                    )
                    content_chunks = self._merge_node_by_tokens(node.children.values(), max_tokens)
                    for content_chunk in content_chunks:
                        return_chunks.append(
                            Chunk(
                                navigation="",
                                content=f"{'#' * node.level} {node.text}\n\n{content_chunk.content}",
                                tokens=node.text_tokens + content_chunk.tokens,
                            )
                        )
                else:
                    current_chunk = Chunk(
                        navigation="",
                        content=self._node_to_text(node),
                        tokens=node.tokens,
                    )
        if current_chunk.tokens > 0:
            return_chunks.append(current_chunk)
        return return_chunks

    def merge_by_max_tokens(self, max_tokens: int, min_tokens: int = 50) -> list[Chunk]:
        current_chunk = Chunk(
            navigation="",
            content=f"{self.root.content}\n\n",
            tokens=self.root.content_tokens,
        )
        chunks = self._merge_node_by_tokens(
            nodes=self.root.children.values(),
            max_tokens=max_tokens,
            current_chunk=current_chunk,
        )

        # 合并过小的块
        # chunks = self._merge_small_chunks(chunks, min_tokens, max_tokens)

        return chunks

    def split_by_max_tokens(self, max_tokens: int, min_tokens: int = 50) -> list[dict]:
        """按 token 数量拆分文档

        根据最大 token 数量将文档拆分为多个块，保持语义完整性。
        小于 min_tokens 的块会被合并到前一个块。

        Args:
            max_tokens: 每个块的最大 token 数量
            min_tokens: 最小 token 数量，小于此值的块会被合并

        Returns:
            拆分后的文档块列表（字典格式）
        """
        chunks = []

        if self.root.content.strip():
            chunks.append(
                {
                    "text": self.root.text,
                    "level": 0,
                    "content": self.root.content,
                    "tokens": self.root.content_tokens,
                    "children": [],
                }
            )

        # 当前正在构建的 chunk（用于合并一级标题）
        current_chunk = None
        current_tokens = 0

        # 从 root.children 开始拆分
        for child in self.root.children.values():
            # 如果整个一级标题不超过 max_tokens，尝试合并
            if child.tokens <= max_tokens:
                child_dict = self._node_to_split_dict(child, recursive=True)
                child_dict_tokens = child.tokens

                # 检查是否可以合并到当前 chunk
                if current_chunk is None:
                    # 创建新 chunk
                    current_chunk = {
                        "text": "",
                        "level": 0,
                        "content": "",
                        "tokens": child_dict_tokens,
                        "children": [child_dict],
                    }
                    current_tokens = child_dict_tokens
                elif current_tokens + child_dict_tokens <= max_tokens:
                    # 可以合并
                    current_chunk["children"].append(child_dict)
                    current_chunk["tokens"] = current_tokens + child_dict_tokens
                    current_tokens += child_dict_tokens
                else:
                    # 不能合并，保存当前 chunk，创建新 chunk
                    chunks.append(current_chunk)
                    current_chunk = {
                        "text": "",
                        "level": 0,
                        "content": "",
                        "tokens": child_dict_tokens,
                        "children": [child_dict],
                    }
                    current_tokens = child_dict_tokens
            else:
                # 一级标题超过 max_tokens，需要拆分
                # 先保存当前 chunk
                if current_chunk is not None:
                    chunks.append(current_chunk)
                    current_chunk = None
                    current_tokens = 0

                # 拆分一级标题
                child_chunks = self._split_node(child, max_tokens)
                chunks.extend(child_chunks)

        # 保存最后一个 chunk
        if current_chunk is not None:
            chunks.append(current_chunk)

        # 合并过小的块
        chunks = self._merge_small_chunks(chunks, min_tokens, max_tokens)

        return chunks

    def _split_node(
        self, node: MkTreeNode, max_tokens: int, include_header: bool = False
    ) -> list[dict]:
        """拆分单个节点

        Args:
            node: 要拆分的节点
            max_tokens: 最大 token 数量
            include_header: 是否包含当前节点标题（递归调用时子节点不包含父标题）

        Returns:
            拆分后的块列表
        """
        result = []
        header_tokens = node.text_tokens if include_header else 0
        available_tokens = max_tokens - header_tokens

        if node.content.strip():
            content_chunks = self._split_content_by_tokens(node.content, available_tokens)
            for content_chunk in content_chunks:
                result.append(
                    {
                        "level": node.level if include_header else 0,
                        "text": node.text if include_header else "",
                        "content": content_chunk["text"],
                        "tokens": header_tokens + content_chunk["tokens"],
                        "children": [],
                    }
                )

        for child_node in node.children.values():
            child_tokens = child_node.tokens

            # 如果子节点单独超过限制，递归拆分
            if child_tokens > available_tokens:
                # 使用完整的 max_tokens 递归拆分子节点（不限制父标题空间）
                child_chunks = self._split_node(child_node, max_tokens)
                result.extend(child_chunks)
            else:
                # 子节点不超过限制，尝试合并到当前 chunk
                # 查找目标 chunk：优先找同级别的最后一个 chunk
                target_chunk = None
                target_level = node.level if include_header else 0

                # 从后往前查找匹配的 chunk
                for chunk in reversed(result):
                    if chunk["level"] == target_level and chunk.get("children") is not None:
                        # 如果 include_header=False，只需要 level 匹配即可
                        # 如果 include_header=True，需要 level 和 text 都匹配
                        if not include_header or chunk["text"] == node.text:
                            target_chunk = chunk
                            break

                if target_chunk is None:
                    # 需要创建新的 chunk
                    target_chunk = {
                        "level": target_level,
                        "text": node.text if include_header else "",
                        "content": "",
                        "tokens": header_tokens,
                        "children": [],
                    }
                    result.append(target_chunk)

                # 检查加入后是否超过限制
                current_tokens = target_chunk["tokens"]
                if current_tokens + child_tokens > max_tokens:
                    # 超过限制，创建新 chunk
                    target_chunk = {
                        "level": target_level,
                        "text": node.text if include_header else "",
                        "content": "",
                        "tokens": header_tokens + child_tokens,
                        "children": [self._node_to_split_dict(child_node)],
                    }
                    result.append(target_chunk)
                else:
                    # 可以加入当前 chunk
                    target_chunk["children"].append(self._node_to_split_dict(child_node))
                    target_chunk["tokens"] = current_tokens + child_tokens

        return result

    def _split_content_by_tokens(self, content: str, max_tokens: int) -> list[dict]:
        """将超长内容按 token 数量拆分

        Args:
            content: 要拆分的内容文本
            max_tokens: 最大 token 数量

        Returns:
            拆分后的内容块列表
        """
        content_tokens = len(tokenizer.encode(content))

        if content_tokens <= max_tokens:
            return [{"text": content, "tokens": content_tokens}]

        # 使用 RecursiveCharacterTextSplitter 进行智能拆分
        splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
            chunk_size=max_tokens,
            chunk_overlap=0,
            length_function=lambda x: len(tokenizer.encode(x)),
        )

        chunks = splitter.split_text(content)
        return [{"text": chunk, "tokens": len(tokenizer.encode(chunk))} for chunk in chunks]

    def _node_to_chunk(self, node: MkTreeNode) -> Chunk:
        return Chunk(
            navigation="",
            content=self._node_to_text(node),
            tokens=node.tokens,
        )

    def _node_to_text(self, node: MkTreeNode) -> str:
        if not node.children:
            return f"{'#' * node.level} {node.text}\n\n{node.content}"
        child_chunks = "".join([self._node_to_text(child) for child in node.children.values()])
        return f"{'#' * node.level} {node.text}\n\n{node.content}\n\n{child_chunks}"

    def _node_to_split_dict(self, node: MkTreeNode, recursive: bool = True) -> dict:
        """将节点转换为拆分用的字典格式

        Args:
            node: 节点
            recursive: 是否递归处理子节点

        Returns:
            字典格式的节点
        """
        result = {
            "text": node.text,
            "level": node.level,
            "content": node.content,
            "tokens": node.tokens,
            "index": node.index,
            "children": [],
        }

        if recursive:
            result["children"] = [
                self._node_to_split_dict(child, recursive=True) for child in node.children.values()
            ]

        return result

    def _merge_small_chunks(
        self, chunks: list[dict], min_tokens: int, max_tokens: int
    ) -> list[dict]:
        """合并过小的块到前一个块

        Args:
            chunks: 文档块列表
            min_tokens: 最小 token 数量
            max_tokens: 最大 token 数量（合并后不能超过）

        Returns:
            合并后的文档块列表
        """
        if not chunks:
            return chunks

        result = []

        for i, chunk in enumerate(chunks):
            chunk_tokens = chunk.get("tokens", 0)

            # 第一个块或当前块足够大，直接添加
            if i == 0 or chunk_tokens >= min_tokens:
                result.append(chunk)
            else:
                # 当前块太小，尝试合并到前一个块
                if result:
                    prev_chunk = result[-1]
                    # 检查合并后是否超过 max_tokens
                    if prev_chunk["tokens"] + chunk_tokens <= max_tokens:
                        # 可以合并
                        prev_chunk["children"].extend(chunk.get("children", []))
                        prev_chunk["tokens"] += chunk_tokens
                        # 合并 content
                        if chunk.get("content"):
                            prev_chunk["content"] += "\n\n" + chunk["content"]
                    else:
                        # 合并后会超过限制，保留当前块
                        result.append(chunk)
                else:
                    # 没有前一个块，保留当前块
                    result.append(chunk)

        return result

    def chunks_to_text(self, chunks: list[dict]) -> list[str]:
        """将拆分后的块转换为文本列表

        每个块会包含完整的标题层级（父级标题），保持上下文信息。

        Args:
            chunks: 文档块列表

        Returns:
            文本列表
        """

        def _dict_node_to_text(node: dict, include_title: bool = True) -> str:
            """将字典节点转换为文本"""
            parts = []

            # 先添加完整路径中的所有父级标题
            if node.get("path"):
                # 遍历路径，添加所有父级标题
                for level, title in node["path"]:
                    prefix = "#" * level
                    parts.append(f"{prefix} {title}")

            # 添加当前节点标题（如果路径中没有包含当前节点）
            if include_title and node["level"] > 0:
                prefix = "#" * node["level"]
                title_text = f"{prefix} {node['text']}"
                # 检查路径中是否已经包含当前标题
                if not node.get("path") or node["path"][-1] != (
                    node["level"],
                    node["text"],
                ):
                    parts.append(title_text)

            # 添加内容
            if node.get("content"):
                parts.append(node["content"])

            # 递归处理子节点
            for child in node.get("children", []):
                parts.append(_dict_node_to_text(child, include_title=True))

            return "\n\n".join(parts)

        return [_dict_node_to_text(chunk) for chunk in chunks]


def split_markdown_by_tokens(
    markdown_path: str | None = None,
    markdown_content: str | None = None,
    max_tokens: int = 1000,
    min_tokens: int = 50,
    output_path: str | None = None,
) -> list[dict]:
    """将 Markdown 文档按 token 数量进行语义化拆分

    Args:
        markdown_path: Markdown 文件路径（与 markdown_content 二选一）
        markdown_content: Markdown 文本内容（与 markdown_path 二选一）
        max_tokens: 每个块的最大 token 数量
        min_tokens: 最小 token 数量，小于此值的块会被合并
        output_path: 输出 JSON 文件路径（可选）

    Returns:
        拆分后的文档块列表
    """
    # 参数验证
    if markdown_path is None and markdown_content is None:
        raise ValueError("必须提供 markdown_path 或 markdown_content")

    if max_tokens <= 0:
        raise ValueError("max_tokens 必须大于 0")

    if min_tokens < 0:
        raise ValueError("min_tokens 不能为负数")

    if min_tokens >= max_tokens:
        raise ValueError("min_tokens 必须小于 max_tokens")

    # 读取文档
    if markdown_path is not None:
        try:
            with open(markdown_path, encoding="utf-8") as f:
                content = f.read()
            doc_title = markdown_path.split("/")[-1]
        except FileNotFoundError:
            raise FileNotFoundError(f"文件不存在: {markdown_path}")
        except Exception as e:
            raise OSError(f"读取文件失败: {e}")
    else:
        content = markdown_content
        doc_title = "unknown.md"

    # 空内容处理
    if not content.strip():
        return []

    # 切分文档（支持 H1-H6）
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
        ("#####", "Header 5"),
        ("######", "Header 6"),
    ]

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=True,
    )
    md_docs = splitter.split_text(content)

    tree = MkTree(document_title=doc_title)
    for doc in md_docs:
        tree.insert(doc.metadata, doc.page_content)

    tree.calculate_tokens()

    chunks = [
        asdict(chunk)
        for chunk in tree.merge_by_max_tokens(max_tokens=max_tokens, min_tokens=min_tokens)
    ]

    tree_dict = tree.to_dict()
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "tree": tree_dict,
                    "chunks": chunks,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    return chunks


# ============ 命令行使用 ============
if __name__ == "__main__":
    # 示例：从文件拆分
    doc_path = "/home/elery/pypj/LightRAG/paging.md"

    print(f"正在处理文档: {doc_path}")
    print("=" * 80)

    # 拆分文档
    chunks = split_markdown_by_tokens(
        markdown_path=doc_path,
        max_tokens=100,
        min_tokens=20,
        output_path="split_output.json",
    )

    print(f"\n拆分完成，共 {len(chunks)} 个块")
    print("=" * 80)

    # 打印每个块的信息
    for i, chunk in enumerate(chunks, 1):
        tokens = chunk.get("tokens", 0)
        print(f"\n块 {i}: {chunk['content']} (tokens={tokens})")
        print(f"{'-' * 80}")

    # 转换为文本
    # tree = MkTree(document_title=doc_path.split("/")[-1])
    # texts = tree.chunks_to_text(chunks)

    with open("chunks.md", "w", encoding="utf-8") as f:
        for i, text in enumerate(chunks):
            f.write(text["content"])
