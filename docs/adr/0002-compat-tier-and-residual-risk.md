# ADR 0002: Offer a compat tier and publish what it leaves open

- Status: accepted
- Date: 2026-10-06

## Context

[ADR 0001](0001-three-container-grading.md) removes in-process attacks by never importing the candidate
into the grader. That requires tasks to be expressible as "run this callable on these inputs and compare the
outputs". Many real evaluations are not: their tests are ordinary pytest suites that import the code under test.
Telling those users "rewrite your tests" is not an answer, and pretending a hardened pytest run is as strong as
strict mode would be dishonest.

## Decision

Ship a second hardened tier, **T2 (compat)**, for tests that must import the candidate:

- the agent phase and artifact firewall are identical to the strict tier (so every attack that depends on
  files the agent leaves behind stops at the boundary),
- verification runs in a fresh non-root, read-only, offline container with `python -I`, an explicit pytest
  configuration (`-c`, `--rootdir`), plugin autoload off, and the candidate placed on the import path only by a
  trusted conftest,
- the reward comes from a strictly parsed JUnit report that must account for exactly the expected number of
  tests with no failure, error or skip.

Do **not** claim more than that. The candidate and the ground truth share one process and one filesystem, so five
in-process attacks (`runtime-read-answer-key`, `frame-introspection-expected`, `atexit-forge-report`,
`always-equal-object`, `monkeypatch-pytest-reports`) still succeed. Each is in the corpus with `t2 = "exploit"`,
and the proof matrix shows them next to the strict tier, where all five are blocked.

## Consequences

- The matrix gives users an honest, measured answer to "what do I lose by keeping pytest?".
- A future change that accidentally fixes one of the five on T2 fails CI as a mismatch, which forces the
  documentation to be updated instead of silently drifting.
- Anyone who needs protection from in-process attacks has a clear next step: strict mode.

## Alternatives considered

- **A subprocess RPC bridge inside T2** (the candidate runs as another user and tests call it over a pipe).
  Closes some in-process attacks but adds a protocol and a second trust boundary to get wrong, and it is
  strict mode in everything but name. Rejected for now.
- **Only offering strict mode.** Cleanest guarantee, but unusable for the many tasks that are pytest suites.
