"""Guard (2026-10-22): the Monthly Bankroll Policy Review failed because its hand-written pip list lacked a
package the code imported. requirements.txt is now the canonical list; this fails loudly if src/ imports a
third-party package it does not name, or a workflow installs an ad-hoc list that drops a needed package."""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: import name -> distribution name
DIST = {"sklearn": "scikit-learn", "yaml": "pyyaml", "dotenv": "python-dotenv"}
#: imported only by single optional modules whose workflow installs them as explicit extras
OPTIONAL = {"lightgbm", "matplotlib", "jsonschema"}
LOCAL = {"src", "config", "tests", "scripts", "player_model"}           # player_model = v9, via V9_LOCAL


def _requirements() -> set[str]:
    out = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(re.split(r"[<>=!~\[ ]", line, 1)[0].lower())
    return out


def _third_party_imports() -> set[str]:
    std = set(sys.stdlib_module_names) | {"__future__"}
    found = set()
    for f in list((ROOT / "src").rglob("*.py")) + list((ROOT / "config").rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods = [n.module]
            else:
                continue
            for m in mods:
                top = m.split(".")[0]
                if top not in std and top not in LOCAL:
                    found.add(top)
    return found


def test_requirements_cover_every_third_party_import():
    req = _requirements()
    missing = sorted(m for m in _third_party_imports() - OPTIONAL if DIST.get(m, m).lower() not in req)
    assert not missing, f"imported by src/ but not in requirements.txt: {missing}"


def test_monthly_bankroll_workflow_uses_the_canonical_file():
    wf = (ROOT / ".github" / "workflows" / "monthly_bankroll_policy.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt" in wf


def test_bankroll_code_imports_resolve_with_requirements_only():
    req = _requirements()
    for f in (ROOT / "src" / "bankroll").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else ([n.module] if n.level == 0 and n.module else [])
                for m in names:
                    top = m.split(".")[0]
                    if top not in set(sys.stdlib_module_names) | LOCAL | {"__future__"}:
                        assert DIST.get(top, top).lower() in req, f"{f.name} imports {top}"
