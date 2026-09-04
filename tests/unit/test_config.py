"""
Phase 1 exit criterion: "Config hashing works."

These tests prove: (1) the shipped default.yaml loads cleanly, (2) hashing
is deterministic -- same content, same hash, regardless of key order or
formatting -- and (3) any real content change produces a different hash, so
config_hash is trustworthy as an audit fingerprint (spec section 16).
"""

from __future__ import annotations

import textwrap

import pytest

from src.utils.config import (
    ConfigError,
    compute_config_hash,
    load_config,
)


def test_default_config_loads() -> None:
    cfg = load_config()
    assert cfg.data["mode"] == "PAPER"
    assert cfg.get("risk.max_risk_per_trade_pct") == 1.0
    assert cfg.get("nonexistent.key", "fallback") == "fallback"


def test_default_config_is_paper_mode_only() -> None:
    # Spec section 21: the system must never default to LIVE.
    cfg = load_config()
    assert cfg.data["mode"] == "PAPER"


def test_hash_is_deterministic_regardless_of_key_order() -> None:
    a = {"risk": {"max_daily_loss_pct": 3.0}, "mode": "PAPER"}
    b = {"mode": "PAPER", "risk": {"max_daily_loss_pct": 3.0}}
    assert compute_config_hash(a) == compute_config_hash(b)


def test_hash_changes_when_content_changes() -> None:
    a = {"mode": "PAPER", "risk": {"max_daily_loss_pct": 3.0}}
    b = {"mode": "PAPER", "risk": {"max_daily_loss_pct": 4.0}}
    assert compute_config_hash(a) != compute_config_hash(b)


def test_hash_has_expected_format() -> None:
    cfg = load_config()
    assert cfg.config_hash.startswith("sha256:")
    assert len(cfg.config_hash) == len("sha256:") + 64


def test_missing_config_file_raises(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_non_mapping_config_raises(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(textwrap.dedent("- just\n- a\n- list\n"), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)


def test_reloading_same_file_gives_same_hash() -> None:
    first = load_config()
    second = load_config()
    assert first.config_hash == second.config_hash
