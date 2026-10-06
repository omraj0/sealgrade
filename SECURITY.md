# Security policy

## What this project is

SealGrade is a defensive tool. It includes **exploit payloads for evaluation harnesses** as test
fixtures, run only against SealGrade's own harness tiers inside containers.

## Please report privately

If you find a way for a submission to obtain a passing verdict on a tier that is documented as
**blocked** (a bypass), or a flaw in the artifact firewall, signed verdicts or container policy:

1. Use GitHub's **private vulnerability reporting** on this repository
   (Security tab, "Report a vulnerability").
2. Include the tier, the payload, and the expected versus observed result.

Please do not open a public issue for a working bypass until it has been fixed.

## Scope

In scope: the runner, the artifact firewall, verdict signing, the container policies, the auditor.

Out of scope: kernel or container-runtime escapes, hardware side channels and compromised hosts
(see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)), and findings about third-party benchmarks.

## Responsible use

Do not run the corpus against systems you do not own or lack permission to test. If you use the
auditor on someone else's benchmark, tell the maintainers before publishing findings.
