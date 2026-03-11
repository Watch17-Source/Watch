"""Simulate a device (for server testing without hardware).

Usage:
  python3 tools/sim_device.py --server http://192.168.68.58 --device-id 1 --token <TOKEN> heartbeat
  python3 tools/sim_device.py --server http://192.168.68.58 --device-id 1 --token <TOKEN> alarm

This uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import urllib.request


def http_json(method: str, url: str, token: str, payload: dict | None = None):
    data = None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Device-Token": token,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="e.g. http://192.168.68.58")
    ap.add_argument("--device-id", type=int, required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("cmd", choices=["heartbeat", "alarm", "sync"])
    args = ap.parse_args()

    base = args.server.rstrip("/")
    did = args.device_id

    if args.cmd == "heartbeat":
        url = f"{base}/api/v1/device/{did}/heartbeat"
        out = http_json("POST", url, args.token, {"state": "ARMED"})
        print(out)
        return

    if args.cmd == "sync":
        url = f"{base}/api/v1/device/{did}/sync?state=ARMED"
        out = http_json("GET", url, args.token, None)
        print(out)
        return

    if args.cmd == "alarm":
        url = f"{base}/api/v1/device/{did}/event"
        out = http_json("POST", url, args.token, {"type": "ALARM_START", "state": "ALARM", "details": {"note": "simulated"}})
        print(out)
        return


if __name__ == "__main__":
    main()
