"""Catalog price edits must reach public readers without cached price fallbacks."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.routes import checkout, plans
from app.services.payments import public_order
from app.services.plans import DEFAULT_PLANS


class Catalog:
    def __init__(self):
        self.rows = [{**deepcopy(plan), "_id": ObjectId(), "version": 1} for plan in DEFAULT_PLANS]

    def find(self, query):
        rows = [deepcopy(row) for row in self.rows if all(row.get(key) == value for key, value in query.items())]

        class Cursor:
            def sort(self, key, _direction):
                rows.sort(key=lambda row: row[key])
                return self

            async def to_list(self, _limit):
                return rows

        return Cursor()

    async def find_one(self, query):
        return next((deepcopy(row) for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)

    async def update_one(self, query, update):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                row.update(update["$set"])
                break


@pytest.fixture
async def catalog_client(monkeypatch):
    catalog = Catalog()
    database = SimpleNamespace(db=SimpleNamespace(plans=catalog, platform_audit_logs=SimpleNamespace(insert_one=AsyncMock())))

    async def get_database():
        return database

    monkeypatch.setattr(plans, "get_mongodb", get_database)
    monkeypatch.setattr(checkout, "get_mongodb", get_database)
    app = FastAPI()
    app.include_router(plans.router)
    app.include_router(checkout.router)
    app.dependency_overrides[plans.require_platform_admin] = lambda: {"_id": "fixture-admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, catalog


async def test_admin_price_edit_is_immediately_visible_in_public_catalog_and_detail(catalog_client):
    client, catalog = catalog_client
    growth = next(row for row in catalog.rows if row["key"] == "growth")
    changed = await client.patch(f"/api/platform/plans/{growth['_id']}", json={
        "name": "Gói mới", "monthly_price": 3_750_000, "vat_rate": 8,
        "display_features": ["Nội dung mới từ Admin"], "badge": "Ưu đãi mới",
    })
    assert changed.status_code == 200
    for path in ("/api/plans/public", "/api/plans/growth"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        current = next(row for row in response.json() if row["key"] == "growth") if path.endswith("public") else response.json()
        assert current["monthly_price"] == 3_750_000
        assert current["name"] == "Gói mới"
        assert current["vat_rate"] == 8
        assert current["display_features"] == ["Nội dung mới từ Admin"]


async def test_public_catalog_omits_hidden_and_archived_but_supports_new_plan_keys(catalog_client):
    client, catalog = catalog_client
    catalog.rows[0]["is_public"] = False
    catalog.rows[1]["is_active"] = False
    catalog.rows.append({**deepcopy(catalog.rows[2]), "_id": ObjectId(), "key": "scale", "display_order": 1})
    response = await client.get("/api/plans/public")
    assert [row["key"] for row in response.json()] == ["scale", "business", "custom"]
    assert (await client.get("/api/plans/growth")).status_code == 404


async def test_contact_price_is_not_interpreted_as_free_but_zero_price_still_is(catalog_client):
    client, catalog = catalog_client
    assert (await client.get("/api/checkout/quote?plan=starter")).json()["total"] == 0
    catalog.rows[0]["monthly_price"] = None
    catalog.rows[0]["requires_contact"] = False
    response = await client.get("/api/checkout/quote?plan=starter")
    assert response.status_code == 400
    assert "liên hệ" in response.json()["detail"]


def test_completed_order_keeps_purchased_plan_name_from_snapshot():
    order = {
        "order_id": "fixture-order", "status": "completed", "plan": "scale",
        "plan_snapshot": {"name": "Tên gói lúc mua"}, "email": "fixture@example.test",
        "subtotal": 1_000_000, "discount": 0, "vat": 80_000, "total": 1_080_000,
    }
    assert public_order(order)["plan_name"] == "Tên gói lúc mua"
    del order["plan_snapshot"]
    assert public_order(order)["plan_name"] == "scale"
