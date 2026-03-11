# WATCH Server (Raspberry Pi 4B)

This folder contains the **local-only web hub** for WATCH: *Wireless Alarm and Threat-Check Hub for Classrooms*.

✅ Works on **Python 3.11.2**  
✅ Uses **Flask + SQLite**  
✅ Designed for **LAN use without internet**

---

## 1) Assumptions / Network

- Raspberry Pi static IP reservation: **192.168.68.58**
- Devices are also on the same LAN (static IP reservations recommended).
- Guards access the hub from any phone/PC on the LAN:  
  - If running on port **80**: `http://192.168.68.58/`  
  - If running on port **8080**: `http://192.168.68.58:8080/`

---

## 2) Install (Python 3.11.2)

```bash
cd server
python3 --version
# should show 3.11.2 (or 3.11.x)

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

---

## 3) Configure

Edit `server/config.py`:

- Admin login (default is **admin/admin** — change it!)
- Port (default is **80**)
- Offline threshold, pause duration, etc.

**Time zone is important.**  
Schedules use the Raspberry Pi **local time**. Set timezone to Asia/Manila:

```bash
sudo timedatectl set-timezone Asia/Manila
timedatectl
```

---

## 4) Run (for quick test)

```bash
cd server
source .venv/bin/activate
python3 app.py
```

Then open: `http://192.168.68.58/`

---

## 5) Run on boot (systemd)

A sample service file is in `systemd/watchhub.service`.

### Install:

1) Copy project to a stable location, e.g. `/home/pi/WATCH/`
2) Edit the service file path inside `watchhub.service` if needed.
3) Copy + enable:

```bash
sudo cp systemd/watchhub.service /etc/systemd/system/watchhub.service
sudo systemctl daemon-reload
sudo systemctl enable --now watchhub.service
sudo systemctl status watchhub.service
```

### Logs:

```bash
journalctl -u watchhub.service -f
```

---

## 6) Add a device

1) Log in to the website
2) Go to **Add Device**
3) Enter device static IP + room name
4) Copy the generated **device token**
5) Paste it into `device/config.py` on that device

---

## Notes on security (LAN)

- This system is intended for **local LAN** use.
- Keep device tokens private.
- Change admin password before deployment.
