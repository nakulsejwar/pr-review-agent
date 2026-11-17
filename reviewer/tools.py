"""Read-only tools the agent can call. Everything is sandboxed to the diff and (optionally) a repo root."""
from __future__ import annotations
import ast, os, re
from pathlib import Path
from google.genai import types
from .diffparse import FileDiff

MAX_OUT = 6000  # chars returned per tool call


def _cap(s: str) -> str:
    return s if len(s) <= MAX_OUT else s[:MAX_OUT] + f"\n...[truncated {len(s)-MAX_OUT} chars]"


class ReviewTools:
    def __init__(self, files: dict[str, FileDiff], repo_root: str | None = None):
        self.files = files
        self.root = Path(repo_root).resolve() if repo_root else None

    # ---- tools -------------------------------------------------------
    def list_changed_files(self) -> dict:
        return {"files": [
            {"path": f.path, "added": f.added_count, "removed": f.removed_count,
             "new_file": f.is_new, "deleted": f.is_deleted} for f in self.files.values()]}

    def get_file_diff(self, path: str) -> dict:
        f = self.files.get(path)
        if not f:
            return {"error": f"'{path}' is not in the diff. Use list_changed_files."}
        return {"path": path, "diff_with_new_line_numbers": _cap(f.numbered())}

    def read_file(self, path: str, start: int = 1, end: int = 120) -> dict:
        """Read surrounding code from the repo checkout (needs --repo)."""
        if not self.root:
            return {"error": "No repo checkout available; only the diff can be inspected."}
        p = (self.root / path).resolve()
        if self.root not in p.parents and p != self.root:
            return {"error": "Path escapes the repo root."}
        if not p.is_file():
            return {"error": f"'{path}' not found in repo."}
        lines = p.read_text(errors="replace").splitlines()
        start, end = max(1, int(start)), min(len(lines), int(end), int(start) + 200)
        body = "\n".join(f"{i:>4} {lines[i-1]}" for i in range(start, end + 1))
        return {"path": path, "total_lines": len(lines), "content": _cap(body)}

    def search_repo(self, pattern: str) -> dict:
        """Regex search over repo files (or just the diff when there is no checkout)."""
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"error": f"bad regex: {e}"}
        hits = []
        if self.root:
            for dp, dn, fn in os.walk(self.root):
                dn[:] = [d for d in dn if d not in {".git", "node_modules", "__pycache__", ".venv"}]
                for name in fn:
                    fp = Path(dp) / name
                    try:
                        for i, l in enumerate(fp.read_text(errors="ignore").splitlines(), 1):
                            if rx.search(l):
                                hits.append(f"{fp.relative_to(self.root)}:{i}: {l.strip()[:160]}")
                                if len(hits) >= 40: return {"matches": hits, "truncated": True}
                    except OSError:
                        pass
        else:
            for f in self.files.values():
                for i, l in f.new_lines.items():
                    if rx.search(l):
                        hits.append(f"{f.path}:{i}: {l.strip()[:160]}")
        return {"matches": hits[:40]}

    def find_related_tests(self, path: str) -> dict:
        """Does the diff (or repo) touch a test file for this source file?"""
        stem = Path(path).stem
        pat = re.compile(rf"(test_{re.escape(stem)}|{re.escape(stem)}[._-]?(test|spec)s?)", re.I)
        in_diff = [p for p in self.files if pat.search(Path(p).name)]
        in_repo = []
        if self.root:
            for dp, dn, fn in os.walk(self.root):
                dn[:] = [d for d in dn if d not in {".git", "node_modules", "__pycache__", ".venv"}]
                in_repo += [str((Path(dp) / n).relative_to(self.root)) for n in fn if pat.search(n)]
        return {"tests_changed_in_this_diff": in_diff, "tests_existing_in_repo": in_repo[:20],
                "repo_checkout_available": bool(self.root)}

    def check_python_syntax(self, path: str) -> dict:
        """Syntax-check the new version of a .py file reconstructed from the diff (+ pyflakes if installed)."""
        f = self.files.get(path)
        if not f or not path.endswith(".py"):
            return {"error": "Not a changed .py file."}
        if self.root and (self.root / path).is_file():
            src = (self.root / path).read_text(errors="replace")
        elif f.is_new:
            src = "\n".join(f.new_lines[k] for k in sorted(f.new_lines))
        else:
            return {"note": "Partial file only (no checkout); syntax check skipped."}
        try:
            ast.parse(src)
        except SyntaxError as e:
            return {"syntax_ok": False, "error": f"line {e.lineno}: {e.msg}"}
        out = {"syntax_ok": True}
        try:
            from pyflakes.api import check
            from pyflakes.reporter import Reporter
            import io
            buf = io.StringIO(); check(src, path, Reporter(buf, buf))
            out["pyflakes"] = buf.getvalue().splitlines()[:20]
        except ImportError:
            pass
        return out

    # ---- dispatch ----------------------------------------------------
    def call(self, name: str, args: dict) -> dict:
        fn = {"list_changed_files": self.list_changed_files, "get_file_diff": self.get_file_diff,
              "read_file": self.read_file, "search_repo": self.search_repo,
              "find_related_tests": self.find_related_tests,
              "check_python_syntax": self.check_python_syntax}.get(name)
        if not fn:
            return {"error": f"Unknown tool '{name}'."}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"Bad arguments: {e}"}
        except Exception as e:  # never let a tool crash the loop
            return {"error": f"{type(e).__name__}: {e}"}


def _s(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}

DECLARATIONS = [
    types.FunctionDeclaration(name="list_changed_files", description="List files in the change with added/removed line counts.",
        parameters_json_schema=_s({}, [])),
    types.FunctionDeclaration(name="get_file_diff", description="Get the diff of one file, annotated with new-file line numbers.",
        parameters_json_schema=_s({"path": {"type": "string"}}, ["path"])),
    types.FunctionDeclaration(name="read_file", description="Read lines of a file from the repo checkout for surrounding context.",
        parameters_json_schema=_s({"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"])),
    types.FunctionDeclaration(name="search_repo", description="Regex search for callers/usages of a symbol.",
        parameters_json_schema=_s({"pattern": {"type": "string"}}, ["pattern"])),
    types.FunctionDeclaration(name="find_related_tests", description="Check whether tests exist/changed for a source file.",
        parameters_json_schema=_s({"path": {"type": "string"}}, ["path"])),
    types.FunctionDeclaration(name="check_python_syntax", description="Syntax check + pyflakes on a changed Python file.",
        parameters_json_schema=_s({"path": {"type": "string"}}, ["path"])),
]
