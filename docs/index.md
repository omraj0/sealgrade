# SealGrade

**A tamper-resistant evaluation runner, an exploit corpus and an auditor for untrusted, AI-generated code.**

Evaluation harnesses for AI agents usually trust the thing they are measuring. A submission that can write a
`conftest.py`, shadow a module, edit the tests, read the answer key or leave a process behind can score full
marks without solving anything. Public research has shown this on well-known benchmarks
([BenchJack, arXiv 2605.12673](https://arxiv.org/abs/2605.12673)).

SealGrade is a deterministic answer:

- **A runner** with four harness tiers, from naive to strict, so the same attacks can be replayed against each.
- **An exploit corpus** of 30 labelled attacks. Each is a submission that does *not* solve the task, so a
  passing verdict means the exploit worked.
- **A proof matrix** that CI regenerates, so a defence regression fails the build.
- **An auditor** (`sealgrade audit`) that scans task directories for the same flaw classes: 26 static rules,
  optional mutation scoring of the verifier, SARIF output for GitHub code scanning, and an adapter for
  Harbor / Terminal-Bench style tasks.

## Where to start

| If you want to... | Read |
|---|---|
| See what it proves | [Proof matrix](results/matrix.md) |
| Understand the guarantees and their limits | [Threat model](THREAT_MODEL.md) |
| Harden your own evaluation | [How to write an unhackable eval](HOWTO-unhackable-evals.md) |
| Audit a task directory | [Auditor rules](AUDIT_RULES.md) |
| Add an attack | [Exploit corpus](CORPUS.md) and the contributing guide |
| See why it is built this way | [ADR 0001](adr/0001-three-container-grading.md) |

## The four tiers

| Tier | How it grades | What it is for |
|---|---|---|
| T0 naive | one container; tests inside; reward from the exit code | the baseline every attack must beat |
| T1 typical | separate verifier container, same image, root, shared volumes, junit check | a common "better" setup that is still weak |
| T2 compat | isolated agent phase, artifact firewall, hardened pytest in a non-root, offline, read-only container | tasks whose tests must import the candidate |
| T3 strict | three containers; the judge compares data and never runs candidate code; signed verdicts | the recommended design |

T0 and T1 are our own re-creations of common patterns. They are not claims about any named benchmark or product.
