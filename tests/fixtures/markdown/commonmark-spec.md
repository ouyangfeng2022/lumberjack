# CommonMark Specification Test Document

This document provides comprehensive examples of all CommonMark syntax elements with substantial content for testing the lumberjack markdown parser and splitter.

## 1. ATX Headings

ATX headings use 1-6 hash characters at the start of the line.

### Level 3 Heading

This is a level 3 heading. It is commonly used for subsections within documents.

#### Level 4 Heading

Level 4 headings provide further granularity for document organization.

##### Level 5 Heading

Level 5 headings are rarely used but available for deep document hierarchies.

###### Level 6 Heading

Level 6 is the deepest heading level available in CommonMark. Beyond this, you should consider using bold text or other formatting for visual hierarchy.

## 2. Setext Headings

Setext headings use underline characters for level 1 and 2 headings only.

Level 1 Heading with Underline
=================================

Setext style level 1 headings are underlined with equal signs. The underline does not need to match the length of the heading text, though many implementations prefer matching lengths for readability and ease of editing.

Level 2 Heading with Underline
---------------------------------

Level 2 Setext headings are underlined with dashes. Like level 1, the number of dashes is flexible, but consistency helps maintain clean source code. These headings can span multiple lines of text before the underline appears.

## 3. Paragraphs

Paragraphs are one or more consecutive lines of text separated by one or more blank lines. This is a paragraph with multiple lines. Lines are combined into a single paragraph when they are separated by single line breaks without intervening blank lines.

This is another paragraph separated by a blank line. Paragraphs can contain inline formatting like *emphasis*, **strong**, and `code` to enhance readability and convey meaning.

Paragraphs can also be quite long, containing multiple sentences that elaborate on a topic. When writing documentation or technical content, it's important to keep paragraphs focused on a single idea or concept. This makes the content more digestible for readers and helps maintain clarity throughout the document.

## 4. Emphasis

### Italic Text

Italic text is used for subtle emphasis, often for introducing new terms, indicating titles of works, or highlighting foreign phrases. In CommonMark, you can create italic text using asterisks or underscores.

*This text is italicized using asterisks.* It appears in a slanted typeface in most renderers.

_This text is italicized using underscores._ The effect should be identical to the asterisk version.

### Bold Text

Bold text creates stronger emphasis and is commonly used for warnings, important keywords, or to draw attention to critical information.

**This text is bold using double asterisks.** Bold text stands out more prominently than italic text.

__This text is bold using double underscores.__ Both syntaxes produce the same result, but consistency within a document is recommended.

### Combined Emphasis

You can combine emphasis for **bold and italic** text. This is useful for special callouts or extreme emphasis.

***Bold and italic*** using triple asterisks produces the strongest emphasis available in standard markdown.

___Bold and italic___ using triple underscores achieves the same visual effect.

## 5. Links

### Inline Links

Inline links are the most common type. They include the link text and destination in a single construct.

[Visit the Example website](https://example.com) - This is a basic inline link without a title.

[Visit Python's official site](https://python.org "Python Programming Language") - This inline link includes a title attribute that may be displayed as a tooltip on hover.

### Reference Links

Reference links separate the link definition from the reference, making the source text more readable and allowing link reuse.

[CommonMark specification][ref] is maintained by the CommonMark organization.
[ref]: https://spec.commonmark.org

Reference links can use numeric identifiers or descriptive labels. They are particularly useful in technical documentation where the same link might appear multiple times.

### Implicit Reference Links

[Implicit reference link] style omits the identifier after the link text, using the link text itself to match the reference definition.
[Implicit reference link]: https://example.com/implicit

### Automatic Links

URLs in angle brackets are automatically converted to links without needing link text.

<https://github.com>
<user@example.com>

## 6. Images

Images use syntax similar to links but with an exclamation mark prefix.

![A beautiful mountain landscape](https://images.unsplash.com/photo-1464822759023-fed622ff2c3b)

Images can have titles:

![Ocean sunset at twilight](https://images.unsplash.com/photo-1507525428034-b723cf961d3e "Sunset over the Pacific Ocean")

The alt text is important for accessibility and serves as a fallback if the image cannot be loaded.

## 7. Blockquotes

Blockquotes are used to indicate quoted text from another source or to set apart special content like notes or warnings.

> This is a blockquote. It can span multiple lines and paragraphs.
>
> Blockquotes are useful for highlighting important information, quoting external sources, or creating callout boxes in documentation.
>
> They can contain other markdown elements including lists, code blocks, and even nested blockquotes.

> ### Nested blockquotes
>
> > This is a nested blockquote. Each level of nesting is indicated by an additional greater-than sign at the start of the line.
> >
> > Nested quotes are less common but can be useful for indicating multiple levels of quoted content or creating visual hierarchy in callouts.
>
> The nesting can continue deeper if needed:
>
> > > Triple nested blockquote
> > >
> > > At this depth, the content is quite set apart from the main document flow.
> > >
> > > > Fourth level nesting
> > > > Usually unnecessary for most documents

## 8. Lists

### Unordered Lists

Unordered lists use dashes, asterisks, or plus signs as list markers. The choice of marker is a matter of preference, though consistency within a document is recommended.

- Item 1: This is the first item in the list
- Item 2: List items can contain multiple sentences. They can be quite long and still be considered part of the same list item as long as they're not separated by a blank line.
  - Nested item 2.1: This item is indented four spaces (or one tab)
  - Nested item 2.2: Nested lists can contain their own nested items
    - Deeper nesting: You can nest lists up to three levels deep in most implementations
    - Return to level 2: This item returns to the second nesting level
- Item 3: Back to the top level of the list

Using asterisks as markers:

* Item A: Asterisks are commonly used in GitHub Flavored Markdown
* Item B: The visual appearance is identical to dash-based lists
* Item C: Choose one style and stick with it throughout your document

Using plus signs:

+ Item X: Plus signs work the same way
+ Item Y: They're less commonly used but perfectly valid
+ Item Z: Some developers prefer them for specific use cases

### Ordered Lists

Ordered lists are numbered sequentially and automatically renumbered in most markdown processors.

1. First item: This introduces the ordered list
2. Second item: The numbers are provided in source but may be renumbered
3. Third item: Ordered lists are ideal for procedures, step-by-step instructions, or any content where sequence matters

Lazy numbering allows any number, which the processor will correct:

1. First item with lazy numbering
1. Second item (also numbered 1 in source)
1. Third item (also numbered 1 in source)
1. The rendered output will show 1, 2, 3, 4

Nested ordered list:

1. First main step: This item contains sub-steps
   1. Sub-step 1.1: Perform this action first
   2. Sub-step 1.2: Then perform this action
   3. Sub-step 1.3: Finally, complete this step
2. Second main step: This is the next top-level item
   1. Sub-step 2.1: Each top-level item can have its own nested list
3. Third main step: Continuing with the sequence

### Complex List Examples

Lists can contain various inline formatting:

- **Bold text** within list items
- *Italic text* for emphasis
- `Inline code` for technical terms
- [Links](https://example.com) to external resources
- Even small paragraphs within a single item that wrap across multiple lines but remain part of the same list item

## 9. Code

### Inline Code

Inline code is created by surrounding text with backticks. It's commonly used for variable names, function names, commands, or short code snippets within running text.

Use `print("Hello, World!")` to output text in Python. The function name `console.log()` is used in JavaScript for similar purposes.

Inline code preserves whitespace and can contain special characters that would otherwise be interpreted as markdown: `*not italic*` and `**not bold**`.

### Fenced Code Blocks

Fenced code blocks use triple backticks (or tildes) and can specify a programming language for syntax highlighting.

```python
def fibonacci(n):
    """
    Calculate the nth Fibonacci number using recursion.
    
    Args:
        n: The position in the Fibonacci sequence (non-negative integer)
    
    Returns:
        The nth Fibonacci number
    """
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Example usage
for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")
```

JavaScript example:

```javascript
class BinaryTree {
    constructor(value) {
        this.value = value;
        this.left = null;
        this.right = null;
    }

    insert(value) {
        if (value < this.value) {
            if (this.left === null) {
                this.left = new BinaryTree(value);
            } else {
                this.left.insert(value);
            }
        } else {
            if (this.right === null) {
                this.right = new BinaryTree(value);
            } else {
                this.right.insert(value);
            }
        }
    }

    traverseInOrder(callback) {
        if (this.left) {
            this.left.traverseInOrder(callback);
        }
        callback(this.value);
        if (this.right) {
            this.right.traverseInOrder(callback);
        }
    }
}
```

### Indented Code Blocks

Indented code blocks are created by indenting each line by 4 spaces or one tab. They don't support syntax highlighting but are part of the original markdown spec.

    def quick_sort(arr):
        if len(arr) <= 1:
            return arr
        pivot = arr[len(arr) // 2]
        left = [x for x in arr if x < pivot]
        middle = [x for x in arr if x == pivot]
        right = [x for x in arr if x > pivot]
        return quick_sort(left) + middle + quick_sort(right)

    # Testing the function
    test_array = [3, 6, 8, 10, 1, 2, 1]
    sorted_array = quick_sort(test_array)
    print(sorted_array)

## 10. Horizontal Rules

Horizontal rules are thematic breaks that separate content sections. They can be created using asterisks, dashes, or underscores.

Three or more asterisks (with optional spaces):

***

This is content after the first rule.

* * *

The spaces between asterisks are optional but can improve readability.

Three or more dashes:

---

Dashes are the most commonly used horizontal rule style, possibly because they're easier to type.

- - -

Spaces are optional here as well.

Three or more underscores:

___

Underscores are less common but equally valid. The choice is largely aesthetic.

## 11. Escaping

Backslashes escape special markdown characters, preventing them from being interpreted as formatting.

These characters can be escaped: \* \_ \[ \] \( \) \` \# \+ \- \. \! \\

For example, \*not italic\* will display as literal asterisks rather than creating italic text.

The backslash itself can be escaped: \\ produces a single backslash.

Escaping is useful when you need to display markdown syntax literally, such as in documentation about markdown itself.

## 12. HTML

### Inline HTML

Markdown allows inline HTML for when you need capabilities beyond standard markdown.

This is <strong>bold text using HTML</strong> within markdown.

You can also use <span style="color: red;">styled spans</span> for specific formatting needs.

HTML entities work alongside HTML tags: &copy; 2026, &trade;, &reg;

### HTML Blocks

Full HTML blocks can be embedded when necessary:

<div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px;">
    <h3>Custom HTML Block</h3>
    <p>This content is rendered as HTML, not markdown.</p>
    <ul>
        <li>HTML list item 1</li>
        <li>HTML list item 2</li>
    </ul>
</div>

<details>
<summary>Click to expand details</summary>

This content is hidden by default. The details/summary tags create an interactive collapsible section, useful for FAQ entries or optional technical details.

</details>

## 13. HTML Entities

HTML entities provide a way to include special characters that might be difficult to type or could conflict with markdown syntax.

Copyright &copy; 2026

Ampersand: &amp;

Less than: &lt; and greater than: &gt;

Non-breaking space: A&nbsp;B&nbsp;C

Em dash: &mdash; and en dash: &ndash;

Currency symbols: &euro; &pound; &yen; &cent;

Mathematical symbols: &plusmn; &times; &divide; &ne; &le; &ge;

Greek letters: &alpha; &beta; &gamma; &Delta; &Sigma; &pi;

## 14. Hard Line Breaks

Hard line breaks force a line break without starting a new paragraph. They're created by ending a line with two or more spaces.

This is line one with two trailing spaces.  
This is line two. Notice it's visually separated but still part of the same paragraph block.

This technique is useful for:  
- Poems or verse where line breaks matter  
- Addresses where each line should be distinct  
- Formatting content where you need precise control over line breaks  

## 15. Soft Line Breaks

Soft line breaks occur when you press Enter but don't add the trailing spaces. They create a newline in the source but render as a space in most browsers.

This is a soft break
that doesn't create a new paragraph.
The browser joins these lines with a space.

This is useful for:
- Making long lines more readable in source
- Wrapping text at a specific column width
- Keeping source code tidy while maintaining normal paragraph flow

## 16. Automatic Links

URLs and email addresses enclosed in angle brackets automatically become clickable links.

<https://www.commonmark.org/>

<https://github.github.com/gfm/>

<user@example.com>

<mailto:admin@example.org>

This is convenient for including raw links without needing separate link text.

## 17. Combined Examples

### Complex Nested Structure

> ## Documentation Blockquote
>
> This blockquote demonstrates how various markdown elements can be combined within a quoted block. This is useful for creating callouts, warnings, or highlighted information sections.
>
> ### Code Example in Blockquote
>
> ```python
> def calculate_rectangle_area(width, height):
>     """
>     Calculate the area of a rectangle.
>     
>     Parameters:
>         width (float): The width of the rectangle
>         height (float): The height of the rectangle
>     
>     Returns:
>         float: The area of the rectangle
>     """
>     return width * height
> ```
>
> ### List in Blockquote
>
> Key considerations for this function:
>
> - **Input validation**: Ensure width and height are positive numbers
> - **Edge cases**: Handle zero values appropriately
> - **Precision**: Consider floating-point precision for large or small numbers
> - **Documentation**: Maintain clear docstrings for API documentation
>
> ### Nested Structure
>
> > **Note:** This is a nested blockquote providing additional context about the implementation details or usage patterns.
> >
> > The nesting allows for hierarchical organization of information within callouts.

### Documentation Example with Multiple Elements

#### Function: `parse_document(source, options)`

Parses a markdown document and returns an abstract syntax tree (AST).

**Parameters:**

- `source` (str): The markdown source text to parse. Can be a single line or multi-line string containing the full document content.
- `options` (dict, optional): Configuration options that control parsing behavior. Available options:
  - `preserve_whitespace` (bool): Whether to preserve insignificant whitespace
  - `strict_mode` (bool): Enable strict CommonMark compliance
  - `allow_extensions` (bool): Enable GitHub Flavored Markdown extensions

**Returns:**

- `DocumentAST`: An abstract syntax tree representing the parsed document structure with all nodes and relationships.

**Raises:**

- `ParseError`: If the source contains syntax errors in strict mode
- `ValueError`: If source is not a string

**Example Usage:**

```python
from lumberjack.parser import MarkdownParser

# Initialize parser with default options
parser = MarkdownParser()

# Parse a markdown document
source = """
# Document Title

This is a paragraph with **bold** and *italic* text.
"""

ast = parser.parse(source)

# Access parsed elements
print(ast.children[0].content)  # Output: Document Title
```

**See also:** [CommonMark Spec](https://spec.commonmark.org), [Parser Options](#parser-options)

## 18. Edge Cases and Ambiguities

### Empty Emphasis Markers

This is not italic: this_is_text (underscores surrounded by alphanumeric characters)

This is not bold: this_is_more_text (word_characters prevent emphasis interpretation)

The rules for emphasis are complex and depend on context. The CommonMark spec defines precise rules based on character categories.

### Links in Emphasis

*[Link inside emphasis](https://example.com)* - The entire link is italicized

**[Link inside bold text](https://example.com)** - Bold link

*[Nested **bold inside italic** and `code` too](https://example.com)* - Complex nesting

### Code in Emphasis

`code` inside *emphasis* works as expected.

But you cannot nest emphasis within code: `` *not italic* `` displays literally.

### Backslash Escapes in Code

`code blocks don't process backslash escapes: \* \* \*`

But inline code in emphasis *does `allow \* escapes` within* the outer emphasis.

## 19. Chinese Characters and CJK Content

中文标题示例
------

这是一个包含中英文混合内容的段落。在中文技术文档中，经常会遇到需要混合使用 English 术语和中文说明的情况。例如：API、SDK、HTTP、JSON 等技术术语通常保持英文原样。

### 中文列表示例

中文列表应该遵循以下格式规范：

- 列表项使用中文标点符号结尾
- 保持列表项之间的一致性
- 每个列表项应该有清晰的语义
  - 子列表项使用缩进
  - 可以包含多个段落
  - 支持嵌套到多层级

### 中文字符与英文混合

在处理中文内容时需要注意以下几点：

1. **标点符号**：中文使用全角标点（，。：；！？），而英文使用半角标点
2. **空格使用**：中英文之间通常需要添加空格以提高可读性
3. **代码块**：中文注释和文档字符串在代码块中应该正确显示

### 中文代码块示例

```python
class ChineseDocument:
    """
    中文文档处理器
    
    这个类专门用于处理包含中文内容的 markdown 文档。
    主要功能包括分词、语法分析和语义理解。
    """
    
    def __init__(self, content):
        """
        初始化文档处理器
        
        参数:
            content (str): 文档内容，可能包含中文
        """
        self.content = content
        self.segments = []
    
    def parse(self):
        """解析文档内容并提取结构化信息"""
        lines = self.content.split('\n')
        for line in lines:
            # 按行处理，保留段落结构
            self.segments.append({
                'text': line.strip(),
                'length': len(line)
            })
        
        return self.segments
```

### CJK 混合排版

日文、韩文与中文混合使用时的示例：

この文章は日本語です。This is English。这是中文。

한국어 문장입니다. Mixed language content requires careful handling of line breaks and spacing between different writing systems.

## 20. Code Fence Features and Variations

### No Language Specifier

```
This is a plain code block without syntax highlighting.

It's useful for:
- Text that needs to preserve formatting
- Configuration files without specific language support
- Pseudocode or algorithm descriptions
- Any content where syntax highlighting would be misleading
```

### Various Language Specifications

Python example:

```python
import asyncio
from typing import List, Optional

async def fetch_data(urls: List[str]) -> List[dict]:
    """
    Asynchronously fetch data from multiple URLs.
    
    This function demonstrates async/await syntax in Python,
    type hints, and docstring conventions.
    """
    results = []
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            async with session.get(url) as response:
                data = await response.json()
                results.append(data)
    
    return results
```

Rust example:

```rust
use std::collections::HashMap;

fn word_count(text: &str) -> HashMap<String, usize> {
    let mut counts = HashMap::new();
    
    for word in text.split_whitespace() {
        let word = word.to_lowercase();
        *counts.entry(word).or_insert(0) += 1;
    }
    
    counts
}

fn main() {
    let text = "hello world hello rust world";
    let counts = word_count(text);
    
    for (word, count) in counts {
        println!("{}: {}", word, count);
    }
}
```

### Tilde-style Code Fences

~~~
Some implementations also support tildes for code fences
This alternative syntax uses ~~~ instead of ```
It's less common but perfectly valid
~~~

### Info Strings with Additional Data

```json {"schema":"example"}
{
  "name": "Example Document",
  "version": "1.0.0",
  "metadata": {
    "author": "Test Author",
    "created": "2026-04-14"
  }
}
```

## 21. Task Lists (GFM Extension)

Task lists extend standard markdown to provide interactive checkboxes.

- [ ] Uncompleted task: Review the documentation
- [ ] Uncompleted task: Update the API reference
- [x] Completed task: Implement the parser
- [x] Completed task: Write unit tests

Tasks can have detailed descriptions:

- [ ] **High Priority**: Fix the critical bug in the splitter module
  - [ ] Investigate the root cause
  - [ ] Implement a fix
  - [ ] Write regression tests
  - [ ] Update documentation
- [ ] **Medium Priority**: Refactor the AST visitor pattern
- [x] **Low Priority**: Update the README with new examples

Nested task lists:

- [ ] Main task: Implement the feature
  - [ ] Sub-task: Research existing solutions
  - [x] Sub-task: Design the architecture
  - [ ] Sub-task: Write the implementation
  - [ ] Sub-task: Add tests
- [ ] Main task: Deploy to production
  - [ ] Prepare deployment checklist
  - [ ] Schedule maintenance window
  - [ ] Execute deployment plan

## 22. Strikethrough (GFM Extension)

Strikethrough text is useful for indicating deleted content, corrections, or deprecated information.

~~This content has been removed~~ and replaced with new content.

Version history:

~~v1.0.0~~ - Initial release (deprecated)
~~v1.1.0~~ - Beta version (deprecated)
~~v1.2.0~~ - Release candidate (deprecated)
**v2.0.0** - Current stable release

~~Old API method~~ is replaced by the **new API method** which provides better performance and additional features.

## 23. Tables (GFM Extension)

Tables are created using pipes to separate columns and dashes for the header separator.

### Basic Table

| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1-1 | Cell 1-2 | Cell 1-3 |
| Cell 2-1 | Cell 2-2 | Cell 2-3 |
| Cell 3-1 | Cell 3-2 | Cell 3-3 |

### Aligned Table

| Left align | Center align | Right align |
|:-----------|:------------:|------------:|
| Left       | Center       | Right       |
| Align this | Center this  | Align this  |
| Content    | Content      | Content     |

### Complex Table

| Parameter | Type | Description | Default | Required |
|-----------|------|-------------|---------|----------|
| `source` | `str` | The markdown source text | `None` | Yes |
| `options` | `dict` | Configuration options | `{}` | No |
| `strict` | `bool` | Enable strict mode | `false` | No |
| `encoding` | `str` | Character encoding | `'utf-8'` | No |
| `timeout` | `int` | Parse timeout in seconds | `30` | No |

### Table with Inline Formatting

| Feature | Syntax | Example | Status |
|---------|--------|---------|--------|
| Bold | `**text**` | **bold text** | ✅ Supported |
| Italic | `*text*` | *italic text* | ✅ Supported |
| Code | `` `code` `` | `inline code` | ✅ Supported |
| Links | `[text](url)` | [Example](https://example.com) | ✅ Supported |

## 24. LaTeX Mathematical Formulas

Mathematical notation is essential for technical documentation, especially in scientific, engineering, and computational contexts. While not part of the original CommonMark specification, LaTeX math syntax is widely supported by markdown processors including Pandoc, GitHub, GitLab, and many static site generators.

### Inline Math Formulas

Inline mathematical expressions are delimited by single dollar signs `$` and are rendered within the flow of text.

The quadratic formula is $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$.

Euler's identity is often considered the most beautiful equation: $e^{i\pi} + 1 = 0$.

The area of a circle is $A = \pi r^2$ where $r$ is the radius.

Newton's second law states that $F = ma$, where $F$ is force, $m$ is mass, and $a$ is acceleration.

The Pythagorean theorem: $a^2 + b^2 = c^2$ for a right triangle with legs $a$ and $b$ and hypotenuse $c$.

### Block Math Formulas

Block mathematical expressions are delimited by double dollar signs `$$` and are rendered as standalone centered blocks. These are used for equations that deserve prominence or are too large for inline display.

The Gaussian integral:

$$
\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}
$$

The definition of the exponential function:

$$
e^x = \sum_{n=0}^{\infty} \frac{x^n}{n!} = 1 + x + \frac{x^2}{2!} + \frac{x^3}{3!} + \cdots
$$

Maxwell's equations in differential form:

$$
\begin{aligned}
\nabla \cdot \mathbf{E} &= \frac{\rho}{\varepsilon_0} \\
\nabla \cdot \mathbf{B} &= 0 \\
\nabla \times \mathbf{E} &= -\frac{\partial \mathbf{B}}{\partial t} \\
\nabla \times \mathbf{B} &= \mu_0\mathbf{J} + \mu_0\varepsilon_0\frac{\partial \mathbf{E}}{\partial t}
\end{aligned}
$$

### Common Mathematical Symbols

Greek letters are commonly used in mathematical expressions:

- Lowercase: $\alpha$, $\beta$, $\gamma$, $\delta$, $\epsilon$, $\theta$, $\lambda$, $\mu$, $\pi$, $\sigma$, $\phi$, $\omega$
- Uppercase: $\Gamma$, $\Delta$, $\Lambda$, $\Sigma$, $\Phi$, $\Omega$

Comparison operators: $<$, $>$, $\le$, $\ge$, $\neq$, $\approx$

Set notation: $\in$, $\notin$, $\subset$, $\subseteq$, $\cup$, $\cap$, $\emptyset$

Logic symbols: $\forall$, $\exists$, $\therefore$, $\because$, $\implies$, $\iff$

Arrows and relations: $\rightarrow$, $\Rightarrow$, $\leftrightarrow$, $\Leftrightarrow$, $\mapsto$

### Fractions and Roots

Fractions are expressed using `\frac{numerator}{denominator}`:

The probability of an event is $P(E) = \frac{\text{favorable outcomes}}{\text{total outcomes}}$.

Roots use `\sqrt[n]{x}` for nth roots or `\sqrt{x}` for square roots:

Square root: $\sqrt{16} = 4$

Cube root: $\sqrt[3]{27} = 3$

General root: $\sqrt[n]{x} = x^{1/n}$

### Superscripts and Subscripts

Superscripts for exponents: $x^2$, $y^{10}$, $e^{-x}$

Subscripts for indices: $a_1$, $b_{ij}$, $\sum_{i=1}^{n}$

Combined: $x_i^2$ (subscript then superscript)

### Sums, Products, and Integrals

The summation notation: $\sum_{i=1}^{n} a_i = a_1 + a_2 + \cdots + a_n$

The product notation: $\prod_{i=1}^{n} a_i = a_1 \cdot a_2 \cdot \cdots \cdot a_n$

Definite integral: $\int_{a}^{b} f(x) dx$

Indefinite integral: $\int f(x) dx$

Double integral: $\iint_D f(x,y) dA$

Triple integral: $\iiint_V f(x,y,z) dV$

### Limits and Calculus

Limit definition:

$$
\lim_{x \to a} f(x) = L
$$

Derivative notation:

$$
f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}
$$

Partial derivative: $\frac{\partial f}{\partial x}$

Gradient: $\nabla f$

Divergence: $\nabla \cdot \mathbf{F}$

Curl: $\nabla \times \mathbf{F}$

### Matrices and Vectors

Column vector: $\mathbf{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$

Row vector: $\mathbf{u} = \begin{pmatrix} u_1 & u_2 & u_3 \end{pmatrix}$

Matrix multiplication:

$$
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
\begin{pmatrix}
x \\
y
\end{pmatrix}
=
\begin{pmatrix}
ax + by \\
cx + dy
\end{pmatrix}
$$

Identity matrix: $I = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}$

### Statistics and Probability

Mean: $\mu = \frac{1}{n}\sum_{i=1}^{n} x_i$

Variance: $\sigma^2 = \frac{1}{n}\sum_{i=1}^{n} (x_i - \mu)^2$

Standard deviation: $\sigma = \sqrt{\frac{1}{n}\sum_{i=1}^{n} (x_i - \mu)^2}$

Normal distribution:

$$
f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{1}{2}\left(\frac{x-\mu}{\sigma}\right)^2}
$$

Binomial coefficient: $\binom{n}{k} = \frac{n!}{k!(n-k)!}$

### Linear Algebra

Matrix determinant: $\det(A) = |A|$

Eigenvalue equation: $A\mathbf{v} = \lambda\mathbf{v}$

Singular value decomposition: $A = U\Sigma V^T$

Dot product: $\mathbf{a} \cdot \mathbf{b} = |\mathbf{a}||\mathbf{b}|\cos\theta$

Cross product: $\mathbf{a} \times \mathbf{b} = \mathbf{c}$

### Complex Numbers

Complex number: $z = a + bi$ where $i^2 = -1$

Complex conjugate: $\bar{z} = a - bi$

Euler's formula: $e^{i\theta} = \cos\theta + i\sin\theta$

Polar form: $z = r(\cos\theta + i\sin\theta) = re^{i\theta}$

### Trigonometry

Basic identities: $\sin^2\theta + \cos^2\theta = 1$

Angle sum: $\sin(\alpha + \beta) = \sin\alpha\cos\beta + \cos\alpha\sin\beta$

Law of cosines: $c^2 = a^2 + b^2 - 2ab\cos\gamma$

### Number Theory

Divisibility: $a \mid b$ (a divides b)

Modular arithmetic: $a \equiv b \pmod{n}$

Greatest common divisor: $\gcd(a,b)$

Prime counting function: $\pi(x) = \sum_{p \le x} 1$

### Computer Science Formulas

Big O notation: $f(n) = O(g(n))$

Logarithm change of base: $\log_b x = \frac{\log_a x}{\log_a b}$

Binary logarithm: $\log_2 n = \frac{\ln n}{\ln 2}$

Information entropy:

$$
H(X) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)
$$

### Advanced Examples

Taylor series expansion:

$$
f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(a)}{n!}(x-a)^n
$$

Fourier series:

$$
f(x) = \frac{a_0}{2} + \sum_{n=1}^{\infty} \left[ a_n\cos\left(\frac{n\pi x}{L}\right) + b_n\sin\left(\frac{n\pi x}{L}\right) \right]
$$

Schrödinger equation:

$$
i\hbar\frac{\partial}{\partial t}\Psi(x,t) = \left[ -\frac{\hbar^2}{2m}\frac{\partial^2}{\partial x^2} + V(x,t) \right]\Psi(x,t)
$$

### Cases and Piecewise Functions

Absolute value function:

$$
|x| = \begin{cases}
x & \text{if } x \ge 0 \\
-x & \text{if } x < 0
\end{cases}
$$

Heaviside step function:

$$
H(x) = \begin{cases}
0 & \text{for } x < 0 \\
\frac{1}{2} & \text{for } x = 0 \\
1 & \text{for } x > 0
\end{cases}
$$

### Mathematical Typography

Blackboard bold: $\mathbb{N}$, $\mathbb{Z}$, $\mathbb{Q}$, $\mathbb{R}$, $\mathbb{C}$

Calligraphic: $\mathcal{A}$, $\mathcal{B}$, $\mathcal{F}$, $\mathcal{L}$

Fraktur: $\mathfrak{g}$, $\mathfrak{h}$, $\mathfrak{sl}(2,\mathbb{C})$

## 25. Real-World Documentation Examples

### API Documentation Section

#### `DocumentParser` Class

The `DocumentParser` class is responsible for converting markdown source text into a structured Abstract Syntax Tree (AST) that can be processed by downstream components.

##### Constructor

```python
def __init__(self, options: Optional[Dict[str, Any]] = None) -> None:
    """
    Initialize the parser with optional configuration.
    
    The parser can be customized with various options to control
    parsing behavior, handle extensions, and manage edge cases.
    """
    self.options = options or {}
    self._extensions = self._load_extensions()
```

##### Methods

###### `parse(source: str) -> DocumentAST`

Parse markdown source text and return the AST.

**Parameters:**
- `source`: The markdown source text to parse

**Returns:** A `DocumentAST` object representing the parsed document

**Raises:**
- `ParseError`: If the source contains invalid syntax in strict mode

**Example:**

```python
parser = DocumentParser({'strict': True})
ast = parser.parse("# Hello\n\nWorld")
print(ast.root.children[0].content)  # Output: Hello
```

### Configuration Reference

#### Available Parser Options

| Option | Type | Description |
|--------|------|-------------|
| `preserve_whitespace` | `boolean` | Keep insignificant whitespace in the AST |
| `allow_html` | `boolean` | Permit HTML tags in the markdown source |
| `smart_quotes` | `boolean` | Convert straight quotes to curly quotes |
| `autolink` | `boolean` | Automatically link bare URLs |

#### Default Configuration

```yaml
parser:
  preserve_whitespace: false
  allow_html: true
  smart_quotes: false
  autolink: true

splitter:
  max_tokens: 1000
  min_tokens: 100
  overlap: 50
  respect_headings: true
```

### Troubleshooting Guide

> **Common Issue:** Parser produces unexpected output
>
> **Solution:** Enable strict mode and check the CommonMark specification for correct syntax. Some edge cases have specific rules that differ from informal markdown conventions.
>
> ```python
> parser = DocumentParser({'strict': True, 'debug': True})
> ast = parser.parse(source)
> print(ast.debug_tree())  # Inspect the parsed structure
> ```

**Frequently Encountered Problems:**

1. **Lists not rendering correctly**
   - Ensure proper indentation (4 spaces or 1 tab)
   - Check for blank lines between list items (which breaks the list)
   - Verify consistent list marker usage

2. **Code blocks not formatting**
   - Use fenced code blocks (```) instead of indentation for better compatibility
   - Specify language for syntax highlighting
   - Escape backticks within code blocks

3. **Links not working**
   - Verify URL format includes protocol (https://)
   - Check for unescaped special characters
   - Reference links must have matching definitions

## End of Comprehensive Test Document

This document provides thorough coverage of CommonMark syntax elements with realistic, substantial content for testing markdown parsers, splitters, and related tools. Each section includes multiple examples demonstrating variations and edge cases.
