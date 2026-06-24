# Contributing to Prefix Hub

Thank you for your interest in contributing! This document covers how to get involved.

## Ways to Contribute

- **Report bugs** — Open an issue with steps to reproduce
- **Suggest features** — Open a discussion or issue with your idea
- **Submit code** — Fork → branch → PR
- **Improve docs** — Fix typos, add examples, clarify explanations
- **Help in Discord** — Answer questions in the community server

## Development Setup

```bash
git clone https://github.com/prefixhub/prefix-hub
cd prefix-hub
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Fill in your test credentials
alembic upgrade head
```

Run tests: `pytest`

## Pull Request Guidelines

1. **One PR per logical change.** Don't bundle unrelated fixes.
2. **Write a clear PR description** — what changed and why.
3. **All existing tests must pass.**
4. **Add tests** for new behavior where practical.
5. **Keep the diff small.** Large PRs are hard to review.

## Code Style

- Python: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (`ruff check . && ruff format .`)
- Type hints on all public functions
- Docstrings on all public classes and functions

## Commit Messages

Use the format: `type: short description`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Example: `feat: add Supporter tier badge to Discord notifications`

## Reporting Security Issues

**Do not open a public issue for security vulnerabilities.**
Email `security@prefixhub.xyz` with details. We'll respond within 48 hours.
