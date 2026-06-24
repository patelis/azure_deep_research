"""Versioned prompt loader.

Prompts are Markdown files with YAML frontmatter (``name``, ``version``, ``description``,
``variables``) in ``backend/prompts/``. Render with ``render("final_report", findings=..., ...)``.
The highest ``version`` is used unless one is pinned. CI deploys the prompts; ``sync_agents.py``
bakes them into the Foundry agents.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import frontmatter


@dataclass(frozen=True)
class Prompt:
    """A single, versioned prompt template."""

    name: str
    version: int
    description: str
    variables: tuple[str, ...]
    body: str
    path: Path

    def render(self, **values: object) -> str:
        """Format the body, validating that all declared variables are supplied."""
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise KeyError(
                f"Prompt {self.name!r} (v{self.version}) is missing variables: {missing}"
            )
        try:
            return self.body.format(**values)
        except KeyError as exc:  # body references an undeclared placeholder
            raise KeyError(f"Prompt {self.name!r} references undeclared placeholder {exc}") from exc


def _prompts_dir() -> Path:
    """Locate the ``prompts/`` directory (env override, else backend/prompts)."""
    override = os.getenv("DEEP_RESEARCH_PROMPTS_DIR")
    if override:
        return Path(override)
    # src/deep_research/prompts.py -> parents[2] == backend/
    return Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict[int, Prompt]]:
    """Parse every ``*.md`` prompt file into a {name: {version: Prompt}} registry."""
    registry: dict[str, dict[int, Prompt]] = {}
    directory = _prompts_dir()
    if not directory.is_dir():
        raise FileNotFoundError(f"Prompts directory not found: {directory}")

    for path in sorted(directory.glob("*.md")):
        post = frontmatter.load(path)
        meta = post.metadata
        name = str(meta.get("name") or path.stem.split(".")[0])
        version = int(meta.get("version", 1))
        variables = tuple(meta.get("variables", []) or [])
        prompt = Prompt(
            name=name,
            version=version,
            description=str(meta.get("description", "")),
            variables=variables,
            body=post.content.strip("\n"),
            path=path,
        )
        versions = registry.setdefault(name, {})
        if version in versions:
            raise ValueError(
                f"Duplicate prompt {name!r} version {version}: {versions[version].path} and {path}"
            )
        versions[version] = prompt
    return registry


def load_prompt(name: str, version: int | None = None) -> Prompt:
    """Return a prompt by name; the highest version unless one is pinned."""
    versions = _registry().get(name)
    if not versions:
        available = ", ".join(sorted(_registry())) or "(none)"
        raise KeyError(f"Unknown prompt {name!r}. Available: {available}")
    if version is None:
        version = max(versions)
    if version not in versions:
        raise KeyError(f"Prompt {name!r} has no version {version}. Available: {sorted(versions)}")
    return versions[version]


def render(name: str, *, version: int | None = None, **values: object) -> str:
    """Load and render a prompt in one call."""
    return load_prompt(name, version).render(**values)


def list_prompts() -> list[Prompt]:
    """Return the latest version of every known prompt (for introspection/tests)."""
    return [load_prompt(name) for name in sorted(_registry())]
