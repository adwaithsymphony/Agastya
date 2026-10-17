"""End-to-end demo flow through the real UI (Playwright, Chromium).

Prerequisites: the API is running with freshly seeded demo data and the built frontend is served
at BASE_URL (default http://127.0.0.1:8000, see README "End-to-end tests"):

    cd backend && python -m app.seed --reset
    FRONTEND_DIST=../frontend/dist uvicorn app.main:app --port 8000
    pytest ../e2e -q
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
LEAF = Path(__file__).resolve().parents[1] / "backend" / "seed_assets" / "leaves" / "tomato_septoria_leaf_spot_0.jpg"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def pick(select, prefix: str) -> None:
    """Select the first option whose text starts with `prefix` (waits for options to load)."""
    expect(select.locator("option", has_text=prefix).first).to_be_attached()
    label = select.evaluate("(el, p) => [...el.options].find(o => o.text.startsWith(p))?.text", prefix)
    assert label, f"no option starting with {prefix!r}"
    select.select_option(label=label)


ACCOUNTS = {
    "Farmer": "ramesh@agastya.demo",
    "Pollination provider": "anil@agastya.demo",
    "Buyer": "imran@agastya.demo",
    "Reviewer": "asha@agastya.demo",
    "Administrator": "admin@agastya.demo",
}
SAMPLE_PASSWORD = os.environ.get("E2E_PASSWORD", "agastya-demo")  # development seed only


def login(browser, who: str) -> Page:
    ctx = browser.new_context(viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE}/login")
    page.get_by_label("Email").fill(ACCOUNTS[who])
    page.get_by_label("Password", exact=True).fill(SAMPLE_PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()
    return page


def test_01_landing_and_login_validation(browser):
    page = browser.new_page()
    page.goto(BASE + "/")
    expect(page.get_by_role("heading", name=re.compile("Grow Smarter"))).to_be_visible()
    page.get_by_role("link", name="Explore the platform").click()
    expect(page.get_by_role("heading", name="Sign in to AGASTYA")).to_be_visible()
    # no sample accounts or shared password on the public page
    expect(page.get_by_text("agastya-demo")).to_have_count(0)
    expect(page.get_by_text(re.compile("demo", re.I))).to_have_count(0)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_text("Enter a valid email address.")).to_be_visible()
    expect(page.get_by_text("Enter your password.")).to_be_visible()
    page.get_by_label("Email").fill("ramesh@agastya.demo")
    pw = page.get_by_label("Password", exact=True)
    pw.fill("wrong-password")
    page.get_by_role("button", name="Show password").click()
    expect(pw).to_have_attribute("type", "text")
    page.get_by_role("button", name="Hide password").click()
    expect(pw).to_have_attribute("type", "password")
    pw.press("Enter")  # keyboard submit
    expect(page.get_by_role("alert")).to_contain_text("Email or password is incorrect.")
    page.close()


def test_02_farmer_uploads_leaf_and_gets_model_result(browser):
    page = login(browser, "Farmer")
    page.get_by_label("Main").get_by_role("link", name="Crop health").click()
    pick(page.get_by_label("Crop cycle"), "Tomato")
    # client-side validation for a non-image file
    page.get_by_label("Leaf photo").set_input_files({"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello"})
    expect(page.get_by_text("Choose a JPEG, PNG or WebP photo.")).to_be_visible()
    page.get_by_label("Leaf photo").set_input_files(str(LEAF))
    page.get_by_role("button", name="Save and analyse").click()
    expect(page.get_by_text("Model reading")).to_be_visible(timeout=15000)
    expect(page.get_by_text(re.compile("Tomato — Septoria leaf spot"))).to_be_visible()
    expect(page.get_by_text(re.compile(r"\d+% confidence"))).to_be_visible()
    page.get_by_role("link", name="Open observation").click()
    expect(page.get_by_role("heading", name="Tomato observation")).to_be_visible()
    page.context.close()


def test_03_spray_record_recalculates_harvest_eligibility(browser):
    page = login(browser, "Farmer")
    page.get_by_label("Main").get_by_role("link", name="Harvest safety").click()
    page.get_by_role("button", name=re.compile("^Tomato")).click()
    page.get_by_role("button", name="Record spray").first.click()
    dlg = page.get_by_role("dialog")
    pick(dlg.get_by_label("Product"), "Demo Spinosad")
    expect(dlg.get_by_text(re.compile("Fictional sample label rule for Tomato"))).to_be_visible()  # provenance shown
    dlg.get_by_label("Dose").fill("0.3")
    dlg.get_by_role("button", name="Save application").click()
    expect(page.get_by_text(re.compile("Recorded. Status"))).to_be_visible()
    expect(page.get_by_text(re.compile(r"Eligible from \d"))).to_be_visible()
    # a batch harvested today must be refused inside the restriction
    page.goto(f"{BASE}/app/batches")
    page.get_by_role("button", name="Record batch").click()
    dlg = page.get_by_role("dialog")
    pick(dlg.get_by_label("Crop cycle"), "Tomato")
    dlg.get_by_label("Quantity").fill("100")
    dlg.get_by_role("button", name="Save batch").click()
    expect(dlg.get_by_role("alert")).to_contain_text("pre-harvest interval")
    page.context.close()


def test_04_pollination_request_and_provider_acceptance(browser):
    farmer = login(browser, "Farmer")
    farmer.get_by_label("Main").get_by_role("link", name="Pollination").click()
    expect(farmer.get_by_label("Crop cycle")).to_have_value(re.compile(r"\d+"))
    pick(farmer.get_by_label("Crop cycle"), "Mustard")
    farmer.get_by_label("Colonies needed").fill("6")
    farmer.get_by_role("button", name="Request booking").first.click()
    farmer.get_by_role("dialog").get_by_role("button", name="Send request").click()
    expect(farmer.get_by_text("Request sent to provider")).to_be_visible()
    farmer.context.close()

    provider = login(browser, "Pollination provider")
    provider.get_by_label("Main").get_by_role("link", name="Bookings").click()
    row = provider.locator("li", has_text="Mustard, 2 ha").filter(has_text="Pimpalgaon")
    row.get_by_role("button", name="Accept").click()
    provider.get_by_role("dialog").get_by_role("button", name="Accept booking").click()
    expect(provider.get_by_text("Booking accepted")).to_be_visible()
    provider.context.close()

    farmer = login(browser, "Farmer")
    farmer.goto(f"{BASE}/app/pollination")
    expect(farmer.locator("li", has_text="Mustard — River Plot").get_by_text("Accepted")).to_be_visible()
    farmer.context.close()


def test_05_buyer_cancels_and_farmer_reroutes(browser):
    buyer = login(browser, "Buyer")
    buyer.get_by_label("Main").get_by_role("link", name="Deliveries").click()
    item = buyer.locator("li", has_text="TOM-A1")
    item.get_by_role("button", name="Cancel delivery").click()
    dlg = buyer.get_by_role("dialog")
    dlg.get_by_label("Reason").fill("Market yard closed for two days")
    dlg.get_by_role("button", name="Cancel delivery").click()
    expect(buyer.get_by_text(re.compile("farmer has been notified"))).to_be_visible()
    buyer.context.close()

    farmer = login(browser, "Farmer")
    expect(farmer.get_by_text("TOM-A1: 1,200 kg Tomato needs a buyer")).to_be_visible()
    farmer.get_by_text("TOM-A1: 1,200 kg Tomato needs a buyer").click()
    expect(farmer.get_by_text("This batch needs a new destination.")).to_be_visible()
    farmer.get_by_role("button", name="Find buyers").first.click()
    expect(farmer.get_by_role("heading", name="Recommended destinations")).to_be_visible()
    first = farmer.get_by_role("button", name="Choose").first
    buyer_name = farmer.locator("ol li").first.locator("span.font-semibold").first.inner_text()
    first.click()
    farmer.get_by_role("dialog").get_by_role("button", name="Confirm destination").click()
    expect(farmer.get_by_text(f"Assigned to {buyer_name}")).to_be_visible()
    expect(farmer.get_by_role("heading", name="Current destination")).to_be_visible()
    # persisted across reload; history keeps the cancelled assignment
    farmer.reload()
    expect(farmer.get_by_text("Buyer assigned").first).to_be_visible()
    expect(farmer.get_by_text("Cancelled by buyer")).to_be_visible()
    farmer.get_by_role("button", name=re.compile("Notifications")).click()
    expect(farmer.get_by_text(re.compile("cancelled TOM-A1"))).to_be_visible()
    farmer.context.close()


def test_06_cross_role_access_rejected(browser):
    buyer = login(browser, "Buyer")
    buyer.goto(f"{BASE}/app/batches")
    expect(buyer.get_by_text("This area isn't available for your role.")).to_be_visible()
    status = buyer.evaluate("fetch('/api/v1/batches').then(r => r.status)")
    assert status == 403
    status = buyer.evaluate("fetch('/api/v1/crop-cycles/1').then(r => r.status)")
    assert status in (403, 404)
    buyer.context.close()


def test_07_reviewer_records_review(browser):
    page = login(browser, "Reviewer")
    page.get_by_label("Main").get_by_role("link", name="Review queue").click()
    page.get_by_role("main").locator("li a").first.click()
    expect(page.get_by_role("heading", name="Record your review")).to_be_visible()
    page.get_by_label("Correct it").check()
    page.get_by_label("Your assessment").fill("Tomato — late blight")
    page.get_by_role("button", name="Save review").click()
    expect(page.get_by_text("Review recorded")).to_be_visible()
    expect(page.get_by_role("heading", name="Agronomist review")).to_be_visible()
    page.context.close()


def test_08_admin_verifies_label(browser):
    page = login(browser, "Administrator")
    page.get_by_label("Main").get_by_role("link", name="Reference data").click()
    page.get_by_role("button", name="Review").first.click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("Authoritative source").fill("Checked against approved label copy (e2e test)")
    dlg.get_by_role("button", name="Verify rule").click()
    expect(page.get_by_text(re.compile("Label verified"))).to_be_visible()
    page.get_by_label("Main").get_by_role("link", name="Audit log").click()
    expect(page.get_by_text("label.verified").first).to_be_visible()
    page.context.close()
