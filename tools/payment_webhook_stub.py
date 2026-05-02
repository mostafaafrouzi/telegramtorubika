#!/usr/bin/env python3
"""
Minimal HTTP hook to grant a plan after (simulated) payment.
Run on the same host as the bot, with the same working directory / .env / queue DB.

  PAYMENT_WEBHOOK_SECRET=yoursecret python tools/payment_webhook_stub.py

  curl -X POST http://127.0.0.1:8787/grant \\
    -H "Authorization: Bearer yoursecret" \\
    -H "Content-Type: application/json" \\
    -d '{"user_id":123456,"tier":"pro","days":30}'
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

from user_entitlements import set_user_tier  # noqa: E402

SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "change-me").strip()
PORT = int(os.getenv("WEBHOOK_PORT", "8787"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/grant":
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
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def main():
    print(f"Listening 127.0.0.1:{PORT} POST /grant (Bearer secret)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
