"""Demonstration data for local development.

Run:  python -m app.seed --reset

* Refuses to run when APP_ENV=production.
* Dates are relative to DEMO_DATE (or today in DEFAULT_TIMEZONE), so records never go stale.
* Organisations and people are fictional and flagged `is_demo`. Pesticide products and label rules
  are DEMONSTRATION records ("Demo ..." names, source "DEMO-LBL-...") and are not authoritative
  label data; never use them for real harvest decisions.
* Crop observations are created by running the actual crop-vision model on PlantVillage images
  (CC BY-SA 3.0) bundled in seed_assets/ — the stored predictions are genuine model outputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core import clock
from app.core.config import BACKEND_DIR, get_settings
from app.core.db import Base, SessionLocal, get_engine
from app.core.events import audit, notify
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.modules.farms.models import CropCycle, CropReference, CycleStatus, Farm, Field, GrowthStageRecord
from app.modules.identity.models import Organization, OrgKind, Role, User
from app.modules.monitoring.models import HumanReview, ReviewStatus
from app.modules.monitoring.service import create_observation, ensure_registry
from app.modules.pesticide.models import LabelSource, LabelVerification, PesticideApplication, PesticideProduct, ProductLabel
from app.modules.pesticide.service import record_assessment
from app.modules.pollination.models import (
    BookingEvent,
    BookingStatus,
    PollinationBooking,
    ProviderAvailability,
    ProviderCrop,
    ProviderProfile,
    ProviderServiceArea,
)
from app.modules.produce.models import (
    AssignmentStatus,
    BatchAssignment,
    BatchStatus,
    BuyerDemand,
    BuyerProfile,
    ProduceBatch,
    RerouteRun,
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
)

TZ = "Asia/Kolkata"
# Development-only password shared by every seeded sample account. Never shown in the UI;
# the seed refuses to run in production.
DEMO_PASSWORD = "agastya-demo"
LEAVES = BACKEND_DIR / "seed_assets" / "leaves"
LOC_NOTE = "approximate town centroid (demo record)"

CROPS = [
    # code, name, scientific, category, stages, pollinator_dependent, vision prefix
    ("tomato", "Tomato", "Solanum lycopersicum", "Vegetable",
     ["Nursery", "Transplanting", "Vegetative", "Flowering", "Fruit set", "Harvesting"], False, "Tomato"),
    ("capsicum", "Capsicum", "Capsicum annuum", "Vegetable",
     ["Nursery", "Transplanting", "Vegetative", "Flowering", "Fruit set", "Harvesting"], False, "Pepper,_bell"),
    ("potato", "Potato", "Solanum tuberosum", "Vegetable",
     ["Planting", "Emergence", "Tuber initiation", "Tuber bulking", "Maturity"], False, "Potato"),
    ("maize", "Maize", "Zea mays", "Cereal", ["Emergence", "Vegetative", "Tasseling", "Silking", "Grain fill", "Maturity"], False, "Corn_(maize)"),
    ("grape", "Grape", "Vitis vinifera", "Fruit", ["Pruning", "Bud break", "Flowering", "Berry set", "Veraison", "Harvest"], False, "Grape"),
    ("apple", "Apple", "Malus domestica", "Fruit", ["Dormancy", "Bud break", "Bloom", "Fruit set", "Fruit development", "Harvest"], True, "Apple"),
    ("strawberry", "Strawberry", "Fragaria × ananassa", "Fruit", ["Planting", "Vegetative", "Flowering", "Fruiting"], True, "Strawberry"),
    ("soybean", "Soybean", "Glycine max", "Oilseed", ["Emergence", "Vegetative", "Flowering", "Pod fill", "Maturity"], False, "Soybean"),
    ("mustard", "Mustard", "Brassica juncea", "Oilseed", ["Emergence", "Rosette", "Bolting", "Flowering", "Pod fill", "Maturity"], True, None),
    ("sunflower", "Sunflower", "Helianthus annuus", "Oilseed", ["Emergence", "Vegetative", "Bud", "Flowering", "Seed fill", "Maturity"], True, None),
    ("onion_seed", "Onion (seed crop)", "Allium cepa", "Seed crop", ["Bulb planting", "Vegetative", "Bolting", "Flowering", "Seed set", "Harvest"], True, None),
    ("cucumber", "Cucumber", "Cucumis sativus", "Vegetable", ["Sowing", "Vegetative", "Flowering", "Fruiting"], True, None),
]


def _reset(engine) -> None:
    from alembic import command
    from alembic.config import Config

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        else:
            Base.metadata.drop_all(conn)
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    from app.core.storage import LocalStorage, get_storage

    st = get_storage()
    if isinstance(st, LocalStorage):  # uploaded images belong to the dropped records
        import shutil

        shutil.rmtree(st.root / "observations", ignore_errors=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=ZoneInfo(TZ))


def seed(today: date) -> dict:
    db = SessionLocal()
    pw = hash_password(DEMO_PASSWORD)
    D = lambda n: today + timedelta(days=n)  # noqa: E731

    # Freeze "now" at 11:00 local on the demo date so relative timestamps are consistent.
    clock.freeze(at(today, 11).astimezone(ZoneInfo("UTC")))
    try:
        crops = {}
        for code, name, sci, cat, stages, poll, prefix in CROPS:
            c = CropReference(code=code, name=name, scientific_name=sci, category=cat, growth_stages=stages,
                              pollinator_dependent=poll, vision_label_prefix=prefix)
            db.add(c)
            crops[code] = c
        db.flush()

        def org(name, kind):
            o = Organization(name=name, kind=kind, is_demo=True)
            db.add(o)
            db.flush()
            return o

        def user(email, name, role, o, phone=None):
            u = User(email=email, full_name=name, role=role, organization_id=o.id if o else None, password_hash=pw,
                     is_demo=True, phone=phone)
            db.add(u)
            db.flush()
            return u

        patil = org("Patil Family Farms", OrgKind.FARM)
        shinde = org("Shinde Agro", OrgKind.FARM)
        madhuban = org("Madhuban Apiaries", OrgKind.PROVIDER)
        deccan = org("Deccan Pollination Services", OrgKind.PROVIDER)
        kullu = org("Kullu Valley Beekeepers", OrgKind.PROVIDER)
        godavari = org("Godavari Fresh Traders", OrgKind.BUYER)
        pune = org("Pune Greens Retail", OrgKind.BUYER)
        ghats = org("Western Ghats Agro Processors", OrgKind.BUYER)
        mumbai = org("Mumbai Fresh Link", OrgKind.BUYER)
        anna = org("Annapoorna Community Kitchen", OrgKind.BUYER)
        desk = org("Krishi Review Desk", OrgKind.AGENCY)
        platform = org("AGASTYA Operations", OrgKind.PLATFORM)

        ramesh = user("ramesh@agastya.demo", "Ramesh Patil", Role.FARMER, patil, "+91 90000 00001")
        sunita = user("sunita@agastya.demo", "Sunita Shinde", Role.FARMER, shinde)
        anil = user("anil@agastya.demo", "Anil Jadhav", Role.PROVIDER, madhuban)
        meera = user("meera@agastya.demo", "Meera Gaikwad", Role.PROVIDER, deccan)
        user("tenzin@agastya.demo", "Tenzin Negi", Role.PROVIDER, kullu)
        imran = user("imran@agastya.demo", "Imran Shaikh", Role.BUYER, godavari)
        kavya = user("kavya@agastya.demo", "Kavya Rao", Role.BUYER, pune)
        user("vikram@agastya.demo", "Vikram More", Role.BUYER, ghats)
        user("farah@agastya.demo", "Farah Qureshi", Role.BUYER, mumbai)
        user("lata@agastya.demo", "Lata Pawar", Role.BUYER, anna)
        asha = user("asha@agastya.demo", "Dr. Asha Kulkarni", Role.REVIEWER, desk)
        admin = user("admin@agastya.demo", "Neha Iyer", Role.ADMIN, platform)

        # ---------------------------------------------------------------- farms
        pimpalgaon = Farm(organization_id=patil.id, name="Pimpalgaon Farm", village="Pimpalgaon Baswant", district="Nashik",
                          state="Maharashtra", timezone=TZ, latitude=20.17, longitude=73.99, location_source=LOC_NOTE)
        sinnar = Farm(organization_id=patil.id, name="Sinnar Farm", village="Sinnar", district="Nashik", state="Maharashtra",
                      timezone=TZ, latitude=19.85, longitude=74.00, location_source=LOC_NOTE)
        yeola = Farm(organization_id=shinde.id, name="Yeola Farm", village="Yeola", district="Nashik", state="Maharashtra",
                     timezone=TZ, latitude=20.04, longitude=74.49, location_source=LOC_NOTE)
        db.add_all([pimpalgaon, sinnar, yeola])
        db.flush()
        f_north = Field(farm_id=pimpalgaon.id, name="North Plot", area_ha=1.2, soil_type="Medium black", irrigation="Drip")
        f_poly = Field(farm_id=pimpalgaon.id, name="Polyhouse 1", area_ha=0.4, soil_type="Prepared beds", irrigation="Drip")
        f_river = Field(farm_id=pimpalgaon.id, name="River Plot", area_ha=2.0, soil_type="Alluvial", irrigation="Canal")
        f_east = Field(farm_id=sinnar.id, name="East Field", area_ha=1.5, soil_type="Shallow black", irrigation="Sprinkler")
        f_west = Field(farm_id=sinnar.id, name="West Field", area_ha=1.0, soil_type="Shallow black", irrigation="Rainfed")
        f_yeola = Field(farm_id=yeola.id, name="Main Field", area_ha=2.0, soil_type="Medium black", irrigation="Well")
        db.add_all([f_north, f_poly, f_river, f_east, f_west, f_yeola])
        db.flush()

        def cycle(field, crop, variety, sow, stage, fl=None, harvest=None, status=CycleStatus.ACTIVE, by=ramesh):
            c = CropCycle(field_id=field.id, crop_id=crops[crop].id, variety=variety, season="Rabi 2026" if sow.month >= 9 else "Kharif 2026",
                          sowing_date=sow, current_stage=stage, expected_flowering_start=fl[0] if fl else None,
                          expected_flowering_end=fl[1] if fl else None, expected_harvest_date=harvest, status=status, created_by=by.id)
            db.add(c)
            db.flush()
            return c

        tomato = cycle(f_north, "tomato", "Abhinav (hybrid)", D(-95), "Harvesting", (D(-50), D(-20)), D(4), CycleStatus.HARVESTING)
        capsicum = cycle(f_poly, "capsicum", "Indra", D(-110), "Harvesting", (D(-65), D(-35)), D(1), CycleStatus.HARVESTING)
        mustard = cycle(f_river, "mustard", "Pusa Bold", D(-12), "Rosette", (D(24), D(44)), D(95))
        sunflower = cycle(f_east, "sunflower", "KBSH-44", D(-48), "Bud", (D(8), D(22)), D(55))
        cycle(f_west, "soybean", "JS 335", D(-150), "Maturity", (D(-110), D(-95)), D(-40), CycleStatus.CLOSED)
        y_mustard = cycle(f_yeola, "mustard", "RH 749", D(-5), "Emergence", (D(15), D(35)), D(100), by=sunita)

        for c, stages in [
            (tomato, [("Transplanting", -88), ("Vegetative", -70), ("Flowering", -50), ("Fruit set", -32), ("Harvesting", -8)]),
            (capsicum, [("Transplanting", -100), ("Flowering", -65), ("Fruit set", -40), ("Harvesting", -18)]),
            (mustard, [("Emergence", -7), ("Rosette", -1)]),
            (sunflower, [("Emergence", -42), ("Vegetative", -30), ("Bud", -3)]),
            (y_mustard, [("Emergence", -1)]),
        ]:
            for s, d in stages:
                db.add(GrowthStageRecord(crop_cycle_id=c.id, stage=s, observed_on=D(d), recorded_by=c.created_by))

        # ---------------------------------------------------------------- pesticide reference (DEMO)
        def product(name, ai, form, ptype):
            p = PesticideProduct(trade_name=name, active_ingredient=ai, formulation=form, product_type=ptype,
                                 registrant="Demonstration record", registration_ref=None, created_by=admin.id)
            db.add(p)
            db.flush()
            return p

        mancozeb = product("Demo Mancozeb 75 WP", "Mancozeb 75%", "WP", "Fungicide")
        imida = product("Demo Imidacloprid 17.8 SL", "Imidacloprid 17.8%", "SL", "Insecticide")
        spinosad = product("Demo Spinosad 45 SC", "Spinosad 45%", "SC", "Insecticide")
        copper = product("Demo Copper Oxychloride 50 WP", "Copper oxychloride 50%", "WP", "Fungicide")
        n = 0

        def label(p, crop, phi, status, vfrom, vuntil=None, version="2025.1", source_kind=LabelSource.DEMO_SEED, src=None, by=admin):
            nonlocal n
            n += 1
            lbl = ProductLabel(
                product_id=p.id, crop_id=crops[crop].id, label_version=version, phi_days=phi, dose_unit="g or ml per litre",
                source_reference=src or f"DEMO-LBL-{n:04d} · demonstration record for development only; not an authoritative label",
                source_kind=source_kind, verification_status=status, valid_from=vfrom, valid_until=vuntil, submitted_by=by.id,
                verified_by=admin.id if status == LabelVerification.VERIFIED else None,
                verified_at=clock.now_utc() - timedelta(days=60) if status == LabelVerification.VERIFIED else None,
            )
            db.add(lbl)
            return lbl

        V, U = LabelVerification.VERIFIED, LabelVerification.UNVERIFIED
        label(mancozeb, "tomato", 5, V, date(2024, 1, 1))
        label(mancozeb, "capsicum", 7, V, date(2024, 1, 1))
        label(mancozeb, "potato", 7, V, date(2024, 1, 1))
        label(imida, "tomato", 3, V, date(2024, 1, 1))
        label(imida, "capsicum", 3, U, date(2025, 1, 1), source_kind=LabelSource.MANUAL, by=ramesh,
              src="Entered by farmer from the product leaflet; awaiting verification")
        label(spinosad, "tomato", 1, V, date(2022, 1, 1), date(2024, 12, 31), version="2022.1")
        label(spinosad, "tomato", 3, V, date(2025, 1, 1), version="2025.1")
        db.flush()

        def apply(c, p, days_ago, hh, dose, unit, target, area=None, rec_phi=None):
            a = PesticideApplication(crop_cycle_id=c.id, product_id=p.id, applied_at=at(D(-days_ago), hh), dose_value=dose,
                                     dose_unit=unit, treated_area_ha=area or float(db.get(Field, c.field_id).area_ha),
                                     application_method="Knapsack sprayer", target_problem=target, recorded_phi_days=rec_phi,
                                     recorded_by=ramesh.id)
            db.add(a)
            db.flush()
            audit(db, actor_id=ramesh.id, action="application.recorded", entity_type="pesticide_application", entity_id=a.id,
                  after={"product": p.trade_name, "applied_at": a.applied_at.isoformat()}, severity="safety")
            return a

        apply(tomato, imida, 9, 7, 0.5, "ml per litre", "Whitefly")
        apply(tomato, spinosad, 6, 17, 0.3, "ml per litre", "Fruit borer")
        record_assessment(db, tomato, trigger="seed", actor_id=None, notify_change=False)
        apply(tomato, mancozeb, 1, 7, 2.5, "g per litre", "Early blight")
        apply(capsicum, mancozeb, 6, 8, 2.0, "g per litre", "Leaf spot")
        apply(capsicum, imida, 2, 18, 0.4, "ml per litre", "Thrips", rec_phi=3)
        for c in (tomato, capsicum, mustard, sunflower):
            record_assessment(db, c, trigger="seed", actor_id=None)

        # ---------------------------------------------------------------- pollination
        def provider(o, name, district, state, lat, lon, radius, colonies, crop_codes, areas, desc, phone):
            p = ProviderProfile(organization_id=o.id, display_name=name, provider_type="Apiary", base_district=district,
                                base_state=state, latitude=lat, longitude=lon, service_radius_km=radius, colonies_total=colonies,
                                contact_phone=phone, description=desc)
            db.add(p)
            db.flush()
            for cc in crop_codes:
                db.add(ProviderCrop(provider_id=p.id, crop_id=crops[cc].id))
            for dist, st in areas:
                db.add(ProviderServiceArea(provider_id=p.id, district=dist, state=st))
            return p

        p_madhuban = provider(madhuban, "Madhuban Apiaries", "Nashik", "Maharashtra", 20.00, 73.79, 120, 120,
                              ["sunflower", "mustard", "onion_seed", "cucumber"], [("Nashik", "Maharashtra"), ("Ahmednagar", "Maharashtra")],
                              "Migratory Apis mellifera colonies with on-site placement and weekly hive checks.", "+91 90000 00011")
        p_deccan = provider(deccan, "Deccan Pollination Services", "Ahmednagar", "Maharashtra", 19.09, 74.74, 200, 200,
                            ["sunflower", "mustard", "onion_seed", "strawberry"],
                            [("Ahmednagar", "Maharashtra"), ("Pune", "Maharashtra"), ("Nashik", "Maharashtra")],
                            "Large-scale colony rental for oilseed and seed-production crops.", "+91 90000 00012")
        provider(kullu, "Kullu Valley Beekeepers", "Kullu", "Himachal Pradesh", 31.96, 77.11, 150, 300,
                 ["apple", "strawberry", "mustard"], [("Kullu", "Himachal Pradesh"), ("Shimla", "Himachal Pradesh")],
                 "Orchard pollination for apple growers in the Kullu and Shimla valleys.", "+91 90000 00013")
        db.flush()
        db.add(ProviderAvailability(provider_id=p_madhuban.id, start_date=D(-5), end_date=D(75), colonies_available=80,
                                    notes="Rabi season placement"))
        db.add(ProviderAvailability(provider_id=p_deccan.id, start_date=D(20), end_date=D(90), colonies_available=150))
        kullu_p = db.query(ProviderProfile).filter_by(organization_id=kullu.id).one()
        db.add(ProviderAvailability(provider_id=kullu_p.id, start_date=D(120), end_date=D(180), colonies_available=250,
                                    notes="Apple bloom"))
        db.flush()

        def booking(c, p, start, end, colonies, status, by, events):
            b = PollinationBooking(crop_cycle_id=c.id, provider_id=p.id, requested_by=by.id, start_date=start, end_date=end,
                                   colonies_requested=colonies, status=status, farmer_note="Please place hives on the north boundary.")
            db.add(b)
            db.flush()
            for frm, to, actor, note in events:
                db.add(BookingEvent(booking_id=b.id, from_status=frm, to_status=to, actor_id=actor.id, note=note))
            return b

        b1 = booking(sunflower, p_madhuban, D(8), D(20), 4, BookingStatus.ACCEPTED, ramesh,
                     [(None, "requested", ramesh, None), ("requested", "accepted", anil, "Four colonies reserved.")])
        b1.provider_note = "Four colonies reserved."
        b2 = booking(y_mustard, p_madhuban, D(15), D(32), 6, BookingStatus.REQUESTED, sunita, [(None, "requested", sunita, None)])
        notify(db, [ramesh.id], event_type="booking.accepted", title="Pollination booking accepted",
               body=f"Sunflower, Sinnar Farm: {b1.start_date:%d %b} – {b1.end_date:%d %b}.", entity_type="pollination_booking",
               entity_id=b1.id, link="/app/pollination")
        notify(db, [anil.id], event_type="booking.requested", title="New request: Mustard, Nashik",
               body=f"6 colonies, {b2.start_date:%d %b} – {b2.end_date:%d %b}.", entity_type="pollination_booking",
               entity_id=b2.id, link=f"/app/provider/bookings?id={b2.id}")

        # ---------------------------------------------------------------- buyers & demand
        def buyer(o, name, btype, district, state, lat, lon, cap, pref, phone):
            b = BuyerProfile(organization_id=o.id, display_name=name, buyer_type=btype, district=district, state=state,
                             latitude=lat, longitude=lon, receiving_capacity_kg_per_day=cap, delivery_preference=pref,
                             contact_phone=phone)
            db.add(b)
            db.flush()
            return b

        by_god = buyer(godavari, "Godavari Fresh Traders", "Wholesaler", "Nashik", "Maharashtra", 20.01, 73.80, Decimal(5000), "either", "+91 90000 00021")
        by_pune = buyer(pune, "Pune Greens Retail", "Retail chain", "Pune", "Maharashtra", 18.52, 73.86, Decimal(1500), "farm_delivery", "+91 90000 00022")
        by_ghats = buyer(ghats, "Western Ghats Agro Processors", "Processor", "Satara", "Maharashtra", 17.68, 74.02, Decimal(10000), "buyer_pickup", "+91 90000 00023")
        by_mum = buyer(mumbai, "Mumbai Fresh Link", "Distributor", "Thane", "Maharashtra", 19.22, 72.98, Decimal(4000), "either", "+91 90000 00024")
        by_anna = buyer(anna, "Annapoorna Community Kitchen", "Community kitchen", "Nashik", "Maharashtra", 19.99, 73.78, Decimal(600), "farm_delivery", "+91 90000 00025")

        def demand(b, crop, grades, qty, vf, vu, ds, de, maxd=None, notes=None, status="open"):
            d = BuyerDemand(buyer_id=b.id, crop_id=crops[crop].id, accepted_grades=grades, quantity_kg=Decimal(qty), valid_from=vf,
                            valid_until=vu, delivery_start=ds, delivery_end=de, max_distance_km=maxd, notes=notes, status=status)
            db.add(d)
            db.flush()
            return d

        dm_god = demand(by_god, "tomato", ["A", "B"], 2000, D(-7), D(10), D(-2), D(6), 80)
        dm_pune = demand(by_pune, "tomato", ["A"], 800, D(-10), D(10), D(-1), D(4), 250)
        demand(by_ghats, "tomato", ["B", "C"], 5000, D(-5), D(30), D(2), D(12), 350, "Puree line")
        demand(by_mum, "tomato", ["A", "B"], 3000, D(-3), D(14), D(1), D(6), 300)
        demand(by_anna, "tomato", ["A", "B", "C"], 1500, D(-3), D(20), D(0), D(3), 50)
        dm_pune_cap = demand(by_pune, "capsicum", ["A"], 500, D(-20), D(15), D(-15), D(10), 250)
        dm_god_cap = demand(by_god, "capsicum", ["A", "B"], 600, D(-25), D(-10), D(-20), D(-10), 80, status="closed")

        # ---------------------------------------------------------------- produce batches
        def batch(code, c, crop, qty, grade, harvested, shelf, status, storage="Shade net, ambient", deliver_by=None):
            b = ProduceBatch(code=code, organization_id=patil.id, crop_cycle_id=c.id, crop_id=crops[crop].id,
                             quantity_value=Decimal(qty), unit="kg", quantity_kg=Decimal(qty), grade=grade,
                             harvested_on=harvested, shelf_life_days=shelf, shelf_life_source="supplied" if shelf else None,
                             storage_condition=storage, available_from=harvested, deliver_by=deliver_by, status=status,
                             harvest_check_status="eligible", harvest_check_details={"unresolved_count": 0, "rule_version": "phi-1"},
                             created_by=ramesh.id)
            db.add(b)
            db.flush()
            return b

        def assign(b, buyer_p, dm, status, reason, assigned_days_ago, shipment_status, ended=None, end_reason=None, ended_by=None):
            a = BatchAssignment(batch_id=b.id, buyer_id=buyer_p.id, demand_id=dm.id, quantity_kg=b.quantity_kg, status=status,
                                reason=reason, assigned_by=ramesh.id, assigned_at=at(D(-assigned_days_ago), 16),
                                ended_at=at(D(-ended), 10) if ended is not None else None, end_reason=end_reason,
                                ended_by=ended_by.id if ended_by else None)
            db.add(a)
            db.flush()
            sh = Shipment(batch_id=b.id, assignment_id=a.id, status=shipment_status, scheduled_date=D(-assigned_days_ago + 2))
            db.add(sh)
            db.flush()
            db.add(ShipmentEvent(shipment_id=sh.id, status="scheduled", note=f"Delivery to {buyer_p.display_name}", actor_id=ramesh.id))
            return a, sh

        t1 = batch("TOM-A1", tomato, "tomato", 1200, "A", D(-3), 7, BatchStatus.ASSIGNED)
        assign(t1, by_god, dm_god, AssignmentStatus.ACTIVE, "initial", 2, ShipmentStatus.SCHEDULED)
        t2 = batch("TOM-A2", tomato, "tomato", 600, "A", D(-3), 7, BatchStatus.NEEDS_DESTINATION)
        assign(t2, by_pune, dm_pune, AssignmentStatus.CANCELLED_BY_BUYER, "initial", 2, ShipmentStatus.CANCELLED, ended=0,
               end_reason="Cold-room fault at our receiving store", ended_by=kavya)
        audit(db, actor_id=kavya.id, action="assignment.cancelled_by_buyer", entity_type="produce_batch", entity_id=t2.id,
              after={"status": "needs_destination", "reason": "Cold-room fault at our receiving store"}, severity="warning")
        notify(db, [ramesh.id], event_type="batch.buyer_cancelled", title="Pune Greens Retail cancelled TOM-A2",
               body="600 kg Tomato needs a new destination. Reason: Cold-room fault at our receiving store",
               entity_type="produce_batch", entity_id=t2.id, link=f"/app/batches/{t2.id}", severity="warning")

        c1 = batch("CAP-A1", capsicum, "capsicum", 400, "A", D(-14), 10, BatchStatus.DELIVERED, storage="Cool room, 10 °C")
        assign(c1, by_god, dm_god_cap, AssignmentStatus.CANCELLED_BY_BUYER, "initial", 14, ShipmentStatus.CANCELLED, ended=13,
               end_reason="Order volume reduced", ended_by=imran)
        db.add(RerouteRun(batch_id=c1.id, trigger="buyer_cancelled", note=None, triggered_by=ramesh.id, as_of_date=D(-13),
                          scoring_version="br-1"))
        a2, sh2 = assign(c1, by_pune, dm_pune_cap, AssignmentStatus.COMPLETED, "reroute_buyer_cancelled", 13,
                         ShipmentStatus.DELIVERED, ended=11, end_reason="Delivered", ended_by=kavya)
        db.add(ShipmentEvent(shipment_id=sh2.id, status="dispatched", note=None, actor_id=ramesh.id))
        db.add(ShipmentEvent(shipment_id=sh2.id, status="delivered", note="Received in good condition", actor_id=kavya.id))
        batch("CAP-A2", capsicum, "capsicum", 250, "B", D(-2), 10, BatchStatus.UNASSIGNED, storage="Cool room, 10 °C")
        db.flush()

        # ---------------------------------------------------------------- observations (real model inference)
        ensure_registry(db)
        observations = [
            (tomato, "tomato_healthy_0.jpg", -21, "Lower canopy check before fruit set."),
            (tomato, "tomato_early_blight_0.jpg", -6, "Brown rings on older leaves, east rows."),
            (tomato, "tomato_late_blight_0.jpg", -1, "Dark water-soaked patches after rain."),
            (capsicum, "pepper_healthy_0.jpg", -10, None),
            (capsicum, "pepper_bacterial_spot_0.jpg", -3, "Small dark spots on a few plants near the door."),
        ]
        made = []
        sources = {s["file"]: s["source"] for s in json.loads((LEAVES / "sources.json").read_text())}
        for c, fname, d, note in observations:
            raw = (LEAVES / fname).read_bytes()
            o = create_observation(db, user=ramesh, cycle=c, raw=raw, filename=fname, notes=note, observed_at=at(D(d), 9, 30),
                                   source_note=f"{sources.get(fname, 'PlantVillage')} (CC BY-SA 3.0)")
            made.append(o)
        early = made[1]
        if early.predictions and early.predictions[0].predicted_class:
            r = HumanReview(observation_id=early.id, prediction_id=early.predictions[0].id, reviewer_id=asha.id, decision="confirmed",
                            reviewed_label="Tomato — early blight", notes="Concentric lesions on older leaves are consistent with early blight.",
                            recommended_action="Remove affected lower leaves; re-inspect in 5 days.")
            db.add(r)
            early.review_status = ReviewStatus.REVIEWED
            notify(db, [ramesh.id], event_type="observation.reviewed", title="Review recorded for your Tomato observation",
                   body="Dr. Asha Kulkarni: confirmed.", entity_type="crop_observation", entity_id=early.id,
                   link=f"/app/observations/{early.id}")
        db.commit()
        return {
            "users": db.query(User).count(),
            "observations": len(made),
            "predictions": [(o.id, o.status, o.predictions[0].predicted_class if o.predictions else None,
                             o.predictions[0].confidence if o.predictions else None) for o in made],
        }
    finally:
        clock.freeze(None)
        db.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed AGASTYA demonstration data")
    parser.add_argument("--reset", action="store_true", help="drop all tables, re-run migrations, then seed")
    args = parser.parse_args(argv)
    s = get_settings()
    if s.is_production:
        print("Refusing to seed demonstration data in production.", file=sys.stderr)
        return 2
    engine = get_engine()
    if args.reset:
        _reset(engine)
    today = s.demo_today() or datetime.now(ZoneInfo(s.default_timezone)).date()
    summary = seed(today)
    print(f"Seeded demo data for {today}: {summary['users']} users, {summary['observations']} observations")
    for p in summary["predictions"]:
        print("  observation", p)
    print(f"Development-only password for every seeded sample account: {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
