# SealGrade

**A tamper-resistant evaluation runner and exploit corpus for untrusted, AI-generated code.**

> Status: early development (P0 and P1 done). The hardened runner is the next phase; see the roadmap below.

Evaluation harnesses for AI agents usually trust the thing they are measuring. A submission that can
write a `conftest.py`, shadow a module, edit the tests, read the answer key or leave a process behind
can score full marks without solving anything. Public research has shown this on well-known
benchmarks ([BenchJack, arXiv 2605.12673](https://arxiv.org/abs/2605.12673)).

SealGrade is a deterministic answer to that problem:

1. **An exploit corpus**: small, labelled attacks, each a submission that does *not* solve the task.
   If the verdict says "pass", the exploit worked.
2. **Harness tiers** from naive to strict, so the same attacks can be replayed against each.
3. **A proof matrix** (attacks x tiers) that CI regenerates, so a defence regression fails the build.
4. **A hardened runner** and an **auditor** that scan evaluation tasks for the same flaw classes
   (both planned, see below).

## What the proof matrix shows today

Eight attacks, three sample tasks, two deliberately weak harness tiers. Each attack is a submission
that does **not** solve the task, so a passing verdict means the exploit worked.

| Attack | Classes | T0 naive | T1 typical |
|---|---|---|---|
| `conftest-force-pass` | V3, V7 | EXPLOIT | EXPLOIT |
| `exit-zero-at-import` | V3, V7 | EXPLOIT | blocked |
| `lingering-reward-writer` | V1, V7 | EXPLOIT | blocked |
| `pytest-ini-collect-only` | V3, V6, V7 | EXPLOIT | blocked |
| `read-answer-key-hardcode` | V2 | EXPLOIT | EXPLOIT |
| `shadow-pytest-forge-report` | V1, V3, V7 | EXPLOIT | EXPLOIT |
| `tamper-tests-in-place` | V1, V8 | EXPLOIT | blocked |
| `trojan-python-binary` | V1, V7, V8 | EXPLOIT | blocked |
| **Exploits that worked** | | **8 / 8** | **3 / 8** |

Controls hold on both tiers (the reference solution passes; a do-nothing submission and a
plausible-but-wrong one fail): 18 / 18. The hardened tiers (T2 compat, T3 strict) are the next phases;
this table is the "before" picture they have to beat. A copy of the latest run lives in
[docs/results](docs/results/matrix.md).

T0 and T1 are our own re-creations of common patterns. They are not claims about any named
benchmark or product.

## Try it

Requires Docker and Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

sealgrade tasks                 # the sample tasks
sealgrade attacks               # the exploit corpus
sealgrade controls              # honest solutions pass, bad ones fail, on every tier
sealgrade matrix --tiers t0,t1  # run every attack against the naive tiers
```

## Roadmap

| Phase | What | State |
|---|---|---|
| P0 | Repo, spec, threat model, ADRs, CI skeleton | done |
| P1 | Naive tiers (T0, T1), first 8 attacks, 3 sample tasks | done |
| P2 | Hardened strict-mode runner (three containers, artifact firewall, signed verdicts) | planned |
| P3 | Corpus to 30-40 attacks, compat tier (T2), matrix in CI, 12-15 tasks | planned |
| P4 | Auditor: static rules, dynamic smoke test, mutation score, Harbor adapter | planned |
| P5 | HTML reports, GitHub Action, docs site, first release | planned |

## Docs

- [Threat model](docs/THREAT_MODEL.md)
- [Attack taxonomy and credits](docs/TAXONOMY.md)
- [ADR 0001: three-container grading](docs/adr/0001-three-container-grading.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
