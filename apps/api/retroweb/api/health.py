from __future__ import annotations

from fastapi import APIRouter

from retroweb import __version__
from retroweb.api.deps import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": __version__}
