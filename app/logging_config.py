"""
SKKNI Extractor - Konfigurasi Logging Terstruktur (Fase 5A.1).

Menyediakan logging standar dengan rotasi berkas (maks. 10 MB, 5 berkas cadangan)
dan output konsol tanpa membocorkan data sensitif (isi PDF/DOCX, token CSRF, dsb).
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / 'logs'
LOG_FILE = LOG_DIR / 'skkni_extractor.log'

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


def inisialisasi_logging() -> logging.Logger:
    """Inisialisasi sistem logging aplikasi dengan rotasi berkas dan konsol."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger('skkni')
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter_berkas = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    formatter_konsol = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Rotating File Handler
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter_berkas)
    logger.addHandler(file_handler)

    # 2. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter_konsol)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def ambil_logger(nama: str = '') -> logging.Logger:
    """Ambil logger turunan di bawah hierarki 'skkni'."""
    if not logging.getLogger('skkni').handlers:
        inisialisasi_logging()
    if nama:
        return logging.getLogger(f"skkni.{nama}")
    return logging.getLogger('skkni')
