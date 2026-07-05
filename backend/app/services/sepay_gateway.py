"""Small SePay Payment Gateway REST client used for reconciliation."""
import base64

import httpx
from fastapi import HTTPException

from app.config import settings


async def fetch_sepay_order(order_invoice_number: str) -> dict:
    credentials = base64.b64encode(
        f"{settings.SEPAY_MERCHANT_ID}:{settings.SEPAY_MERCHANT_SECRET_KEY}".encode()
    ).decode()
    url = f"{settings.SEPAY_API_BASE_URL.rstrip('/')}/v1/order"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Basic {credentials}"},
            params={"q": order_invoice_number},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"SePay reconciliation failed ({response.status_code})",
        )

    payload = response.json()
    expected = order_invoice_number.strip().upper()
    matched = next(
        (
            row
            for row in payload.get("data", [])
            if str(row.get("order_invoice_number") or "").strip().upper() == expected
        ),
        None,
    )
    if not matched:
        raise HTTPException(status_code=404, detail="SePay không tìm thấy đơn hàng")
    return {"data": matched}
