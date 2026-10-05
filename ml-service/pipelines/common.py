"""Shared paths, HTTP and data-manifest helpers for the offline pipelines."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
import yaml

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
DATA_DIR = Path(os.environ.get("ECHO_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
MAPPINGS_DIR = ML_ROOT / "mappings"
CONFIGS_DIR = ML_ROOT / "configs"
ARTIFACTS_DIR = Path(os.environ.get("MODEL_DIR", ML_ROOT / "artifacts"))
REPORTS_DIR = ML_ROOT / "reports"

SEED = 42
DEFAULT_SEC_USER_AGENT = "ECHO-academic-project research@echo-project.dev"

log = logging.getLogger("echo.pipelines")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:  # torch is only installed for transformer training
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def sec_user_agent() -> str:
    """SEC requires a descriptive User-Agent with a contact address (set SEC_USER_AGENT in .env)."""
    return os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT


@lru_cache
def load_mapping(name: str) -> dict:
    return yaml.safe_load((MAPPINGS_DIR / name).read_text(encoding="utf-8"))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def update_manifest(manifest_path: Path, file_path: Path, url: str) -> dict:
    """Record sha256, source URL and retrieval time of a raw input (ML_PIPELINE §7.5)."""
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    key = file_path.relative_to(manifest_path.parent).as_posix()
    entry = {
        "sha256": sha256_file(file_path),
        "bytes": file_path.stat().st_size,
        "url": url,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    manifest[key] = entry
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return entry


def manifest_hash(manifest_path: Path) -> str:
    """One hash over a whole manifest, logged with every training run."""
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else ""


def download(url: str, dest: Path, *, headers: dict | None = None, refresh: bool = False,
             manifest: Path | None = None, timeout: float = 120.0) -> Path:
    """Stream a URL to disk (skipped if the file exists, unless refresh=True)."""
    if dest.exists() and not refresh:
        log.info("Using cached %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("Downloading %s -> %s", url, dest)
    started = time.monotonic()
    with httpx.stream("GET", url, headers=headers or {}, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for block in resp.iter_bytes(1 << 20):
                fh.write(block)
    tmp.replace(dest)
    log.info("Downloaded %.1f MB in %.0fs", dest.stat().st_size / 1e6, time.monotonic() - started)
    if manifest is not None:
        update_manifest(manifest, dest, url)
    return dest


class RateLimitedClient:
    """Minimal polite HTTP client: fixed minimum interval between requests + retries on 429/5xx."""

    def __init__(self, min_interval: float, headers: dict | None = None, timeout: float = 30.0):
        self._client = httpx.Client(headers=headers or {}, timeout=timeout, follow_redirects=True)
        self._min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, params: dict | None = None, retries: int = 3) -> httpx.Response:
        for attempt in range(retries + 1):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self._client.get(url, params=params)
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
                return resp
            time.sleep(2 ** attempt * max(self._min_interval, 1.0))
        return resp

    def close(self) -> None:
        self._client.close()


def sector_for_sic(sic: int | str | None) -> str:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return "Other"
    mapping = load_mapping("sic_sectors.yaml")
    for lo, hi, sector in mapping["ranges"]:
        if lo <= code <= hi:
            return sector
    return mapping["default"]


def is_bank_sic(sic: int | str | None) -> bool:
    try:
        return 6000 <= int(sic) <= 6399
    except (TypeError, ValueError):
        return False


def is_financial_sic(sic: int | str | None) -> bool:
    try:
        return 6000 <= int(sic) <= 6999
    except (TypeError, ValueError):
        return False
