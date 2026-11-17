import argparse, subprocess, sys
from .agent import ReviewAgent, DEFAULT_MODEL
from .render import to_markdown

def main():
    ap = argparse.ArgumentParser(description="AI code-change reviewer (Gemini)")
    ap.add_argument("diff", nargs="?", help="Path to .diff file, or '-' for stdin")
    ap.add_argument("--git", metavar="RANGE", help="Run `git diff RANGE` in --repo, e.g. main...HEAD")
    ap.add_argument("--repo", help="Repo checkout for extra context tools")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true", help="Print raw JSON instead of markdown")
    ap.add_argument("-v", "--verbose", action="store_true", help="Show tool calls")
    a = ap.parse_args()
    if a.git:
        diff = subprocess.run(["git", "-C", a.repo or ".", "diff", a.git], capture_output=True, text=True, check=True).stdout
    elif a.diff == "-" or (a.diff is None and not sys.stdin.isatty()):
        diff = sys.stdin.read()
    elif a.diff:
        diff = open(a.diff).read()
    else:
        ap.error("provide a diff file, '-', or --git RANGE")
    rep = ReviewAgent(model=a.model, repo_root=a.repo, verbose=a.verbose).review(diff)
    print(rep.model_dump_json(indent=2) if a.json else to_markdown(rep))

if __name__ == "__main__":
    main()
