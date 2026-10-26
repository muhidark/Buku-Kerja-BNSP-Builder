"""Endpoint status sistem (Fase 4A)."""

from fastapi import APIRouter

from app import web_data
from app.version import __version__

router = APIRouter(prefix="/api", tags=["system"])

VERSI_APLIKASI = __version__


@router.get("/health")
def health():
    """Status dasar aplikasi."""
    return {
        "status": "ok",
        "application": "SKKNI Extractor",
        "version": VERSI_APLIKASI,
    }


@router.get("/system/status")
def system_status():
    """Status modul ekstraktor + direktori penyimpanan (data nyata)."""
    return {
        "sistem": web_data.status_sistem(),
        "modul": web_data.status_modul(),
    }
