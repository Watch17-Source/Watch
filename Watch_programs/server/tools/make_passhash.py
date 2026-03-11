"""Generate a password hash for WATCH server config.

Usage:
  source .venv/bin/activate
  python3 tools/make_passhash.py "newpassword"

Output format:
  pbkdf2_sha256$iters$salt_b64$hash_b64

Then set in server/config.py:
  ADMIN_PASSWORD = None
  ADMIN_PASSWORD_HASH = "<output>"
"""

from __future__ import annotations

import sys
from security import hash_password

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/make_passhash.py <password>")
        raise SystemExit(2)
    pw = sys.argv[1]
    ph = hash_password(pw).to_string()
    print(ph)

if __name__ == "__main__":
    main()
