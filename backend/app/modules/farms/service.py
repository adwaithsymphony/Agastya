"""Farm/field/cycle access control. Every lookup enforces organisation ownership."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.modules.farms.models import CropCycle, Farm, Field
from app.modules.identity.models import Role, User

READ_ALL_ROLES = {Role.ADMIN.value}


def _check_org(user: User, organization_id: int, *, write: bool, extra_read_roles: set[str] = frozenset()) -> None:
    if user.role == Role.FARMER and user.organization_id == organization_id:
        return
    if not write and (user.role in READ_ALL_ROLES or user.role in extra_read_roles):
        return
    # Do not reveal whether the record exists.
    raise NotFound("Record not found.")


def get_farm(db: Session, user: User, farm_id: int, *, write: bool = False) -> Farm:
    farm = db.get(Farm, farm_id)
    if not farm:
        raise NotFound("Farm not found.")
    _check_org(user, farm.organization_id, write=write)
    return farm


def get_field(db: Session, user: User, field_id: int, *, write: bool = False) -> Field:
    field = db.get(Field, field_id)
    if not field:
        raise NotFound("Field not found.")
    _check_org(user, field.farm.organization_id, write=write)
    return field


def get_cycle(
    db: Session, user: User, cycle_id: int, *, write: bool = False, extra_read_roles: set[str] = frozenset()
) -> CropCycle:
    cycle = db.get(CropCycle, cycle_id)
    if not cycle:
        raise NotFound("Crop cycle not found.")
    _check_org(user, cycle.field.farm.organization_id, write=write, extra_read_roles=extra_read_roles)
    return cycle


def farmer_cycles_stmt(user: User):
    if user.role != Role.FARMER:
        raise Forbidden("Only farm accounts manage crop cycles.")
    return (
        select(CropCycle)
        .join(Field, CropCycle.field_id == Field.id)
        .join(Farm, Field.farm_id == Farm.id)
        .where(Farm.organization_id == user.organization_id)
    )


def cycle_label(c: CropCycle) -> str:
    return f"{c.crop.name} · {c.field.name}, {c.field.farm.name}"
