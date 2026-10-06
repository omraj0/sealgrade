"""The audit rules.

Each rule looks for one concrete, checkable weakness and maps it to a published flaw class
(V1 to V8, see docs/TAXONOMY.md). Rules are heuristics over text and syntax trees: they do not run
the task and they can be wrong. They aim to be *specific* (point at a line and say why) and
*conservative* (prefer a low-severity note to a confident false alarm). The planted-flaw test suite in
``tests/test_audit_rules.py`` measures recall on seeded flaws and false alarms on a clean task.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath

from sealgrade.audit.dockerfile import (
    base_images,
    copy_sources,
    final_user,
    ignored,
    image_pin,
)
from sealgrade.audit.model import AuditTarget, Finding, Rule, Severity

# --- shared helpers ---------------------------------------------------------------------------

ANSWER_DIR = re.compile(r"^(tests?|solutions?|oracle|golden|answers?)$", re.I)
ANSWER_FILE = re.compile(
    r"^(expected[\w.-]*|answers?[\w.-]*|golden[\w.-]*|ground[_-]?truth[\w.-]*|solution\.[\w]+|"
    r"solve\.sh|conftest\.py|test_[\w.-]+\.py|[\w.-]+_test\.py)$",
    re.I,
)
COPY_ALL = {".", "./", "*", "/", "./*"}


def logical_lines(text: str) -> Iterator[tuple[int, str]]:
    """Shell-ish logical lines: backslash continuations joined, comments dropped."""
    pending = ""
    start = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not pending:
            start = number
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        pending += line
        stripped = pending.strip()
        pending = ""
        if stripped and not stripped.startswith("#"):
            yield start, stripped
    if pending.strip() and not pending.strip().startswith("#"):
        yield start, pending.strip()


def _looks_like_answer_path(path: str) -> bool:
    parts = [p for p in PurePosixPath(path.strip("/")).parts if p not in (".", "")]
    if not parts:
        return False
    if any(ANSWER_DIR.match(p) for p in parts[:-1]):
        return True
    return bool(ANSWER_DIR.match(parts[-1]) or ANSWER_FILE.match(parts[-1]))


def _context_files(target: AuditTarget) -> list[str]:
    """Files inside the image build context that ``.dockerignore`` does not exclude."""
    prefix = f"{target.build_context}/" if target.build_context else ""
    out = []
    for path in target.files:
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix) :]
        if relative == "Dockerfile" or relative == ".dockerignore":
            continue
        if not ignored(relative, target.dockerignore):
            out.append(relative)
    return sorted(out)


def _pytest_lines(target: AuditTarget) -> Iterator[tuple[str, int, str]]:
    for path in target.verifier_scripts:
        for number, line in logical_lines(target.text(path)):
            if re.search(r"\bpytest\b", line) and not re.match(r"^(echo|printf)\b", line):
                yield path, number, line


def _parse_python(target: AuditTarget, path: str) -> ast.Module | None:
    try:
        return ast.parse(target.text(path))
    except (SyntaxError, ValueError):
        return None


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    detail: str,
    path: str = "",
    line: int = 0,
    classes: tuple[str, ...] = (),
) -> Finding:
    return Finding(rule_id, severity, title, detail, path, line, classes)


# --- V2: answers reachable from the agent -----------------------------------------------------


def sg001_answers_copied(target: AuditTarget) -> Iterable[Finding]:
    if not target.dockerfile_path:
        return
    title = "Tests, solutions or answers are copied into the agent image"
    for instruction in target.dockerfile:
        if instruction.op not in ("COPY", "ADD"):
            continue
        sources = copy_sources(instruction)
        for source in sources:
            cleaned = source.lstrip("./") if source not in COPY_ALL else source
            if source in COPY_ALL:
                leaked = [f for f in _context_files(target) if _looks_like_answer_path(f)]
                if leaked:
                    shown = ", ".join(leaked[:4]) + (" ..." if len(leaked) > 4 else "")
                    yield _finding(
                        "SG001",
                        Severity.HIGH,
                        title,
                        f"`{instruction.op} {source}` copies the whole build context, which "
                        f"contains answer-like files that .dockerignore does not exclude: {shown}.",
                        target.dockerfile_path,
                        instruction.line,
                        ("V2",),
                    )
            elif _looks_like_answer_path(cleaned):
                yield _finding(
                    "SG001",
                    Severity.HIGH,
                    title,
                    f"`{instruction.op} {source}` places test, solution or answer material in the "
                    "image the agent runs in.",
                    target.dockerfile_path,
                    instruction.line,
                    ("V2",),
                )


def sg002_answer_like_files(target: AuditTarget) -> Iterable[Finding]:
    prefix = f"{target.build_context}/" if target.build_context else ""
    if not target.dockerfile_path:
        return
    already = {f.path for f in sg001_answers_copied(target)}
    for relative in _context_files(target):
        name = PurePosixPath(relative).name
        if re.match(
            r"^(expected[\w.-]*|answers?[\w.-]*|golden[\w.-]*|ground[_-]?truth[\w.-]*)$", name, re.I
        ):
            path = f"{prefix}{relative}"
            if path in already:
                continue
            yield _finding(
                "SG002",
                Severity.MEDIUM,
                "An answer-like file sits in the agent-visible directory",
                f"`{path}` looks like expected output. Anything in the build context may be reachable "
                "from the agent's container.",
                path,
                0,
                ("V2",),
            )


def sg019_git_history(target: AuditTarget) -> Iterable[Finding]:
    prefix = f"{target.build_context}/" if target.build_context else ""
    git_paths = [
        p for p in target.files if ".git" in PurePosixPath(p).parts and p.startswith(prefix)
    ]
    if not git_paths:
        return
    relative = [p[len(prefix) :] for p in git_paths]
    if all(ignored(r, target.dockerignore) for r in relative):
        return
    yield _finding(
        "SG019",
        Severity.MEDIUM,
        "A .git directory is part of the agent-visible build context",
        "Commit history can contain the fix or the answers (`git log -p`, packed objects).",
        git_paths[0],
        0,
        ("V2",),
    )


# --- V8: permissions and exposure -------------------------------------------------------------


def sg003_root_agent(target: AuditTarget) -> Iterable[Finding]:
    if not target.dockerfile_path:
        return
    user = final_user(target.dockerfile)
    agent_user = str((target.config.get("agent") or {}).get("user", "") or "")
    if (user in (None, "root", "0")) and agent_user in ("", "root", "0"):
        yield _finding(
            "SG003",
            Severity.MEDIUM,
            "The agent runs as root",
            "No non-root USER in the Dockerfile and no [agent] user is set. A root agent can replace "
            "binaries, edit any file and start privileged processes.",
            target.dockerfile_path,
            0,
            ("V8",),
        )


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-/+=]{12,}"
    ),
]


def sg004_secrets(target: AuditTarget) -> Iterable[Finding]:
    candidates = [p for p in target.files if p == target.dockerfile_path or p.endswith(".env")]
    for path in candidates:
        for number, line in logical_lines(target.text(path)):
            if any(p.search(line) for p in SECRET_PATTERNS):
                yield _finding(
                    "SG004",
                    Severity.HIGH,
                    "A credential appears to be baked into the environment",
                    "Anything in the image or its environment is readable by the agent.",
                    path,
                    number,
                    ("V8",),
                )
                break


HOST_ACCESS = re.compile(
    r"(?i)(--privileged|privileged:\s*true|/var/run/docker\.sock|docker\.sock|network_mode:\s*host|"
    r"--network[= ]host|cap_add|--cap-add|SYS_ADMIN)"
)


def sg011_host_access(target: AuditTarget) -> Iterable[Finding]:
    for path in sorted(target.files):
        if not (
            path == target.dockerfile_path
            or PurePosixPath(path).name.startswith(("docker-compose", "compose"))
            or path == "task.toml"
        ):
            continue
        for number, line in logical_lines(target.text(path)):
            if HOST_ACCESS.search(line):
                yield _finding(
                    "SG011",
                    Severity.HIGH,
                    "The environment grants privileged or host access",
                    f"`{line[:100]}` lets code in the sandbox reach the host or escalate.",
                    path,
                    number,
                    ("V8",),
                )


def sg025_network(target: AuditTarget) -> Iterable[Finding]:
    if target.kind != "harbor":
        return
    env = target.config.get("environment") or {}
    mode = str(env.get("network_mode", "")).lower()
    internet = env.get("allow_internet")
    if mode in ("none", "offline", "isolated") or internet is False:
        return
    if not target.dockerfile_path and not env:
        return
    yield _finding(
        "SG025",
        Severity.LOW,
        "The agent may have internet access",
        "With network access an agent can download reference solutions or datasets. Declare "
        'network_mode = "none" unless the task genuinely needs the internet.',
        "task.toml",
        0,
        ("V8",),
    )


# --- V1 / V3 / V7: how the verdict is produced ------------------------------------------------


def sg005_exit_code_reward(target: AuditTarget) -> Iterable[Finding]:
    for path in target.verifier_scripts:
        text = target.text(path)
        if "reward" not in text:
            continue
        uses_status = re.search(r"\$\?", text) or re.search(r"pytest[^\n]*&&\s*echo\s+1", text)
        validates = re.search(
            r"(?i)junit|ctrf|report\.json|results?\.json|expected_count|n_tests", text
        )
        if uses_status and not validates:
            number = next(
                (n for n, line in logical_lines(text) if "$?" in line or "&& echo 1" in line), 0
            )
            yield _finding(
                "SG005",
                Severity.MEDIUM,
                "The reward is derived from a process exit code alone",
                "Exit status can be forced to 0 (conftest hooks, import-time exits, trojaned "
                "interpreters). Read a structured report and require the expected number of tests.",
                path,
                number,
                ("V3", "V7"),
            )


def sg006_pytest_config(target: AuditTarget) -> Iterable[Finding]:
    mode = target.verifier_mode
    severity = Severity.LOW if mode == "separate" else Severity.HIGH
    for path, number, line in _pytest_lines(target):
        pinned = re.search(r"(\s-c\s|--config-file|--rootdir|--confcutdir)", line)
        if not pinned:
            yield _finding(
                "SG006",
                severity,
                "pytest configuration and conftest discovery are not pinned",
                "Without -c/--rootdir/--confcutdir pytest searches the test path's ancestors for "
                "pytest.ini, pyproject.toml, tox.ini and conftest.py, any of which an agent may have "
                "planted (for example --collect-only, or a hook that rewrites outcomes).",
                path,
                number,
                ("V3", "V7"),
            )


def sg007_plugin_autoload(target: AuditTarget) -> Iterable[Finding]:
    lines = list(_pytest_lines(target))
    if not lines:
        return
    scripts = " ".join(target.text(p) for p in target.verifier_scripts)
    dockerfile = " ".join(i.args for i in target.dockerfile if i.op == "ENV")
    if (
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in scripts
        or "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in dockerfile
    ):
        return
    path, number, _ = lines[0]
    severity = Severity.LOW if target.verifier_mode == "separate" else Severity.MEDIUM
    yield _finding(
        "SG007",
        severity,
        "pytest plugin autoloading is enabled",
        "Installed plugins load through entry points. Set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and pass "
        "the plugins you need explicitly with -p.",
        path,
        number,
        ("V3",),
    )


def sg008_interpreter_cwd(target: AuditTarget) -> Iterable[Finding]:
    workdirs = [i.args.strip() for i in target.dockerfile if i.op == "WORKDIR"]
    for path in target.verifier_scripts:
        text = target.text(path)
        in_tests = re.search(r"(?m)^\s*cd\s+[\"']?(/tests|\$\{?TEST)", text)
        for number, line in logical_lines(text):
            if not re.search(r"\bpython[\d.]*\s+-m\s+", line) or re.search(
                r"\bpython[\d.]*\s+-[a-zA-Z]*[IP]\b", line
            ):
                continue
            if in_tests:
                continue
            agent_dir = workdirs[-1] if workdirs else "the container's default directory"
            yield _finding(
                "SG008",
                Severity.MEDIUM,
                "The interpreter starts in an agent-writable directory",
                f"`python -m ...` puts the current directory ({agent_dir}) first on sys.path, so a "
                "file the agent wrote there (argparse.py, pytest/, sitecustomize) can run instead of "
                "the real module. Use `python -I`, or `cd` to a directory the agent cannot write.",
                path,
                number,
                ("V1", "V3"),
            )
            return


def sg009_permissive_modes(target: AuditTarget) -> Iterable[Finding]:
    for instruction in target.dockerfile:
        if instruction.op != "RUN":
            continue
        text = instruction.args
        if re.search(r"chmod\s+(-R\s+)?(0?777|a\+[rwx]*w|o\+[rwx]*w)", text) and re.search(
            r"/(logs|tests|solution)\b", text
        ):
            yield _finding(
                "SG009",
                Severity.MEDIUM,
                "World-writable permissions on verifier paths",
                f"`{text[:90]}` lets the agent edit the reward or test locations.",
                target.dockerfile_path or "",
                instruction.line,
                ("V7",),
            )


def sg010_report_without_count(target: AuditTarget) -> Iterable[Finding]:
    scripts = [p for p in target.tests_files if p.endswith((".sh", ".py"))]
    blob = chr(10).join(target.text(p) for p in scripts)
    if not re.search(r"(?i)(junit|ctrf)", blob):
        return
    parsers = [
        p
        for p in scripts
        if re.search(
            r"(json\.load|ET\.parse|fromstring|xml\.etree|(?<![A-Za-z0-9_])jq(?![A-Za-z0-9_]))",
            target.text(p),
        )
    ]
    if not parsers:
        return
    counts = re.search(
        r"(?i)(tests|total|num_tests|n_tests)\s*(==|!=|>=)\s*(\d+|len\(|expected)"
        r"|expected[_a-z]*\s*(==|!=)",
        blob,
    )
    if not counts:
        yield _finding(
            "SG010",
            Severity.MEDIUM,
            "A test report is trusted without checking the test count",
            "A forged or truncated report with zero failures looks like a pass. Require the report "
            "to account for exactly the expected number of tests, with none skipped.",
            parsers[0],
            0,
            ("V7",),
        )


def sg021_stdout_parsing(target: AuditTarget) -> Iterable[Finding]:
    for path in target.verifier_scripts:
        text = target.text(path)
        if "reward" not in text:
            continue
        for number, line in logical_lines(text):
            decides = re.search(r"^(if|elif)\b.*\bgrep\b", line) or re.search(
                r"\bgrep\b[^|]*(&&|\|\|)", line
            )
            runner_words = re.search(r"\b(PASSED|passed|FAILED|failed)\b|\bPASS\b(?!\s+CODE)", line)
            if decides and runner_words:
                yield _finding(
                    "SG021",
                    Severity.MEDIUM,
                    "Program output decides the reward",
                    "Text printed by the submission or by a process it can influence is not evidence. "
                    "Decide from structured data produced by trusted code.",
                    path,
                    number,
                    ("V7",),
                )
                break


def sg024_shared_environment(target: AuditTarget) -> Iterable[Finding]:
    if target.kind != "harbor":
        return  # SealGrade-native tasks get their isolation from the tier, not the task
    if not target.dockerfile_path and not target.config:
        return
    if target.verifier_mode == "separate":
        return
    yield _finding(
        "SG024",
        Severity.MEDIUM,
        "The agent and the verifier share one environment",
        "Edits to binaries, startup hooks, files and background processes made during the agent "
        "phase persist into verification. Use a separate verifier environment that receives only "
        'declared artifacts (Harbor: [verifier] environment_mode = "separate").',
        "task.toml",
        0,
        ("V1",),
    )


def sg014_remote_code(target: AuditTarget) -> Iterable[Finding]:
    pipe = re.compile(r"(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b")
    for path in target.verifier_scripts:
        for number, line in logical_lines(target.text(path)):
            if pipe.search(line):
                yield _finding(
                    "SG014",
                    Severity.MEDIUM,
                    "Remote code is piped into a shell at verification time",
                    "The verifier now depends on the network and on whatever the URL serves that day. "
                    "Bake the tool into the image at a pinned version.",
                    path,
                    number,
                    ("V3", "V7"),
                )
    for instruction in target.dockerfile:
        if instruction.op == "RUN" and pipe.search(instruction.args):
            yield _finding(
                "SG014",
                Severity.LOW,
                "Remote code is piped into a shell while building the image",
                "Prefer a pinned package or a checksum-verified download.",
                target.dockerfile_path or "",
                instruction.line,
                ("V3",),
            )


# --- V6: reproducibility and weak verification ------------------------------------------------


def sg012_floating_base(target: AuditTarget) -> Iterable[Finding]:
    stages: set[str] = set()
    for instruction in target.dockerfile:
        if instruction.op != "FROM":
            continue
        tokens = instruction.args.split()
        alias = (
            tokens[tokens.index("AS") + 1]
            if "AS" in [t.upper() for t in tokens] and len(tokens) > 2
            else ""
        )
        refs = base_images([instruction])
        if refs and refs[0] not in stages:
            pin = image_pin(refs[0])
            if pin == "latest":
                yield _finding(
                    "SG012",
                    Severity.MEDIUM,
                    "The base image tag floats",
                    f"`FROM {refs[0]}` changes over time; two runs of the same task can differ.",
                    target.dockerfile_path or "",
                    instruction.line,
                    ("V6",),
                )
            elif pin == "tag":
                yield _finding(
                    "SG012",
                    Severity.LOW,
                    "The base image is not pinned by digest",
                    f"`FROM {refs[0]}`: tags can be re-pushed. Pin with @sha256:... for reproducibility.",
                    target.dockerfile_path or "",
                    instruction.line,
                    ("V6",),
                )
        if alias:
            stages.add(alias)


def sg013_unpinned_packages(target: AuditTarget) -> Iterable[Finding]:
    install = re.compile(r"\b(pip3?|uv pip|npm)\s+install\b([^\n;&|]*)|--with\s+(\S+)")
    for path in target.verifier_scripts:
        for number, line in logical_lines(target.text(path)):
            for match in install.finditer(line):
                if match.group(3):
                    packages = [match.group(3)]
                else:
                    packages = [
                        t
                        for t in match.group(2).split()
                        if not t.startswith("-") and "/" not in t and not t.endswith(".txt")
                    ]
                loose = [p for p in packages if not re.search(r"(==|@|===)", p)]
                if loose:
                    yield _finding(
                        "SG013",
                        Severity.MEDIUM,
                        "Packages are installed unpinned at verification time",
                        f"`{', '.join(loose)}` can resolve to a different version tomorrow. Pin exact "
                        "versions (pip with ==) or bake them into the image.",
                        path,
                        number,
                        ("V6",),
                    )
                    return


def sg015_substring_assertions(target: AuditTarget) -> Iterable[Finding]:
    for path in target.test_python:
        tree = _parse_python(target, path)
        if tree is None:
            continue
        hits: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
                ops = node.test.ops
                sides = [node.test.left, *node.test.comparators]
                if any(isinstance(o, (ast.In, ast.NotIn)) for o in ops) and any(
                    isinstance(s, ast.Constant) and isinstance(s.value, str) for s in sides
                ):
                    hits.append(node.lineno)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in (
                    "assertIn",
                    "assertNotIn",
                    "assertRegex",
                    "assertRegexpMatches",
                ):
                    hits.append(node.lineno)
        if hits:
            yield _finding(
                "SG015",
                Severity.MEDIUM,
                "Assertions check substrings instead of exact values",
                f"{len(hits)} assertion(s) test membership in a string; keyword stuffing satisfies them "
                "without producing the right answer. Compare complete, normalised values.",
                path,
                hits[0],
                ("V5",),
            )
    # The same weakness in shell: an unanchored grep that *decides* the outcome.
    for path in target.verifier_scripts:
        for number, line in logical_lines(target.text(path)):
            decides = re.search(r"^(if|elif)\b.*\bgrep\b", line) or re.search(
                r"\bgrep\b[^|]*(&&|\|\|)", line
            )
            anchored = re.search(r"grep\s+(-[a-zA-Z]*[xw][a-zA-Z]*\s)", line) or re.search(
                r"grep[^\"']*[\"']\^[^\"']*\$[\"']", line
            )
            if decides and not anchored:
                yield _finding(
                    "SG015",
                    Severity.MEDIUM,
                    "A substring match decides the outcome",
                    "`grep` without an anchor (or -x/-w) passes whenever the text appears anywhere in "
                    "what the submission wrote. Compare the complete expected value.",
                    path,
                    number,
                    ("V5",),
                )
                break


def _const_number(node: ast.AST) -> float | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    return None


def sg016_loose_tolerance(target: AuditTarget) -> Iterable[Finding]:
    relative = {"rel", "rel_tol", "rtol"}
    absolute = {"abs", "abs_tol", "atol"}
    for path in target.test_python:
        tree = _parse_python(target, path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if name in ("approx", "isclose", "allclose", "assert_allclose", "assertAlmostEqual"):
                for keyword in node.keywords:
                    value = _const_number(keyword.value)
                    if value is None:
                        continue
                    too_loose = (
                        (keyword.arg in relative and value >= 0.01)
                        or (keyword.arg in absolute and value >= 1.0)
                        or (keyword.arg == "places" and value <= 1)
                        or (keyword.arg == "delta" and value >= 1.0)
                    )
                    if too_loose:
                        yield _finding(
                            "SG016",
                            Severity.MEDIUM,
                            "A numeric tolerance is loose enough to accept wrong answers",
                            f"`{name}({keyword.arg}={value:g})` accepts large errors. Justify every tolerance "
                            "from the problem, and use the tightest one the legitimate solution meets.",
                            path,
                            node.lineno,
                            ("V5", "V6"),
                        )
                        break


def _is_weak_assert(test: ast.expr) -> bool:
    if isinstance(test, ast.Call):
        name = (
            test.func.attr if isinstance(test.func, ast.Attribute) else getattr(test.func, "id", "")
        )
        return name in (
            "exists",
            "isfile",
            "isdir",
            "callable",
            "hasattr",
            "isinstance",
            "any",
            "all",
            "bool",
        )
    if isinstance(test, ast.Name):
        return True
    if isinstance(test, ast.Compare):
        ops, comps = test.ops, test.comparators
        if any(isinstance(o, (ast.Is, ast.IsNot)) for o in ops):
            return True
        if isinstance(test.left, ast.Call) and getattr(test.left.func, "id", "") == "len":
            return any(isinstance(o, (ast.Gt, ast.GtE, ast.NotEq)) for o in ops) and all(
                (_const_number(c) in (0.0, 1.0)) for c in comps
            )
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _is_weak_assert(test.operand)
    return False


def sg017_weak_assertions(target: AuditTarget) -> Iterable[Finding]:
    for path in target.test_python:
        tree = _parse_python(target, path)
        if tree is None:
            continue
        weak: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
                if asserts and all(_is_weak_assert(a.test) for a in asserts):
                    weak.append(node.name)
        if weak:
            yield _finding(
                "SG017",
                Severity.MEDIUM,
                "Tests only check that something exists, not that it is right",
                f"{', '.join(weak[:5])}: every assertion is an existence, type or non-empty check. "
                "A stub passes these. Assert on the actual values.",
                path,
                0,
                ("V6",),
            )


def sg018_no_effective_tests(target: AuditTarget) -> Iterable[Finding]:
    if target.kind != "harbor":
        return
    # A Python test "checks" something if it asserts, branches on a comparison, raises or exits.
    has_assert = False
    for path in target.test_python:
        tree = _parse_python(target, path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            is_exit = isinstance(node, ast.Call) and getattr(
                node.func, "attr", getattr(node.func, "id", "")
            ) in ("exit", "_exit")
            if (
                isinstance(node, ast.Assert | ast.Raise)
                or (isinstance(node, ast.If) and isinstance(node.test, ast.Compare))
                or is_exit
                or (
                    isinstance(node, ast.Attribute)
                    and node.attr in ("assertEqual", "assertTrue", "assertIn", "assertRaises")
                )
            ):
                has_assert = True
                break
    code = "\n".join(
        line for p in target.verifier_scripts for _, line in logical_lines(target.text(p))
    )
    # In shell or batch, any conditional or comparison tool counts as "something checks the result".
    # Running pytest or python on its own does not: that is only as good as the tests it runs.
    compares = re.search(
        r"(\[\[?\s|\btest\s|\bif\b|\b(diff|cmp|grep|awk|jq|md5sum|sha256sum|findstr|fc)\b)",
        code,
    )
    if any(LLM_MODULES.search(target.text(p)) for p in target.test_python):
        return  # an LLM judge is a verifier (SG020 covers its weaknesses)
    if not target.verifier_scripts and not target.test_python:
        yield _finding(
            "SG018",
            Severity.HIGH,
            "The task has no verifier",
            "No tests/ scripts or Python tests were found, so nothing decides the reward.",
            "tests",
            0,
            ("V6",),
        )
    elif not has_assert and not compares:
        yield _finding(
            "SG018",
            Severity.HIGH,
            "The tests contain no assertions",
            "Nothing in tests/ compares an outcome with an expectation, so any submission can pass.",
            "tests",
            0,
            ("V6",),
        )


def sg022_nondeterministic_truth(target: AuditTarget) -> Iterable[Finding]:
    for path in target.test_python:
        text = target.text(path)
        seeded = re.search(r"(random\.seed|\.seed\(|default_rng\(|Random\(|PYTHONHASHSEED)", text)
        volatile = re.search(
            r"(random\.(random|randint|choice|shuffle|sample)\(|time\.time\(|datetime\.now\(|uuid4\()",
            text,
        )
        if volatile and not seeded:
            yield _finding(
                "SG022",
                Severity.LOW,
                "Ground truth may depend on randomness or the clock",
                "Unseeded randomness or the current time makes expected values differ between runs. "
                "Seed generators and fix timestamps.",
                path,
                0,
                ("V6",),
            )


def sg026_few_cases(target: AuditTarget) -> Iterable[Finding]:
    if target.kind != "sealgrade":
        return
    cases = target.text(str((target.config.get("judge") or {}).get("cases", "cases.jsonl")))
    count = sum(1 for line in cases.splitlines() if line.strip())
    if count < 20:
        yield _finding(
            "SG026",
            Severity.LOW,
            "Very few graded cases",
            f"{count} case(s). A small set is easy to memorise and rarely covers edge cases; aim for "
            "dozens, including boundaries and invalid input.",
            "cases.jsonl",
            0,
            ("V6",),
        )


# --- V4 and V1: judges and shared processes ----------------------------------------------------

LLM_MODULES = re.compile(
    r"^\s*(import|from)\s+(openai|anthropic|litellm|ollama|mistralai|cohere|langchain|google\.generativeai|google\.genai)\b",
    re.M,
)
AGENT_OUTPUT_NAMES = {
    "output",
    "response",
    "answer",
    "result",
    "submission",
    "text",
    "content",
    "solution",
    "transcript",
}


def sg020_llm_judge(target: AuditTarget) -> Iterable[Finding]:
    for path in target.test_python:
        text = target.text(path)
        if not LLM_MODULES.search(text):
            continue
        tree = _parse_python(target, path)
        injected: list[int] = []
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    names = {
                        v.value.id
                        for v in node.values
                        if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name)
                    }
                    if names & AGENT_OUTPUT_NAMES:
                        literal = "".join(
                            v.value
                            for v in node.values
                            if isinstance(v, ast.Constant) and isinstance(v.value, str)
                        )
                        delimited = "```" in literal or re.search(r"</?\w+>", literal)
                        if not delimited:
                            injected.append(node.lineno)
        if injected:
            yield _finding(
                "SG020",
                Severity.MEDIUM,
                "An LLM judge prompt is built directly from agent output",
                "Text the agent controls is interpolated into the judge's prompt with no delimiter or "
                "escaping, so it can instruct the judge (prompt injection). Quote it with a random "
                "delimiter, use structured output, keep rubrics out of band.",
                path,
                injected[0],
                ("V4",),
            )
        else:
            yield _finding(
                "SG020",
                Severity.LOW,
                "The task uses an LLM judge",
                "LLM judges are non-deterministic and injectable. Prefer deterministic checks wherever "
                "the task allows.",
                path,
                0,
                ("V4",),
            )


def sg023_shared_process(target: AuditTarget) -> Iterable[Finding]:
    pattern = re.compile(
        r"(sys\.path\.(insert|append)\(|importlib\.import_module|spec_from_file_location|runpy\.|\bexec\(|\beval\(|__import__\()"
    )
    for path in target.test_python:
        for number, line in enumerate(target.text(path).splitlines(), 1):
            if pattern.search(line):
                yield _finding(
                    "SG023",
                    Severity.LOW,
                    "Candidate code is imported into the test process",
                    "When tests and candidate share a process, in-process attacks apply (reading the "
                    "answer file, inspecting the caller's frame, patching pytest, forging the report at "
                    "exit). Run the candidate in a separate process or container and compare its outputs.",
                    path,
                    number,
                    ("V1", "V7"),
                )
                break


RULES: list[Rule] = [
    Rule(
        "SG001",
        "Tests, solutions or answers are copied into the agent image",
        ("V2",),
        Severity.HIGH,
        "COPY/ADD places test or answer material in the image the agent runs in.",
        "Keep tests and ground truth out of the agent image; mount them only into the verifier.",
        sg001_answers_copied,
    ),
    Rule(
        "SG002",
        "An answer-like file sits in the agent-visible directory",
        ("V2",),
        Severity.MEDIUM,
        "Files named expected*/golden*/answer* in the build context may be reachable by the agent.",
        "Move ground truth out of the build context.",
        sg002_answer_like_files,
    ),
    Rule(
        "SG003",
        "The agent runs as root",
        ("V8",),
        Severity.MEDIUM,
        "No non-root user for the agent.",
        "Add a USER instruction or set [agent] user.",
        sg003_root_agent,
    ),
    Rule(
        "SG004",
        "A credential is baked into the environment",
        ("V8",),
        Severity.HIGH,
        "Secrets in the Dockerfile or .env files are readable by the agent.",
        "Remove secrets; inject only at verification time into the verifier.",
        sg004_secrets,
    ),
    Rule(
        "SG005",
        "The reward is derived from a process exit code alone",
        ("V3", "V7"),
        Severity.MEDIUM,
        "Exit status can be forced to 0.",
        "Read a structured report; require the expected test count.",
        sg005_exit_code_reward,
    ),
    Rule(
        "SG006",
        "pytest configuration and conftest discovery are not pinned",
        ("V3", "V7"),
        Severity.HIGH,
        "pytest walks ancestors for config and conftest files.",
        "Use -c, --rootdir and --confcutdir pointing at trusted files.",
        sg006_pytest_config,
    ),
    Rule(
        "SG007",
        "pytest plugin autoloading is enabled",
        ("V3",),
        Severity.MEDIUM,
        "Entry-point plugins load automatically.",
        "Set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.",
        sg007_plugin_autoload,
    ),
    Rule(
        "SG008",
        "The interpreter starts in an agent-writable directory",
        ("V1", "V3"),
        Severity.MEDIUM,
        "python -m puts the current directory first on sys.path.",
        "Use python -I or cd elsewhere.",
        sg008_interpreter_cwd,
    ),
    Rule(
        "SG009",
        "World-writable permissions on verifier paths",
        ("V7",),
        Severity.MEDIUM,
        "chmod 777 on /logs, /tests or /solution.",
        "Keep verifier paths root-owned and read-only.",
        sg009_permissive_modes,
    ),
    Rule(
        "SG010",
        "A test report is trusted without checking the test count",
        ("V7",),
        Severity.MEDIUM,
        "A zero-failure report is accepted regardless of how many tests it covers.",
        "Require the exact expected count and no skips.",
        sg010_report_without_count,
    ),
    Rule(
        "SG011",
        "The environment grants privileged or host access",
        ("V8",),
        Severity.HIGH,
        "privileged, docker.sock, host networking or added capabilities.",
        "Remove them; they defeat container isolation.",
        sg011_host_access,
    ),
    Rule(
        "SG012",
        "The base image is floating or unpinned",
        ("V6",),
        Severity.MEDIUM,
        "latest tags or tags without digests.",
        "Pin with @sha256 digests.",
        sg012_floating_base,
    ),
    Rule(
        "SG013",
        "Packages are installed unpinned at verification time",
        ("V6",),
        Severity.MEDIUM,
        "Unpinned pip/npm installs in verifier scripts.",
        "Pin exact versions or bake into the image.",
        sg013_unpinned_packages,
    ),
    Rule(
        "SG014",
        "Remote code is piped into a shell",
        ("V3", "V7"),
        Severity.MEDIUM,
        "curl | sh at verification or build time.",
        "Use pinned packages or verified downloads.",
        sg014_remote_code,
    ),
    Rule(
        "SG015",
        "Assertions check substrings instead of exact values",
        ("V5",),
        Severity.MEDIUM,
        "assert 'x' in output style checks.",
        "Compare complete normalised values.",
        sg015_substring_assertions,
    ),
    Rule(
        "SG016",
        "A numeric tolerance is loose",
        ("V5", "V6"),
        Severity.MEDIUM,
        "approx/isclose tolerances of 1% or more, or absolute tolerance of 1.",
        "Justify and tighten every tolerance.",
        sg016_loose_tolerance,
    ),
    Rule(
        "SG017",
        "Tests only check existence or type",
        ("V6",),
        Severity.MEDIUM,
        "All assertions in a test are existence/type/non-empty checks.",
        "Assert on actual values.",
        sg017_weak_assertions,
    ),
    Rule(
        "SG018",
        "No effective verifier",
        ("V6",),
        Severity.HIGH,
        "No tests, or tests without assertions.",
        "Add tests that compare outcomes.",
        sg018_no_effective_tests,
    ),
    Rule(
        "SG019",
        ".git history is agent-visible",
        ("V2",),
        Severity.MEDIUM,
        "A .git directory in the build context exposes history.",
        "Exclude .git via .dockerignore.",
        sg019_git_history,
    ),
    Rule(
        "SG020",
        "An LLM judge is used or its prompt is built from agent output",
        ("V4",),
        Severity.MEDIUM,
        "LLM judges are injectable and non-deterministic.",
        "Prefer deterministic checks; quote and isolate input.",
        sg020_llm_judge,
    ),
    Rule(
        "SG021",
        "Program output decides the reward",
        ("V7",),
        Severity.MEDIUM,
        "grep on program output sets the reward.",
        "Use structured data from trusted code.",
        sg021_stdout_parsing,
    ),
    Rule(
        "SG022",
        "Ground truth may be non-deterministic",
        ("V6",),
        Severity.LOW,
        "Unseeded randomness or the clock feeds expected values.",
        "Seed and fix inputs.",
        sg022_nondeterministic_truth,
    ),
    Rule(
        "SG023",
        "Candidate code is imported into the test process",
        ("V1", "V7"),
        Severity.LOW,
        "Tests and candidate share a process.",
        "Compare outputs of a separate process.",
        sg023_shared_process,
    ),
    Rule(
        "SG024",
        "The agent and the verifier share one environment",
        ("V1",),
        Severity.MEDIUM,
        "Agent-phase changes persist into verification.",
        "Use a separate verifier environment.",
        sg024_shared_environment,
    ),
    Rule(
        "SG025",
        "The agent may have internet access",
        ("V8",),
        Severity.LOW,
        "Network is not disabled.",
        'Set network_mode = "none" unless required.',
        sg025_network,
    ),
    Rule(
        "SG026",
        "Very few graded cases",
        ("V6",),
        Severity.LOW,
        "Fewer than 20 cases.",
        "Add edge cases and invalid input.",
        sg026_few_cases,
    ),
]


def _generated(target: AuditTarget) -> Iterable[Finding]:
    """Rules whose findings come from running things (mutation, dynamic) rather than from text."""
    return ()


RULES.extend(
    [
        Rule(
            "SG027",
            "Weak verifier: low mutation score",
            ("V6",),
            Severity.MEDIUM,
            "Many plausible bugs in the reference solution still pass the tests.",
            "Add cases that distinguish the surviving mutants.",
            _generated,
        ),
        Rule(
            "SG028",
            "An exploit from the corpus succeeds",
            ("V1", "V2", "V3", "V6", "V7", "V8"),
            Severity.HIGH,
            "A payload that does not solve the task obtained a passing verdict.",
            "Move to a stricter tier or remove the weakness the attack targets.",
            _generated,
        ),
    ]
)

RULES_BY_ID = {r.id: r for r in RULES}
