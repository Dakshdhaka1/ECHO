from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.inference.model_cards import load_model_cards

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    cards = load_model_cards(settings.model_dir)
    return {
        "status": "UP",
        "service": "echo-ml-service",
        "version": __version__,
        "demo_mode": settings.demo_mode,
        "explanation_provider": settings.explanation_provider,
        "models": [{"name": c.get("name"), "version": c.get("version")} for c in cards],
    }
