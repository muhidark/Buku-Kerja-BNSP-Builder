"""API status job ekstraksi (Fase 4D)."""

from fastapi import APIRouter, HTTPException

from app import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def status_job(job_id: str):
    job = jobs.ambil_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return job
