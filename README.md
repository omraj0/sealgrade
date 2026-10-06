# SealGrade

[![CI](https://github.com/omraj0/sealgrade/actions/workflows/ci.yml/badge.svg)](https://github.com/omraj0/sealgrade/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)

**A tamper-resistant evaluation runner, an exploit corpus and an auditor for untrusted, AI-generated code.**

Evaluation harnesses for AI agents usually trust the thing they are measuring. A submission that can write a
`conftest.py`, shadow a module, edit the tests, read the answer key or leave a process behind can score full
marks without solving anything. Public research has shown this on well-known benchmarks
([BenchJack, arXiv 2605.12673](https://arxiv.org/abs/2605.12673)). BenchJack is an LLM-driven *auditor*;
SealGrade is the deterministic *fix* plus a regression suite that proves it.

## What it proves

30 attacks, 13 sample tasks, four harness tiers. Every attack is a submission that does **not** solve the task,
so a passing verdict means the exploit worked. Every claim below was measured, and CI fails if a claim and a
measurement disagree.

| | T0 naive | T1 typical | T2 compat | T3 strict |
|---|---|---|---|---|
| **Exploits that worked** (of 21) | **21** | **10** | **5** | **0** |
| Boundary probes that got through (of 9) | 0 | 0 | 0 | 0 |
| Controls passed (oracle passes, do-nothing and near-miss fail) | 39 / 39 | 39 / 39 | 39 / 39 | 39 / 39 |
| Median seconds to grade one submission | 2.0 | 3.2 | 3.1 | 3.4 |

- The **five** attacks that still work on T2 are the *in-process* ones (reading the answer file at call time,
  inspecting the caller's stack frame, patching pytest, forging the report from an exit handler, returning an
  object that equals everything). They need the candidate to share a process with the tests. T3 never does that,
  and blocks all five. That is the whole argument for the strict tier, measured.
- The strict tier costs about **1.4 s more per grade** than the naive one (three throw-away containers instead of
  one). See [latency](docs/results/latency.md).
- Full per-attack table: [docs/results/matrix.md](docs/results/matrix.md).

![Proof matrix: attacks by harness tier](docs/results/matrix.svg)

T0 and T1 are our own re-creations of common patterns. They are not claims about any named benchmark or product.

## How the strict tier works

```
agent container ──▶ artifact firewall ──▶ candidate container ──▶ judge container ──▶ controller
 (no tests, no key)   (host: one regular     (artifacts + inputs     (ground truth;      (validates the
  non-root, no net,    file, size-bounded,     only; returns            compares DATA;     report, computes
  read-only fs)        no links/devices)       outputs as bytes)        never runs         the reward,
                                                                        candidate code)    signs a record)
```

- Each phase runs in a fresh container with all capabilities dropped, `no-new-privileges`, a read-only root
  filesystem, no network, and memory/pid limits. The container's **effective** configuration is read back with
  `docker inspect` and compared with the policy before it starts.
- Only declared artifacts cross to the host, through a firewall that is fuzzed with Hypothesis.
- The judge compares **JSON data with type-strict equality** (`True` is not `1`, `1` is not `1.0`; NaN and
  oversized or deeply nested output are rejected).
- The controller computes the reward from the validated report and **signs the record** (HMAC) with a key that
  never enters a container.

Design notes: [threat model](docs/THREAT_MODEL.md), [ADR 0001](docs/adr/0001-three-container-grading.md),
[ADR 0002](docs/adr/0002-compat-tier-and-residual-risk.md).

## The auditor

```bash
sealgrade audit path/to/task-or-dataset                  # table
sealgrade audit path/to/tasks --format sarif --out r.sarif   # GitHub code scanning
sealgrade audit tasks/py-roman --mutation                # + mutation score of the verifier
sealgrade audit tasks/py-roman --dynamic t0,t1           # + run the exploit corpus against it
```

- **26 static rules** mapped to the published flaw classes, each pointing at a file and line
  ([reference](docs/AUDIT_RULES.md)): answers copied into the agent image, exit-code rewards, unpinned pytest
  configuration, substring and loose-tolerance assertions, weak existence checks, LLM-judge prompts built from
  agent output, privileged containers, unpinned images, and more.
- **Mutation scoring**: plant one plausible bug at a time in the reference solution and count how many the tests
  catch. On the 13 sample tasks, 229 of 232 valid mutants were killed (98.7%); the 3 survivors are listed with diffs in
  the [results](docs/results/mutation.md), each is either an equivalent program or a missing case.
- **Harbor / Terminal-Bench adapter**: reads `task.toml`, `environment/Dockerfile`, `tests/test.sh` (and the
  multi-step `steps/*/tests/` layout) from [Harbor](https://github.com/harbor-framework/harbor) tasks.
- **Measured, not claimed**: a clean hardened task produces **0** findings and each of the 25 planted flaws is
  detected (62 tests). The fixtures were written together with the rules, so that measures self-consistency;
  running the auditor over Harbor's 32 public example tasks (a sanity check for false alarms, not a
  criticism of teaching examples) exposed three false-positive patterns, which are fixed and covered by tests.

Use it in CI:

```yaml
- uses: omraj0/sealgrade@main
  with:
    path: tasks
    fail-on: high
```

## Try it

Requires Python 3.11+ and Docker.

```bash
git clone https://github.com/omraj0/sealgrade && cd sealgrade
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

sealgrade tasks                                    # the 13 sample tasks
sealgrade attacks                                  # the 30-attack corpus
sealgrade controls --tiers t0,t1,t2,t3 -j 2        # honest work passes, bad work fails, everywhere
sealgrade matrix --tiers t0,t1,t2,t3 -j 2 --tasks py-slugify   # the proof matrix
sealgrade attack py-slugify conftest-force-pass --tier t0      # one attack, one tier
```

## Adding your own

An attack is a folder under `corpus/` with an `attack.toml` and a payload; a task is a folder under `tasks/` with
an oracle, a near-miss and generated cases. See [CONTRIBUTING.md](CONTRIBUTING.md). To harden a real evaluation,
start with [How to write an unhackable eval](docs/HOWTO-unhackable-evals.md).

## Honest limits

- **Docker is not a hardware security boundary.** Containers share the host kernel. SealGrade reduces the
  attack surface and verifies the policy it asked for, but kernel and container-runtime escapes are out of
  scope. See the [threat model](docs/THREAT_MODEL.md).
- "Blocked" means: in this repository, against these tasks, on this runtime, that payload did not obtain a
  passing verdict. It is a regression suite for known exploit classes, not a proof of unhackability.
- Tasks are Python functions graded by comparing JSON-serialisable outputs. Richer task types (CLI programs,
  multi-file projects) are future work.
- The auditor's rules are heuristics; they can be wrong in both directions.
- Version 1 deliberately does not audit third-party benchmarks. If you audit someone else's, tell the maintainers
  before you publish.

## Credits

The flaw taxonomy comes from **BenchJack** ([arXiv 2605.12673](https://arxiv.org/abs/2605.12673)) and the
Berkeley RDI write-up ["We Scored 100% on AI Benchmarks Without Solving a Single Problem"](https://rdi.berkeley.edu/blog/trustworthy-benchmarks/).
Harbor and Terminal-Bench are projects of their own maintainers; SealGrade reads their public task formats and
is not affiliated with them. See [docs/TAXONOMY.md](docs/TAXONOMY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
