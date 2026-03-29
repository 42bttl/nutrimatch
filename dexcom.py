import os
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv

load_dotenv()

DEXCOM_SANDBOX = os.getenv("DEXCOM_SANDBOX", "true").lower() == "true"
BASE_URL = "https://sandbox-api.dexcom.com" if DEXCOM_SANDBOX else "https://api.dexcom.com"
CLIENT_ID = os.getenv("DEXCOM_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DEXCOM_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DEXCOM_REDIRECT_URI", "http://localhost:8000/auth/dexcom/callback")


def is_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def get_auth_url() -> str:
    return (
        f"{BASE_URL}/v2/oauth2/login"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=offline_access"
    )


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/v2/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_token_flow(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/v2/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_egvs(access_token: str, start_date: datetime, end_date: datetime) -> list:
    """Fetch Estimated Glucose Values (EGVs) from the Dexcom API."""
    fmt = "%Y-%m-%dT%H:%M:%S"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/v3/users/self/egvs",
            params={
                "startDate": start_date.strftime(fmt),
                "endDate": end_date.strftime(fmt),
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("egvs", [])
