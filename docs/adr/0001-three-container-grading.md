# ADR 0001: Grade in three containers and compare data, not code

- Status: accepted
- Date: 2026-10-06

## Context

Most evaluation harnesses run the submission and the tests in the same place: one container, one
filesystem, often one Python process. The research cited in [TAXONOMY.md](../TAXONOMY.md) shows that
this lets a submission rewrite test outcomes, shadow modules, edit tests, read the answer key or
forge the reward. Fixing each trick one at a time is a losing game; the cause is that the thing being
scored can touch the thing doing the scoring.

## Decision

The **strict tier** uses three containers and a trusted host controller:

1. **Agent container**: contains the task inputs only. No tests, no ground truth, no secrets.
   Non-root, capabilities dropped, read-only root filesystem, no network, resource limits.
2. **Candidate-execution container**: a fresh container that receives only the declared artifacts
   (read-only) and judge-provided inputs. It runs the candidate and returns **outputs as bytes**.
   It never holds expected values. The container is destroyed afterwards, so nothing outlives it.
3. **Judge container**: holds the tests and ground truth. It **compares data** returned by the
   candidate and **never executes candidate code**. It emits a structured verdict.

The controller validates artifacts crossing boundaries (an archive firewall that rejects links,
devices, traversal and oversize entries), validates the judge's verdict against a schema, and signs
it with a key that never enters any container.

A **compat tier** exists for tasks whose tests must import the candidate (pytest style). It applies
a hardened invocation but the candidate still shares a process with the tests. The proof matrix
shows exactly which attacks that leaves open, so the trade-off is visible instead of hidden.

## Consequences

- In-process attacks (monkey-patching, stack introspection, `sys.modules` tricks) are impossible in
  strict mode by construction, not by detection.
- Tasks must be expressible as "run this callable or command on these inputs, compare outputs".
  That covers function, CLI and data-transformation tasks; it does not cover tasks that need to run
  arbitrary test code inside the candidate's process. Those use compat mode and are documented as such.
- Grading costs more (three container starts instead of one). We measure and publish the overhead.
- The design adds moving parts; each one gets its own tests, and the proof matrix guards the whole.

## Alternatives considered

- **One hardened container.** Cheaper, but any bug in hardening exposes both candidate and judge.
- **A language-level sandbox (restricted interpreters).** Historically escapable and
  language-specific; rejected as a primary boundary.
- **MicroVMs per phase.** Strongest isolation, but needs KVM and is not available on common
  developer machines. Supported later as an optional runtime, not a requirement.
- **An LLM judge.** Subject to prompt injection (V4) and non-deterministic; rejected as the
  default. Deterministic comparison is the baseline.
