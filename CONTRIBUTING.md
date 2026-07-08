# Contributing to lumberjack

Thanks for your interest in contributing to lumberjack! This document describes how to set up a development environment and the workflow for submitting changes.

Contributions of all sizes are welcome — bug reports, bug fixes, new features, documentation improvements, and feature requests.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Coding Standards](#coding-standards)
- [Commit Style](#commit-style)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Getting Started

### Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) (the project's package manager)
- [Node.js](https://nodejs.org/) 20+ (only if you work on the web UI)

### Setup

1. **Fork** the repository on GitHub, then clone your fork:

   ```bash
   git clone https://github.com/<your-username>/lumberjack.git
   cd lumberjack
   ```

2. **Add an upstream remote** to keep your fork in sync:

   ```bash
   git remote add upstream https://github.com/ouyangfeng2022/lumberjack.git
   ```

3. **Install Python dependencies** (dev tools, tests, tokenizers, and DOCX support):

   ```bash
   uv sync --group dev --group test --extra tokenizers --extra docx
   ```

4. **(Optional) Install web dependencies** if you'll touch the frontend:

   ```bash
   cd lumberjack_webui
   npm ci
   ```

### Branch naming

Create a branch for your work. Use a descriptive name with one of these prefixes:

- `feat/` — new feature
- `fix/` — bug fix
- `docs/` — documentation only
- `refactor/` — code restructuring without behavior change
- `test/` — test additions or fixes

```bash
git checkout -b feat/add-new-splitter
```

## Development Workflow

Before opening a pull request, run these checks locally and make sure they pass — they are the same ones CI runs:

```bash
# Type check
uv run ty check .

# Lint (auto-fix safe issues)
uv run ruff check --fix

# Verify formatting is correct (does not modify files)
uv run ruff format --check

# Apply formatting if needed
uv run ruff format

# Run tests
uv run pytest
```

For the frontend (`lumberjack_webui/`):

```bash
cd lumberjack_webui
npm run lint    # eslint
npm run build   # tsc -b type check + vite build
```

## Testing

- **All new features and bug fixes must include tests.** Place tests under `tests/`, mirroring the module under test.
- Tests use `pytest`. Run the full suite with `uv run pytest`, or scope to a file: `uv run pytest tests/test_splitter.py`.
- `tests/conftest.py` puts `src/` on `sys.path`, so no extra setup is needed to import `lumberjack`.
- If your change needs fixture documents, add them under `tests/fixtures/markdown/` or `tests/fixtures/docx/`.
- Tests should be deterministic and not depend on network access.

## Coding Standards

- **Formatting**: enforced by `ruff format`. Run `uv run ruff format` before committing.
- **Linting**: enforced by `ruff check`. Run `uv run ruff check --fix` to auto-fix.
- **Type checking**: enforced by `ty`. Code must pass `uv run ty check .`.
- **Type annotations**: add type annotations to new public functions and methods.
- **Match surrounding style**: read the code around your change and follow the same patterns — naming, comments, module organization.

## Commit Style

Use [Conventional Commits](https://www.conventionalcommits.org/). The commit message format is:

```
<type>(<optional scope>): <description>

<optional body>

<optional footer>
```

Common types:

| Type     | Use for                                   |
| -------- | ----------------------------------------- |
| `feat`   | A new feature                             |
| `fix`    | A bug fix                                 |
| `docs`   | Documentation only                        |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test`   | Adding or correcting tests                |
| `chore`  | Build, tooling, CI, or other maintenance  |
| `perf`   | A change that improves performance        |

Examples:

```
feat(splitters): add section-flat incremental variant
fix(docx): preserve empty paragraphs in list items
docs: update CONTRIBUTING with commit style table
```

`!` signals a breaking change, e.g. `feat(splitters)!: rename merge_below_tokens to merge_below_ratio`.

## Pull Request Process

1. **Sync with upstream** to avoid conflicts:

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make sure local checks pass** (see [Development Workflow](#development-workflow)).

3. **Write a clear PR description.** Link the related issue (e.g. `Closes #123`), explain *what* changed and *why*.

4. **Fill in the PR checklist** from the pull request template.

5. **Open the pull request** against the `main` branch.

6. **Wait for CI to pass.** All status checks must be green before merging.

7. **Request / await review.** At least one approval is required, and changes to code paths listed in `CODEOWNERS` require review from the corresponding owner.

8. **Address review feedback** by pushing new commits to the same branch. Avoid force-pushing during active review unless asked — it makes comments hard to follow.

A maintainer will merge your PR once it's approved and CI is green. We use squash merges to keep history linear.

## Reporting Issues

Found a bug or have a feature idea? [Open an issue](https://github.com/ouyangfeng2022/lumberjack/issues/new/choose) and choose the **Bug report** or **Feature request** template.

**Good bug reports include:**

- A clear title and description of the problem
- Minimal steps to reproduce
- Expected vs. actual behavior
- Your environment: Python version, OS, lumberjack version, and how you installed it

**Good feature requests include:**

- The problem you're trying to solve (the *why*)
- A rough description of the solution you'd like (the *what*)
- Any alternatives you've considered

Thank you for contributing! 🪵
