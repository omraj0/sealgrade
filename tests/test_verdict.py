from __future__ import annotations

import pytest

from sealgrade.runner import verdict


def record() -> dict[str, object]:
    return {
        "task": "t",
        "tier": "t3",
        "reward": 1.0,
        "artifacts_sha256": {"solution.py": "ab" * 32},
    }


def test_sign_and_verify_round_trip() -> None:
    key = b"k" * 32
    assert verdict.verify(record(), verdict.sign(record(), key), key)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(reward=0.0),
        lambda r: r.update(task="other"),
        lambda r: r["artifacts_sha256"].update({"solution.py": "00" * 32}),  # type: ignore[union-attr]
        lambda r: r.update(extra="field"),
    ],
)
def test_any_change_invalidates_the_signature(mutation: object) -> None:
    key = b"k" * 32
    original = record()
    signature = verdict.sign(original, key)
    tampered = record()
    mutation(tampered)  # type: ignore[operator]
    assert not verdict.verify(tampered, signature, key)


def test_a_different_key_does_not_verify() -> None:
    signature = verdict.sign(record(), b"a" * 32)
    assert not verdict.verify(record(), signature, b"b" * 32)


def test_signature_does_not_depend_on_key_order() -> None:
    key = b"k" * 32
    first = {"a": 1, "b": 2}
    second = {"b": 2, "a": 1}
    assert verdict.sign(first, key) == verdict.sign(second, key)


def test_non_finite_numbers_cannot_be_signed() -> None:
    with pytest.raises(ValueError):
        verdict.sign({"reward": float("nan")}, b"k" * 32)


def test_key_comes_from_the_environment_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(verdict.KEY_ENV, "ab" * 16)
    assert verdict.load_key() == bytes.fromhex("ab" * 16)


@pytest.mark.parametrize("bad", ["zz", "abcd"])
def test_a_bad_key_is_rejected(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv(verdict.KEY_ENV, bad)
    with pytest.raises(ValueError):
        verdict.load_key()


def test_without_configuration_each_process_gets_a_fresh_random_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(verdict.KEY_ENV, raising=False)
    first, second = verdict.load_key(), verdict.load_key()
    assert len(first) == 32 and first != second
