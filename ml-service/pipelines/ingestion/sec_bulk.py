"""Download SEC EDGAR bulk archives (public domain) into data/raw/sec with a sha256 manifest.

    python -m pipelines.ingestion.sec_bulk [--refresh]
"""

from __future__ import annotations

import argparse

from pipelines.common import RAW_DIR, download, sec_user_agent, setup_logging

BULK_FILES = {
    "companyfacts.zip": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "submissions.zip": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
}
SEC_RAW = RAW_DIR / "sec"
MANIFEST = RAW_DIR / "MANIFEST.json"


def main(refresh: bool = False) -> None:
    headers = {"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    for name, url in BULK_FILES.items():
        download(url, SEC_RAW / name, headers=headers, refresh=refresh, manifest=MANIFEST, timeout=600)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download even if cached")
    main(parser.parse_args().refresh)
