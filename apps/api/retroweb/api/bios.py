"""BIOS inventory endpoints. Files are addressed by registry name only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from retroweb.api.deps import StorageDep, UserDep
from retroweb.api.uploads import read_bounded
from retroweb.library.bios import MAX_BIOS_BYTES
from retroweb.library.systems import GameSystem
from retroweb.schemas.bios import BiosFileOut, SystemBiosOut
from retroweb.services import bios as bios_service
from retroweb.services.bios import SystemBiosStatus

router = APIRouter(prefix="/bios", tags=["bios"])


def _to_out(status: SystemBiosStatus) -> SystemBiosOut:
    installed = {row.spec.filename: row for row in status.installed}
    files = []
    for spec in status.info.files:
        row = installed.get(spec.filename)
        files.append(
            BiosFileOut(
                filename=spec.filename,
                description=spec.description,
                known_md5=spec.md5,
                installed=row is not None,
                size_bytes=row.size_bytes if row else None,
                sha256=row.sha256 if row else None,
                md5=row.md5 if row else None,
                verified=row.verified if row else None,
            )
        )
    preferred = next((row.spec.filename for row in status.installed), None)
    return SystemBiosOut(
        system=status.info.system,
        note=status.info.note,
        optional=status.info.optional,
        ready=status.ready,
        preferred_file=preferred,
        files=files,
    )


@router.get("", response_model=list[SystemBiosOut])
def list_bios(storage: StorageDep, _user: UserDep) -> list[SystemBiosOut]:
    return [_to_out(status) for status in bios_service.inventory(storage)]


@router.get("/{system}", response_model=SystemBiosOut)
def system_bios(system: GameSystem, storage: StorageDep, _user: UserDep) -> SystemBiosOut:
    return _to_out(bios_service.system_status(storage, system))


@router.post("/{system}", response_model=SystemBiosOut, status_code=201)
def upload_bios(
    system: GameSystem,
    storage: StorageDep,
    _user: UserDep,
    file: Annotated[UploadFile, File()],
) -> SystemBiosOut:
    bios_service.system_status(storage, system)  # 404 for systems without BIOS
    data = read_bounded(file, MAX_BIOS_BYTES)
    bios_service.install(storage, system, file.filename or "", data)
    return _to_out(bios_service.system_status(storage, system))


@router.get("/{system}/{filename}")
def download_bios(
    system: GameSystem, filename: str, storage: StorageDep, _user: UserDep
) -> Response:
    name, data = bios_service.read_file(storage, system, filename)
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{name}"',
            "Cache-Control": "private, max-age=3600",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


@router.delete("/{system}/{filename}", status_code=204)
def delete_bios(system: GameSystem, filename: str, storage: StorageDep, _user: UserDep) -> Response:
    bios_service.remove(storage, system, filename)
    return Response(status_code=204)
