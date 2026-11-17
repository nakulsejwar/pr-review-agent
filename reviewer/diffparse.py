"""Minimal unified-diff parser: maps each file to its added/context lines (new-file numbering)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    raw: list[str] = field(default_factory=list)
    new_lines: dict[int, str] = field(default_factory=dict)   # added + context lines
    added: set[int] = field(default_factory=set)
    is_new: bool = False
    is_deleted: bool = False

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def removed_count(self) -> int:
        return sum(1 for l in self.raw if l.startswith("-") and not l.startswith("---"))

    def numbered(self) -> str:
        """Diff text with new-file line numbers prefixed, so the model can cite them accurately."""
        out, n = [], None
        for l in self.raw:
            m = HUNK.match(l)
            if m:
                n = int(m.group(1)); out.append(l); continue
            if n is None:
                out.append(l); continue
            if l.startswith("-"):
                out.append(f"     {l}")
            else:
                out.append(f"{n:>4} {l}"); n += 1
        return "\n".join(out)


def parse_diff(text: str) -> dict[str, FileDiff]:
    files: dict[str, FileDiff] = {}
    cur: FileDiff | None = None
    n = 0
    for line in text.splitlines():
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            cur = FileDiff(path=m.group(2) if m else line)
            files[cur.path] = cur
            cur.raw = []
            n = 0
            continue
        if cur is None:
            # plain `diff -u` without git header
            if line.startswith("+++ "):
                p = line[4:].split("\t")[0]
                p = p[2:] if p.startswith("b/") else p
                cur = FileDiff(path=p); files[p] = cur
            continue
        if line.startswith("new file mode"):
            cur.is_new = True
        elif line.startswith("deleted file mode"):
            cur.is_deleted = True
        m = HUNK.match(line)
        if m:
            n = int(m.group(1))
            cur.raw.append(line)
            continue
        if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("index "):
            cur.raw.append(line)
            continue
        if not cur.raw or not any(HUNK.match(x) for x in cur.raw):
            cur.raw.append(line)
            continue
        cur.raw.append(line)
        if line.startswith("+"):
            cur.new_lines[n] = line[1:]; cur.added.add(n); n += 1
        elif line.startswith("-") or line.startswith("\\"):
            pass
        else:
            cur.new_lines[n] = line[1:] if line.startswith(" ") else line; n += 1
    return files
