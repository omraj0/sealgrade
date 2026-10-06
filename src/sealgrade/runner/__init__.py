"""Harness tiers: grading strategies that differ in how much they trust the submission."""

from __future__ import annotations

from sealgrade.runner.models import Harness, Submission, Verdict
from sealgrade.runner.tier_t0 import T0Naive
from sealgrade.runner.tier_t1 import T1Typical
from sealgrade.runner.tier_t2 import T2Compat
from sealgrade.runner.tier_t3 import T3Strict

TIERS: dict[str, type[Harness]] = {
    "t0": T0Naive,
    "t1": T1Typical,
    "t2": T2Compat,
    "t3": T3Strict,
}

TIER_LABELS = {
    "t0": "T0 naive",
    "t1": "T1 typical",
    "t2": "T2 compat",
    "t3": "T3 strict",
}


def get_harness(tier: str) -> Harness:
    try:
        return TIERS[tier]()
    except KeyError:
        known = ", ".join(sorted(TIERS))
        raise ValueError(f"unknown tier {tier!r} (available: {known})") from None


__all__ = ["TIERS", "TIER_LABELS", "Harness", "Submission", "Verdict", "get_harness"]
