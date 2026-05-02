#!/usr/bin/env python3
"""Set user plan from the server shell (no Telegram). Examples:
  python tools/grant_plan.py tier 12345 pro --days 30
  python tools/grant_plan.py bonus 12345 500
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from user_entitlements import add_bonus_month_mb, set_user_tier  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Grant tier or monthly bonus MB to a Telegram user id.")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier", help="Set guest|free|pro")
    t.add_argument("user_id", type=int)
    t.add_argument("name", choices=["guest", "free", "pro"])
    t.add_argument("--days", type=int, default=0, help="If tier is pro, validity in days (from now).")
    b = sub.add_parser("bonus", help="Add extra monthly quota MB (stacking)")
    b.add_argument("user_id", type=int)
    b.add_argument("mb", type=int)
    args = p.parse_args()
    if args.cmd == "tier":
        exp = 0
        if args.name == "pro" and args.days > 0:
            exp = int(time.time()) + args.days * 86400
        set_user_tier(args.user_id, args.name, exp)
        print(f"OK tier={args.name} user={args.user_id} expires_at={exp}")
    else:
        add_bonus_month_mb(args.user_id, args.mb)
        print(f"OK bonus +{args.mb} MB user={args.user_id}")


if __name__ == "__main__":
    main()
