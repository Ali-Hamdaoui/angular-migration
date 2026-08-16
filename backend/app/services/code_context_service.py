"""Code context extraction and retrieval service (V2 F20)."""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.code_context import CodeContextBundle, CodeContextUnit
from app.services.assistant_context_budget import count_tokens


class CodeContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


DEFAULT_BUDGET = 6000
#: Max lines per excerpt; bounded so a single file cannot starve the budget.
MAX_EXCERPT_LINES = 60
MAX_FILES = 12


class CodeContextService:
    """Extract bounded, relevant code context for affected symbols (F20)."""

    def __init__(self, *, budget: int = DEFAULT_BUDGET) -> None:
        self._budget = budget

    def retrieve_context(
        self,
        workspace: Path,
        symbols: list[str],
        template_selectors: list[str] | None = None,
        *,
        budget: int | None = None,
    ) -> CodeContextBundle:
        """Retrieve bounded context for affected symbols across the workspace (F20-03)."""
        budget = budget or self._budget
        units: list[CodeContextUnit] = []
        source_files = self._discover_source_files(workspace)

        for path in source_files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for symbol in symbols:
                excerpts = _extract_symbol_blocks(text, symbol)
                for start, end in excerpts:
                    units.append(
                        _make_unit(str(path), "typescript", symbol, text, start, end)
                    )
            if template_selectors:
                for selector in template_selectors:
                    excerpts = _extract_template_blocks(text, selector)
                    for start, end in excerpts:
                        units.append(
                            _make_unit(str(path), "template", selector, text, start, end)
                        )

        return self._assemble(units, budget)

    def extract_ts_context(self, source_text: str, symbol: str) -> list[CodeContextUnit]:
        """Extract TypeScript context blocks for a symbol (F20-01)."""
        units = []
        for start, end in _extract_symbol_blocks(source_text, symbol):
            units.append(_make_unit("<source>", "typescript", symbol, source_text, start, end))
        return units

    def extract_template_context(self, template_text: str, selector: str) -> list[CodeContextUnit]:
        """Extract Angular template context for a selector (F20-02)."""
        units = []
        for start, end in _extract_template_blocks(template_text, selector):
            units.append(_make_unit("<template>", "template", selector, template_text, start, end))
        return units

    @staticmethod
    def _assemble(units: list[CodeContextUnit], budget: int) -> CodeContextBundle:
        """Bound the assembled bundle under the token budget (F20-04).

        Units are ordered by (kind, path, symbol) for determinism; the bundle
        accepts units until the running token total would exceed the budget.
        """
        units.sort(key=lambda u: (u.kind, u.path, u.symbol, u.start_line))
        bounded: list[CodeContextUnit] = []
        total = 0
        truncated = False
        for unit in units:
            if total + unit.token_count > budget:
                truncated = True
                continue
            bounded.append(unit)
            total += unit.token_count
        bundle = CodeContextBundle(units=tuple(bounded), total_tokens=total, budget=budget, truncated=truncated)
        return bundle.bind_checksum()

    def _discover_source_files(self, workspace: Path) -> list[Path]:
        if not workspace.is_dir():
            raise CodeContextError("WORKSPACE_MISSING", f"workspace {workspace} is not a directory")
        files: list[Path] = []
        for pattern in ("**/*.ts", "**/*.html"):
            files.extend(sorted(workspace.glob(pattern)))
        # Exclude build artifacts and node_modules.
        files = [f for f in files if "node_modules" not in f.parts and "dist" not in f.parts and "build" not in f.parts]
        return files[:MAX_FILES]


def _make_unit(path: str, kind: str, symbol: str, text: str, start: int, end: int) -> CodeContextUnit:
    excerpt = "\n".join(text.splitlines()[start - 1 : end])
    return CodeContextUnit(
        path=path, kind=kind, symbol=symbol, excerpt=excerpt,
        start_line=start, end_line=end, token_count=count_tokens(excerpt),
    )


def _extract_symbol_blocks(text: str, symbol: str) -> list[tuple[int, int]]:
    """Lexical extraction: enclosing block around each symbol occurrence."""
    lines = text.splitlines()
    results: list[tuple[int, int]] = []
    seen: set[int] = set()
    for index, line in enumerate(lines, start=1):
        if symbol not in line or index in seen:
            continue
        if re.search(rf"\b{re.escape(symbol)}\b", line) is None:
            continue
        start, end = _enclosing_block(lines, index, symbol)
        seen.update(range(start, end + 1))
        results.append((start, end))
    return results


def _extract_template_blocks(text: str, selector: str) -> list[tuple[int, int]]:
    """Lexical extraction: the element (and its attributes) for a template selector."""
    lines = text.splitlines()
    results: list[tuple[int, int]] = []
    for index, line in enumerate(lines, start=1):
        if selector not in line:
            continue
        start = index
        end = index
        # If the tag opens on this line and continues, extend to its close.
        if re.search(rf"<{re.escape(selector)}[^>]*>", line) and "</" + selector + ">" not in line:
            for cursor in range(index, min(index + MAX_EXCERPT_LINES, len(lines) + 1)):
                if f"</{selector}>" in lines[cursor - 1]:
                    end = cursor
                    break
        results.append((start, end))
    return results


def _enclosing_block(lines: list[str], index: int, symbol: str) -> tuple[int, int]:
    start = max(1, index - 8)
    end = min(len(lines), index + 12)
    depth = 0
    for cursor in range(index, start - 1, -1):
        depth += lines[cursor - 1].count("}")
        depth -= lines[cursor - 1].count("{")
        if depth >= 1 and cursor > start:
            start = cursor
            break
        if lines[cursor - 1].strip().startswith(("export ", "function ", "class ", "const ", "import ")):
            start = cursor
    for cursor in range(index, end + 1):
        depth += lines[cursor - 1].count("{")
        depth -= lines[cursor - 1].count("}")
        if depth <= 0 and cursor > index:
            end = cursor
            break
    return start, end
