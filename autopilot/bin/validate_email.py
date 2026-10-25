#!/usr/bin/env python3
"""Check an address before any pitch. Usage: validate_email.py <address> [<address> ...]
Prints [{"input","valid","normalized","mx","reason"}]. Syntax + domain MX via email-validator (Unlicense)."""
import json, sys
try:
    from email_validator import validate_email, EmailNotValidError
except ImportError:
    print(json.dumps({"error": "email-validator missing: pip install --target /home/user/pylib email-validator"})); sys.exit(0)

def check(a):
    try:
        v = validate_email(a, check_deliverability=True)
        return {"input": a, "valid": True, "normalized": v.normalized, "mx": [m[1] for m in (getattr(v, "mx", None) or [])][:3], "reason": None}
    except EmailNotValidError as e:
        return {"input": a, "valid": False, "normalized": None, "mx": [], "reason": str(e)[:160]}
    except Exception as e:
        return {"input": a, "valid": False, "normalized": None, "mx": [], "reason": "check failed: " + str(e)[:120]}

print(json.dumps([check(a) for a in sys.argv[1:]], indent=1))
