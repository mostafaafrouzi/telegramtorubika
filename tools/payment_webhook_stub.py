#!/usr/bin/env python3
"""
Minimal HTTP hooks for (simulated) payment + plan grant.

Run on the same host as the bot, with the same working directory / .env / queue DB.

  PAYMENT_WEBHOOK_SECRET=yoursecret python tools/payment_webhook_stub.py

Plan grant (unchanged)::

  curl -X POST http://127.0.0.1:8787/grant \\
    -H "Authorization: Bearer yoursecret" \\
    -H "Content-Type: application/json" \\
    -d '{"user_id":123456,"tier":"pro","days":30}'

Update one row in ``v2_payments`` (v2 billing ledger)::

  curl -X POST http://127.0.0.1:8787/v2_payment_event \\
    -H "Authorization: Bearer yoursecret" \\
    -H "Content-Type: application/json" \\
    -d '{"payment_id":1,"status":"paid","ref_id":"test-ref"}'
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from queue_db import QueueDB  # noqa: E402
from user_entitlements import set_user_tier  # noqa: E402
from v2.billing.webhook import (  # noqa: E402
    apply_verified_payment_event,
    parse_verified_event_from_dict,
)

SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "change-me").strip()
PORT = int(os.getenv("WEBHOOK_PORT", "8787"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/grant", "/v2_payment_event"):
            self.send_error(404)
            return
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {SECRET}":
            self.send_error(401)
            return
        try:
            ln = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(ln).decode("utf-8") if ln else "{}"
            body = json.loads(raw)
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
            return

        if self.path == "/grant":
            try:
                uid = int(body["user_id"])
                tier = str(body.get("tier", "pro")).lower()
                days = int(body.get("days", 30))
                exp = int(time.time()) + days * 86400 if tier == "pro" and days > 0 else 0
                set_user_tier(uid, tier, exp)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return
        else:
            try:
                ev = parse_verified_event_from_dict(body)
                apply_verified_payment_event(QueueDB(), ev)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def main():
    print(
        f"Listening 127.0.0.1:{PORT}\n"
        f"  POST /grant  (plan)\n"
        f"  POST /v2_payment_event  (v2_payments status; same Bearer secret)"
    )
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
