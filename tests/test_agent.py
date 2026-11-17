import json
from types import SimpleNamespace as NS
from google.genai import types
from reviewer.agent import ReviewAgent
from reviewer.diffparse import parse_diff
from reviewer.tools import ReviewTools

DIFF = open("samples/login.diff").read()


def test_parse_line_numbers():
    f = parse_diff(DIFF)["auth/login.py"]
    assert 5 in f.added or 6 in f.added
    assert any("md5" in l for l in f.new_lines.values())
    assert "auth/login.py" in parse_diff(DIFF) and "README.md" in parse_diff(DIFF)
    assert "  " in f.numbered()


def test_tools_sandbox_and_errors(tmp_path):
    t = ReviewTools(parse_diff(DIFF), repo_root=str(tmp_path))
    assert "escapes" in t.read_file("../../etc/passwd")["error"]
    assert "error" in t.get_file_diff("nope.py")
    assert "error" in t.call("rm_rf", {})
    assert "error" in t.call("get_file_diff", {"bad": 1})
    assert t.find_related_tests("auth/login.py")["tests_changed_in_this_diff"] == []


class Fake:
    """Scripted stand-in for genai.Client."""
    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.models = self
    def generate_content(self, model, contents, config):
        self.calls += 1
        return self.script.pop(0)


def fc(name, args):
    c = types.Content(role="model", parts=[types.Part.from_function_call(name=name, args=args)])
    return NS(function_calls=[NS(name=name, args=args)], candidates=[NS(content=c)], text=None, parsed=None)

def txt(s):
    return NS(function_calls=None, candidates=[NS(content=None)], text=s, parsed=None)


GOOD = {"summary": "s", "verdict": "request_changes", "findings": [
    {"category": "risk", "severity": "high", "file": "auth/login.py", "line": 25, "title": "SQL injection",
     "explanation": "f-string query", "suggestion": "parametrize", "evidence": "WHERE name = '{username}'"},
    {"category": "bug", "severity": "high", "file": "ghost.py", "line": 1, "title": "x", "explanation": "x", "suggestion": "x"},
    {"category": "bug", "severity": "high", "file": "auth/login.py", "line": 999, "title": "bad line", "explanation": "x",
     "suggestion": "x", "evidence": "does not exist in diff"}]}


def test_loop_tools_retry_and_grounding():
    fake = Fake([fc("get_file_diff", {"path": "auth/login.py"}), txt("done investigating"),
                 txt("not json at all"), txt(json.dumps(GOOD))])
    agent = ReviewAgent(client=fake)
    rep = agent.review(DIFF)
    kinds = [t["t"] for t in agent.trace]
    assert "tool" in kinds and "schema_retry" in kinds
    files = [f.file for f in rep.findings]
    assert "ghost.py" not in files                     # hallucinated file dropped
    bad = [f for f in rep.findings if f.title == "bad line"][0]
    assert bad.line is None and not bad.verified and bad.severity.value == "medium"
    sqli = [f for f in rep.findings if f.title == "SQL injection"][0]
    assert sqli.verified


def test_tool_budget_and_duplicates():
    script = [fc("list_changed_files", {})] * 2 + [txt("ok"), txt(json.dumps(GOOD))]
    agent = ReviewAgent(client=Fake(script)); agent.review(DIFF)
    oks = [t["ok"] for t in agent.trace if t["t"] == "tool"]
    assert oks == [True, False]                        # duplicate rejected


def test_empty_diff():
    import pytest
    with pytest.raises(ValueError):
        ReviewAgent(client=Fake([])).review("hello")
