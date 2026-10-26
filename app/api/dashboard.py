"""Endpoint ringkasan dashboard (Fase 4A)."""

from fastapi import APIRouter

from app import web_data
from app.version import __version__

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard():
    """Ringkasan dari data lokal yang benar-benar tersedia (tanpa dummy)."""
    data = web_data.dashboard_data()
    data["application"] = "SKKNI Extractor"
    data["version"] = __version__
    return data
