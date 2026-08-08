"""
Lead Triage System — Scheduled & Background Tasks

Provides keep-alive ping tasks for Render cloud deployments and external cron runners.
"""

import os
import sys
import asyncio
from pathlib import Path
import httpx


def ping_health_endpoint(target_url: str | None = None) -> bool:
    """
    Ping health endpoint for cron jobs.
    Usage: python src/tasks.py
    """
    url = target_url or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL") or "http://localhost:8000"
    health_url = f"{url.rstrip('/')}/health"
    print(f"[CRON TASK] Pinging health endpoint: {health_url}")
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(health_url)
            print(f"[CRON TASK] Response status: {res.status_code} | Body: {res.text}")
            return res.status_code == 200
    except Exception as err:
        print(f"[CRON TASK ERROR] Ping failed: {err}")
        return False


async def keep_alive_background_loop():
    """Asynchronous background loop for application lifespan manager."""
    url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
    if not url:
        print("[INFO] Keep-alive background loop inactive (No RENDER_EXTERNAL_URL set).")
        return

    health_url = f"{url.rstrip('/')}/health"
    print(f"[INFO] Keep-alive background loop started targeting: {health_url}")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                await asyncio.sleep(600)  # Ping every 10 minutes (600s)
                res = await client.get(health_url, timeout=10.0)
                print(f"[KEEP-ALIVE] Ping sent to {health_url} | Status: {res.status_code}")
            except Exception as err:
                print(f"[KEEP-ALIVE WARNING] Ping failed: {err}")


if __name__ == "__main__":
    success = ping_health_endpoint()
    sys.exit(0 if success else 1)
