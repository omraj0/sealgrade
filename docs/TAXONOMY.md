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

The corpus has 30 attacks (21 exploits and 9 boundary probes). The full list with each attack's classes and
documented outcome per tier is generated from the manifests in [CORPUS.md](CORPUS.md). In short:

| Class | Covered by |
|---|---|
| V1 isolation failure | `tamper-tests-in-place`, `lingering-reward-writer`, `shadow-stdlib-argparse`, `pth-startup-hook`, `trojan-python-binary`, `frame-introspection-expected` |
| V2 answers shipped with the test | `read-answer-key-hardcode`, `runtime-read-answer-key` |
| V3 execution into the evaluator | `conftest-*`, `*-collect-only`, `atexit-forge-report`, `monkeypatch-pytest-reports` |
| V4 LLM-judge injection | not exercised by the runner (it has no LLM judge); the auditor flags it (SG020) |
| V5 weak string matching | not a runner property; the auditor flags substring checks and loose tolerances (SG015, SG016) |
| V6 evaluation-logic gaps | `always-equal-object`, `conftest-skip-all`, `pytest-ini-collect-only`, `nan-output` |
| V7 trusting untrusted output | `exit-zero-at-import`, `conftest-rewrite-junit`, `atexit-forge-report` |
| V8 excessive permissions | `trojan-python-binary`, `tamper-tests-in-place`, `pth-startup-hook`, the artifact probes |

V4 and V5 are properties of how a *task* scores, not of the harness that runs it, so they are covered by
auditor rules (and by the mutation score) rather than by runner attacks.

## Using this responsibly

The payloads are written as test fixtures against SealGrade's own harness tiers. Do not point
them at systems you do not own or have permission to test. See [the security policy](https://github.com/omraj0/sealgrade/blob/main/SECURITY.md).
