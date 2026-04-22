# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Infrastructure-as-config repository for monitoring a **Ragtech Easy Pro 4164** UPS (nobreak) using Network UPS Tools (NUT). The UPS uses a proprietary binary protocol incompatible with standard NUT drivers, so the solution bridges it via a Python daemon + dummy-ups driver.

**Deployment topology:**
- **NUT Server (MiniCinnamon / Raspberry Pi — 192.168.50.20):** Reads UPS over USB serial (`/dev/ttyACM0`, 2400 baud) and publishes data to NUT via `upsrw`.
- **NUT Client (Ugreen DH4300 Plus NAS — 192.168.50.110):** Monitors NUT server over TCP and shuts itself down on `OB LB`.
- The NUT server never shuts down (`SHUTDOWNCMD="/bin/true"`); only the NAS does.

## Repository Layout

```
configs/          NUT config files → deploy to /etc/nut/ on the server
scripts/
  ragtech_nut.py  Main daemon → deploy to /opt/ragtech-monitor/
  notifycmd.py    upsmon hook (Telegram + WOL) → deploy to /etc/nut/
  teste_simulacao.sh  Full end-to-end simulation test (run as root on server)
systemd/          Drop-in and service units → deploy to /etc/systemd/system/
```

`configs/upsd.users` is gitignored (contains real passwords). Use `configs/upsd.users.example` as the template and replace `CHANGE_ME_*` placeholders before deploying.

## Deployment Commands (run on NUT server)

```bash
# Install dependencies
sudo apt install -y nut-server nut-client python3-serial wakeonlan

# Add nut user to dialout for USB serial access
sudo usermod -aG dialout nut

# Test UPS communication before deploying the daemon
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyACM0', 2400, timeout=2)
s.write(bytes.fromhex('AA0400801E9E'))
time.sleep(0.5)
r = s.read(64)
s.close()
print(r.hex())
# Expected: starts with 'aa' and is 31+ bytes
"

# Verify NUT stack is healthy
upsc ragtech@127.0.0.1 | grep -E "ups.status|battery|input.voltage"
systemctl is-active ragtech-monitor nut-server nut-monitor

# Run simulation test (safe — does not physically cut power)
sudo bash scripts/teste_simulacao.sh
```

## Key Configuration Constraints

- **`/etc/nut/nut.conf` must be `MODE=netserver`**, not `standalone`. With `standalone`, upsd rejects external connections from the NAS.
- **`/etc/nut/upsd.conf` must use only `LISTEN 0.0.0.0 3493`**. Combining `127.0.0.1` and `0.0.0.0` on the same port causes silent bind failures — especially on WiFi where the IP isn't assigned when the service starts.
- **`systemd/nut-server-network-wait.conf`** ensures upsd starts only after the network interface has an IP (`network-online.target`). This is critical on both WiFi and Raspberry Pi.
- The desktop power manager (Cinnamon/GNOME) can independently shut down the server via `upower` on low battery. Disable with `gsettings set org.cinnamon.settings-daemon.plugins.power critical-battery-action 'nothing'`. Not needed on Raspberry Pi.

## Proprietary Protocol

The Ragtech Easy Pro 4164 uses a binary protocol (USB ID `04d8:000a`, CDC ACM):

- **Query:** `AA 04 00 80 1E 9E` (6 bytes)
- **Response:** 31 bytes starting with `0xAA`
- Key offsets and formulas are in `scripts/ragtech_nut.py:44–51` and documented in `DDS.md` section 4.

Status logic: `OB` when `input_v < 50.0V`; `LB` added when `battery_pct < 25%`.

## Secrets

- `configs/upsd.users` — gitignored, never commit.
- `scripts/notifycmd.py` — contains `BOT_TOKEN` and `CHAT_ID` as literals; replace before deploying.
- `scripts/ragtech_nut.py` — contains `NUT_PASS` as a literal; replace before deploying.

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| NAS doesn't receive events | upsd not listening externally | Check `MODE=netserver` and `LISTEN 0.0.0.0 3493` |
| upsd shows only `127.0.0.1:3493` | Multiple LISTEN lines | Remove `LISTEN 127.0.0.1`, keep only `0.0.0.0` |
| `FSD OL` stuck after simulation | dummy-ups retains FSD flag | Stop nut-monitor, nut-server, nut-driver@ragtech; restart in order |
| NAS doesn't wake via WOL | WOL disabled on NAS | `sudo ethtool eth0 \| grep -i wake` — must show `Wake-on: g` |
| Server shuts down unexpectedly | Desktop power manager | Disable critical-battery-action via gsettings |

Full documentation and architecture diagrams: see `DDS.md`.
