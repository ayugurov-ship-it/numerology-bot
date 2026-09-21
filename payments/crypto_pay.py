import os
import aiohttp
from typing import Optional

TESTNET_API_TOKEN = os.getenv("CRYPTO_PAY_TESTNET_API_TOKEN")
TESTNET_API_URL = "https://testnet-pay.crypt.bot/api"

class CryptoPayError(RuntimeError):
    pass

async def _api_request(method: str, payload: Optional[dict] = None) -> dict:
    if not TESTNET_API_TOKEN:
        raise CryptoPayError("CRYPTO_PAY_TESTNET_API_TOKEN is not configured")
    headers = {"Crypto-Pay-API-Token": TESTNET_API_TOKEN, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{TESTNET_API_URL}/{method}", headers=headers, json=payload or {}) as response:
            text = await response.text()
            if response.status != 200:
                raise CryptoPayError(f"HTTP {response.status}: {text[:500]}")
            data = await response.json()
            if not data.get("ok"):
                raise CryptoPayError(f"Crypto Pay {method} failed: {data.get('error', 'unknown error')}")
            return data.get("result") or {}

async def get_me() -> dict:
    return await _api_request("getMe")

async def create_test_invoice(amount: str = "1", user_id: Optional[int] = None) -> dict:
    payload = {
        "currency_type": "crypto",
        "asset": "USDT",
        "amount": amount,
        "description": "SoulCode Test — тестовая оплата",
        "hidden_message": "Тестовая оплата успешно завершена.",
        "payload": f"testpay:{user_id or 0}",
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 900,
    }
    return await _api_request("createInvoice", payload)

async def get_invoice(invoice_id: int) -> dict:
    result = await _api_request("getInvoices", {"invoice_ids": str(invoice_id), "count": 1})
    if not result:
        raise CryptoPayError(f"Invoice {invoice_id} not found")
    return result[0]
