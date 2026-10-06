# How to write an evaluation that cannot be gamed

A practical checklist, in the order the work actually goes. Each item names the flaw class it
closes ([taxonomy](TAXONOMY.md)) and the SealGrade rule or attack that checks it. None of this makes a
grader unhackable; it removes the cheap ways in and gives you tests that tell you when one reopens.

## 1. Separate what scores from what is scored (V1)

- Run the submission and the grader in **different containers**. A grader that shares a filesystem or
  process with the submission can be edited, shadowed or outlived (`tamper-tests-in-place`,
  `shadow-stdlib-argparse`, `pth-startup-hook`, `lingering-reward-writer`).
- Give the grader only what it needs: the **declared artifacts**, copied out through a check that
  accepts one regular file of bounded size and refuses links, devices, odd names and oversize data.
- Destroy the submission's container before grading. A container that exits takes every process in it
  with it, so nothing outlives its phase.
- Audit: `SG024`, `SG008`, `SG003`.

## 2. Keep the answers out of reach (V2)

- Never put tests, solutions or expected outputs in the image the agent runs in, and never rely on
  `.dockerignore` to be right by accident (`read-answer-key-hardcode`, `runtime-read-answer-key`).
- Check the **built image**, not the repository layout: search its filesystem for your answer files.
- Remember `.git`: history can contain the fix. Audit: `SG001`, `SG002`, `SG019`.

## 3. Do not run candidate code inside the grader (V3, V7)

- The strongest design compares **data**, not live objects. Run the candidate in its own container on
  inputs you provide, serialise its outputs to JSON, and compare them in a third process that never imports
  the candidate (`frame-introspection-expected`, `always-equal-object`, `monkeypatch-pytest-reports` all
  fail against this).
- If tests must import the candidate (pytest style), accept the residual risk knowingly: pin pytest's
  configuration (`-c`, `--rootdir`, `--confcutdir`), run the interpreter isolated (`python -I`), turn plugin
  autoload off (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`), and keep the candidate on the import path through a
  trusted conftest only. Then measure what is left (the T2 column of the proof matrix).
- Audit: `SG006`, `SG007`, `SG023`.

## 4. Decide the verdict from trusted data (V7)

- Never derive the reward from a **process exit code** or from text the submission can print. Exit status can
  be forced to 0 (`conftest-exitstatus-zero`, `exit-zero-at-import`); stdout can say anything.
- Read a structured report and require it to account for **exactly the expected number of tests** with none
  failed, errored or skipped (`conftest-skip-all`, `conftest-rewrite-junit`, `atexit-forge-report`).
- Parse hostile reports defensively: refuse DOCTYPE and entity declarations, bound the size, check that the
  totals agree with the elements they summarise.
- Sign the verdict record with a key that never enters a container, so a stored result is tamper-evident.
- Audit: `SG005`, `SG010`, `SG021`.

## 5. Restrict the sandbox (V8)

Non-root user, all capabilities dropped, `no-new-privileges`, read-only root filesystem, no network, memory
and process limits, no host mounts, no `docker.sock`. Then **read the effective configuration back** with
`docker inspect` and refuse to start if it is weaker than you asked for. Audit: `SG003`, `SG004`, `SG009`,
`SG011`, `SG025`.

## 6. Test the tests (V5, V6)

- Ship three controls and run them on every change: the **reference solution passes**, a **do-nothing
  submission fails**, and a **plausible-but-wrong near-miss fails**. Hardening that breaks honest solutions is
  worthless.
- Compute a **mutation score**: introduce one plausible bug at a time into the reference solution and
  count how many the tests catch (`sealgrade audit --mutation`). Survivors are either equivalent programs or
  gaps; read them.
- Prefer exact, normalised comparisons. Substring checks and loose numeric tolerances accept wrong answers
  (`SG015`, `SG016`), and existence checks accept stubs (`SG017`).
- Make types part of equality: `True` is not `1` and `1` is not `1.0`.

## 7. Make it reproducible

Pin base images by digest, pin packages exactly at build time, seed every generator, fix timestamps, and make
data generation byte-identical. Audit: `SG012`, `SG013`, `SG014`, `SG022`.

## 8. If you must use an LLM judge (V4)

Treat the agent's text as untrusted input to the judge: delimit it with a random token, ask for structured
output, keep the rubric out of band, and prefer deterministic checks wherever the task allows. Audit: `SG020`.

## 9. Keep the attacks as regression tests

Every exploit you find (or read about) becomes a payload in `corpus/`, with a documented expectation per
tier. CI runs the matrix, so a defence that regresses fails the build.

## 10. Disclose responsibly

If you audit someone else's benchmark, tell the maintainers before you publish, and do not publish findings
before they respond.
