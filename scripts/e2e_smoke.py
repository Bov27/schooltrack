"""End-to-end smoke test against a running stack (docker compose) with the demo data.

It drives the system the way people use it:

1. a school admin signs in to the dashboard and reads the attendance report through it;
2. the demo student checks in from "the phone" (a live GPS event inside the geofence);
3. the worker turns that event into a notification that the guardian sees;
4. the admin sees the student as present.

Only the standard library is used, so it runs on a bare CI runner.

    python scripts/e2e_smoke.py --api http://localhost:8000 --web http://localhost:3000
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

DOMAIN = "demo.schooltrack.test"
CENTER = (2.4419, -76.6063)


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.headers: dict[str, str] = {}
        # Kept by hand: the dashboard marks its cookies Secure, and http.cookiejar never
        # sends Secure cookies over plain http, even to localhost (browsers do).
        self.cookies: dict[str, str] = {}

    def _keep_cookies(self, headers: Any) -> None:
        for header in headers.get_all("set-cookie") or []:
            name, _, rest = header.partition("=")
            value = rest.split(";", 1)[0]
            if value:
                self.cookies[name.strip()] = value
            else:
                self.cookies.pop(name.strip(), None)

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(  # noqa: S310 - URL comes from the command line
            f"{self.base}{path}", data=data, method=method
        )
        request.add_header("content-type", "application/json")
        for name, value in self.headers.items():
            request.add_header(name, value)
        if self.cookies:
            request.add_header("cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                self._keep_cookies(response.headers)
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, raw.decode(errors="replace")


def expect(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}")
        sys.exit(1)
    print(f"ok   {message}")


def api_login(api_url: str, email: str, password: str) -> Client:
    client = Client(api_url)
    status, body = client.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    expect(status == 200, f"{email} signs in to the API")
    client.headers["authorization"] = f"Bearer {body['access_token']}"
    return client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--web", default="http://localhost:3000")
    args = parser.parse_args()
    password = os.environ.get("SCHOOLTRACK_DEMO_PASSWORD", "")
    if len(password) < 12:
        sys.exit("Set SCHOOLTRACK_DEMO_PASSWORD to the password used by seed-demo")

    # 1. Dashboard: sign in through the BFF; the browser never holds the tokens.
    web = Client(args.web)
    status, _ = web.call(
        "POST", "/api/auth/login", {"email": f"rectoria@{DOMAIN}", "password": password}
    )
    expect(status == 200, "the school admin signs in to the dashboard")
    status, me = web.call("GET", "/api/backend/users/me")
    expect(status == 200 and me["memberships"], "the dashboard proxies authenticated calls")
    web.headers["x-institution-id"] = me["memberships"][0]["institution_id"]
    today = date.today()
    status, report = web.call(
        "GET",
        f"/api/backend/analytics/attendance?from={today - timedelta(days=21)}&to={today}",
    )
    expect(status == 200 and len(report["students"]) == 8, "the attendance report has 8 students")
    status, _ = web.call("GET", "/api/backend/../health")
    expect(status in (400, 404), "the dashboard proxy refuses path traversal")

    # 2. Phone: the student checks in inside the geofence.
    student = api_login(args.api, f"estudiante@{DOMAIN}", password)
    _, states = student.call("GET", "/api/v1/attendance/state")
    expect(states[0]["state"] == "OUTSIDE", "the student starts the day outside")
    _, campuses = student.call("GET", "/api/v1/campuses")
    now = datetime.now(UTC)
    event = {
        "idempotency_key": str(uuid.uuid4()),
        "event_type": "CHECK_IN",
        "campus_id": campuses[0]["id"],
        "occurred_at": (now - timedelta(seconds=1)).isoformat(),
        "latitude": CENTER[0],
        "longitude": CENTER[1],
        "accuracy_m": 8,
        "location_captured_at": (now - timedelta(seconds=2)).isoformat(),
    }
    status, created = student.call("POST", "/api/v1/attendance/events", event)
    expect(status == 201 and created["validation_status"] == "VALIDATED", "check-in is validated")
    status, _ = student.call("POST", "/api/v1/attendance/events", event)
    expect(status == 200, "retrying the same request returns the original event")

    # 3. Worker: the guardian is notified (outbox -> Celery -> notification).
    guardian = api_login(args.api, f"acudiente@{DOMAIN}", password)
    deadline = time.monotonic() + 60
    notifications: list[Any] = []
    while time.monotonic() < deadline:
        _, notifications = guardian.call("GET", "/api/v1/notifications")
        if notifications:
            break
        time.sleep(2)
    expect(bool(notifications), "the guardian receives a notification within 60 s")
    _, children = guardian.call("GET", "/api/v1/attendance/guardian/students")
    valentina = next(c for c in children if c["full_name"] == "Valentina Muñoz")
    expect(valentina["state"] == "PRESENT", "the guardian sees the student as present")

    # 4. Dashboard again: the event is listed.
    status, events = web.call("GET", "/api/backend/attendance/events?limit=5")
    expect(
        status == 200 and any(e["id"] == created["id"] for e in events),
        "the admin sees the new event in the dashboard",
    )
    print("E2E smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
