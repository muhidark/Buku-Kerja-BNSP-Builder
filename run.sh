#!/usr/bin/env bash
# SKKNI Extractor - jalankan server lokal (Fase 4A)
set -euo pipefail

PROYEK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$PROYEK/.venv/bin/python"
HOST="127.0.0.1"
PORT="${PORT:-8000}"

if [ ! -x "$PY" ]; then
  echo "Virtual environment tidak ditemukan: $PY" >&2
  echo "Buat dengan: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if ! "$PY" - <<'CEK'
import importlib, sys
wajib = ["fastapi", "uvicorn", "jinja2", "fitz", "docx"]
kurang = []
for nama in wajib:
    try:
        importlib.import_module(nama)
    except Exception:
        kurang.append(nama)
if kurang:
    print("Dependensi belum terpasang: " + ", ".join(kurang), file=sys.stderr)
    sys.exit(1)
CEK
then
  echo "Instal dengan: .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

cd "$PROYEK"
echo "SKKNI Extractor"
echo "  modul  : app.main:app"
echo "  alamat : http://$HOST:$PORT"
echo "  berhenti: Ctrl+C"
echo

exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
