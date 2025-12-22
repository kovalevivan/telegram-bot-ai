"""
Compatibility entrypoint for platforms that expect `uvicorn main:app`.

Actual application lives in `app/main.py` as `app.main:app`.
"""

from app.main import app  # noqa: F401




