"""Download the Kaggle "Glassdoor Job Reviews" dataset (M3) into data/raw/reviews.

Kaggle serves this public dataset without a login. It lists no licence, so ECHO treats it as
academic-use only (DATA_STRATEGY L2): it is never committed or redistributed, and a commercial deployment
must plug a licensed source into `ReviewSource` instead. The Kaggle CDN often drops long connections, so the
download resumes with HTTP Range requests.

    python -m pipelines.ingestion.reviews_dataset
"""

from __future__ import annotations

import logging
import zipfile

import httpx

from pipelines.common import RAW_DIR, setup_logging, update_manifest

log = logging.getLogger("echo.ingestion.reviews")
URL = "https://www.kaggle.com/api/v1/datasets/download/davidgauthier/glassdoor-job-reviews"
PAGE = "https://www.kaggle.com/datasets/davidgauthier/glassdoor-job-reviews"
OUT_DIR = RAW_DIR / "reviews"
ZIP = OUT_DIR / "glassdoor-job-reviews.zip"
CSV = OUT_DIR / "glassdoor_reviews.csv"


def download_with_resume(url: str, attempts: int = 20) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = None
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        for attempt in range(1, attempts + 1):
            have = ZIP.stat().st_size if ZIP.exists() else 0
            if total is not None and have >= total:
                return
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code not in (200, 206):
                        raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                    if resp.status_code == 200:
                        have = 0  # server ignored the range: restart
                        total = int(resp.headers.get("content-length", 0)) or None
                    else:
                        total = int(resp.headers["content-range"].split("/")[-1])
                    with ZIP.open("ab" if have else "wb") as fh:
                        for block in resp.iter_bytes(1 << 20):
                            fh.write(block)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                log.info("attempt %d interrupted at %d bytes (%s); resuming", attempt, ZIP.stat().st_size, exc)
                continue
            if total is None or ZIP.stat().st_size >= total:
                return
    raise RuntimeError("download did not complete")


def main() -> None:
    if CSV.exists():
        log.info("Using cached %s", CSV)
        return
    download_with_resume(URL)
    update_manifest(RAW_DIR / "MANIFEST.json", ZIP, PAGE)
    with zipfile.ZipFile(ZIP) as zf:
        zf.extract("glassdoor_reviews.csv", OUT_DIR)
    log.info("Extracted %s (%.0f MB)", CSV, CSV.stat().st_size / 1e6)


if __name__ == "__main__":
    setup_logging()
    main()
