# Threat model

This document says what SealGrade protects, against whom, and where its guarantees stop.
It is written first on purpose: a security tool that is vague about its limits is not trustworthy.

## What is being protected

The **integrity of a verdict**: a pass, fail or score that says a submission solved a task must
mean that it did. A second asset follows from the first: the **secrecy of ground truth** (expected
outputs, hidden tests), because leaking it lets a submission copy answers instead of solving.

## Who is the adversary

The **submission**. That means code, files and shell commands produced by an AI agent or a person,
assumed to be hostile and clever. It is not assumed to be malicious in intent (reward hacking
often emerges without anyone asking for it) but it is assumed capable of anything its privileges
allow.

The adversary can:

- write arbitrary files anywhere its user can write, including its own working directory,
- start, detach and leave behind processes,
- read anything readable by its user, including environment variables and `/proc`,
- print any text, including text that looks like a test report,
- run until the configured limits stop it.

The adversary cannot (by assumption, see "Out of scope"):

- escape the container runtime or attack the host kernel,
- tamper with the host-side controller process or its secrets.

## Trust boundaries

```
 untrusted                                  trusted
 ---------                                  -------
 agent phase (container A)                  controller (host process)
 candidate execution (container B)          judge (container C): tests + ground truth
 everything the submission produced         per-run secrets (HMAC key, canaries)
```

Rules that follow from the boundaries (the strict tier implements all of them; weaker tiers
deliberately break some, and the proof matrix measures what that costs):

1. Nothing that scores lives in, or is reachable from, anything that is being scored.
2. The grader never executes candidate code in its own process, container or filesystem.
3. Data crossing a boundary is validated before it is interpreted (archive entries, JSON schemas,
   reward values), and only declared artifacts may cross.
4. The verdict is produced by trusted code from structured data, never read from output the
   submission could print or from a file it could write.
5. A container is destroyed after its phase, so no process outlives the phase that started it.

## Flaw classes covered

The classes come from published research and are described in [TAXONOMY.md](TAXONOMY.md):
isolation failures, answers reachable from the sandbox, execution of agent-controlled data in the
evaluator, judge prompt injection, weak string matching, evaluation-logic gaps, trusting output the
agent can influence, and excessive permissions.

## Out of scope (stated plainly)

- **Container and kernel escapes.** Docker containers share the host kernel and are not a
  hardware security boundary. SealGrade lowers the *surface* (non-root, dropped capabilities,
  read-only filesystems, no network, resource limits, seccomp). Optional stronger runtimes
  (gVisor, Kata, Firecracker) are supported as extra layers where the platform provides them, and the
  documentation says which tier was used for any published result.
- **Hardware side channels**, timing channels between co-located workloads, and covert channels.
- **A compromised controller host**, a malicious task author, or a malicious dependency of
  SealGrade itself.
- **Task-level correctness bugs that are not exploits**, for example a test that is simply wrong.
  The auditor's mutation score helps find weak tests, but SealGrade does not prove tests correct.
- **Denial of service against the host** beyond the configured per-run limits.

## What a published result means

When the proof matrix says an attack is "blocked" on a tier, it means: in this repository, against
these sample tasks, on this container runtime, that specific payload did not obtain a passing verdict.
It is a regression test for known exploit classes, not a proof of unhackability.
