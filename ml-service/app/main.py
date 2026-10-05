import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from app import __version__
from app.api import health, v1
from app.core.config import check_secrets, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _warm_up() -> None:
    """Load champion models and the employee-review subset in the background so the first analysis is fast."""
    from app.adapters.base import CompanyRef
    from app.core.services import get_analyzer, get_services

    services = get_services()
    for name in services.registry.versions():
        services.registry.get(name)
    services.reviews.reviews(CompanyRef("US_SEC", "0000320193"), datetime.now())
    # Pre-compute the (slow) Employee Sentiment Index of demo companies covered by the review dataset.
    analyzer = get_analyzer()
    for entry in services.sec._universe:
        if int(entry["cik"]) in services.reviews.firm_map and "latest" in entry.get("as_of", []):
            try:
                analyzer.analyze(CompanyRef("US_SEC", f"{int(entry['cik']):010d}"), include_backfill=False)
            except Exception as exc:  # warm-up is best-effort
                logging.getLogger(__name__).warning("warm-up of %s failed: %s", entry["name"], exc)
    logging.getLogger(__name__).info("warm-up complete")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_secrets(get_settings())
    v1._job_store().fail_interrupted()  # retrain jobs orphaned by a restart can never finish
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(
    title="ECHO ML service",
    version=__version__,
    description="Internal inference API: company resolution, analysis, sentiment, model cards, monitoring, retraining.",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(v1.router)
