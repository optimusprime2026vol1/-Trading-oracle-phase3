"""
Config loading and hashing.

Master spec reference: TRADING_ORACLE_v2_MASTER_SPEC.md, sections 1 (Tier 2/4),
13 (output schema field "config_hash"), 16 (audit & reproducibility), 19
(repository structure: "config/ versioned, hashed").

Every emitted signal carries the hash of the exact config that produced it,
so a decision made months ago can be reconstructed byte-for-byte. That only
works if hashing is deterministic: same config content -> same hash, always,
independent of key order, whitespace, or the machine that computed it.

Environment variables (loaded from `.env` locally, GitHub Secrets in CI) may
override config values but are never mixed into the hashed config object --
secrets must never end up inside a hash that gets logged or displayed. The
hash covers structural/behavioural config only (risk limits, thresholds,
timeframe defaults, etc.), not credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


class ConfigError(Exception):
    """Raised when config is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class LoadedConfig:
    """Immutable, hashed view of the system config.

    `data` is the parsed config dict. `config_hash` is deterministic across
    runs and machines: it is computed from a canonical JSON serialisation
    (sorted keys, fixed separators, UTF-8) so formatting differences in the
    source YAML never change the hash, only actual content changes do.
    """

    data: dict[str, Any]
    source_path: Path
    config_hash: str

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Look up a nested value with dot notation, e.g. 'risk.max_daily_loss_pct'."""
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _canonical_bytes(data: dict[str, Any]) -> bytes:
    """Serialise `data` the same way every time, regardless of dict insertion order."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def compute_config_hash(data: dict[str, Any]) -> str:
    """Return 'sha256:<hex>' for a config dict, matching the format used in
    the output schema (section 13: "config_hash": "sha256:...")."""
    digest = hashlib.sha256(_canonical_bytes(data)).hexdigest()
    return f"sha256:{digest}"


def load_config(path: str | Path | None = None) -> LoadedConfig:
    """Load and hash the YAML config at `path` (defaults to config/default.yaml).

    Raises ConfigError if the file is missing or does not parse to a dict --
    a silent fallback to empty config is exactly the kind of thing section 2
    forbids: no config means no run, not a guess at defaults.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"Config at {config_path} did not parse to a mapping/dict")

    return LoadedConfig(
        data=raw,
        source_path=config_path,
        config_hash=compute_config_hash(raw),
    )


def get_env(key: str, default: str | None = None, required: bool = False) -> str | None:
    """Read a secret/environment override. Never included in config_hash."""
    value = os.environ.get(key, default)
    if required and not value:
        raise ConfigError(f"Required environment variable '{key}' is not set")
    return value
