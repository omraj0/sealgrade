# Attack taxonomy and credits

SealGrade does not invent a new classification. It uses the one published with **BenchJack**
and cross-references the patterns from the Berkeley RDI write-up, then turns each class into
runnable, regression-tested attacks.

## Sources

- **BenchJack**: "Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent
  Benchmarks with BenchJack", [arXiv 2605.12673](https://arxiv.org/abs/2605.12673). It defines the
  eight flaw classes V1 to V8 below and audits ten agent benchmarks with an LLM-driven pipeline.
- **Berkeley RDI**: "We Scored 100% on AI Benchmarks Without Solving a Single Problem",
  <https://rdi.berkeley.edu/blog/trustworthy-benchmarks/>. It describes seven recurring patterns,
  quoted here by short name.

Our contribution is different in kind: a **deterministic** runner, a **corpus** of concrete exploit
payloads, and a **regression matrix** that fails CI when a defence stops working. We complement
BenchJack's auditor; we do not replace it.

## The eight classes (paraphrased)

| Class | Meaning |
|---|---|
| V1 | **Isolation failure.** The submission and the evaluator share an environment or a process. |
| V2 | **Answers shipped with the test.** The reference solution or expected outputs are reachable from where the submission runs. |
| V3 | **Remote code execution into the evaluator.** The evaluator parses or executes data the submission controls. |
| V4 | **LLM-judge prompt injection.** Output aimed at an LLM judge steers its score. |
| V5 | **Weak string matching.** Scorers that pattern-match can be satisfied by keyword stuffing. |
| V6 | **Evaluation-logic gaps.** A scorer can be satisfied by an easier property than the intended one. |
| V7 | **Trusting untrusted output.** Signals such as test output or reports can be influenced by the submission. |
| V8 | **Excessive permissions.** Root, writable host paths, or unrestricted network inside the sandbox. |

## The seven Berkeley patterns (short names)

1. Isolate everything that scores from everything being scored.
2. Never trust output from the code you are evaluating.
3. Test the tests, not just the submissions.
4. Make tolerances and baselines honest.
5. Treat evaluation code as production code.
6. Answer leakage.
7. Monkey-patching and stack introspection.

## How the corpus maps to them

Attack ids are folder names under `corpus/`. This table grows with the corpus.

| Attack | Classes | What it does |
|---|---|---|
| `conftest-force-pass` | V3, V7 | `conftest.py` hook rewrites every test outcome to passed |
| `shadow-pytest-forge-report` | V1, V3, V7 | a fake `pytest` package forges a passing report |
| `pytest-ini-collect-only` | V3, V6, V7 | `pytest.ini` switches to `--collect-only`, which exits 0 |
| `exit-zero-at-import` | V3, V7 | the solution prints a success line and exits 0 on import |
| `read-answer-key-hardcode` | V2 | reads the answer key in the sandbox and builds a lookup table |
| `tamper-tests-in-place` | V1, V8 | overwrites the test file in a shared container |
| `lingering-reward-writer` | V1, V7 | a detached process keeps rewriting the reward file |
| `trojan-python-binary` | V1, V7, V8 | replaces `python` on `PATH` with a script that exits 0 |

## Using this responsibly

The payloads are written as test fixtures against SealGrade's own harness tiers. Do not point
them at systems you do not own or have permission to test. See [SECURITY.md](../SECURITY.md).
