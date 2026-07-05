from bson import ObjectId
from fastapi import HTTPException
import pytest

from app.routes.platform_admin import serialize
from app.services import sepay_gateway


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    response = None
    request = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        type(self).request = (url, kwargs)
        return type(self).response


def test_serialize_converts_nested_object_ids():
    site_id = ObjectId()
    member_id = ObjectId()

    result = serialize({
        "_id": ObjectId(),
        "sites": [{"_id": site_id}],
        "members": [{"_id": member_id}],
    })

    assert result["sites"][0]["_id"] == str(site_id)
    assert result["members"][0]["_id"] == str(member_id)
    assert isinstance(result["id"], str)


async def test_sepay_reconciliation_uses_exact_invoice_match(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {
        "data": [
            {"order_invoice_number": "AUR-WRONG", "order_status": "CAPTURED"},
            {"order_invoice_number": "aur-right", "order_status": "CAPTURED"},
        ],
    })
    monkeypatch.setattr(sepay_gateway.httpx, "AsyncClient", FakeAsyncClient)

    result = await sepay_gateway.fetch_sepay_order("AUR-RIGHT")

    assert result["data"]["order_invoice_number"] == "aur-right"
    url, kwargs = FakeAsyncClient.request
    assert url.endswith("/v1/order")
    assert kwargs["params"] == {"q": "AUR-RIGHT"}


async def test_sepay_reconciliation_rejects_fuzzy_only_match(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {
        "data": [{"order_invoice_number": "AUR-ORDER-EXTRA"}],
    })
    monkeypatch.setattr(sepay_gateway.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as exc:
        await sepay_gateway.fetch_sepay_order("AUR-ORDER")

    assert exc.value.status_code == 404
