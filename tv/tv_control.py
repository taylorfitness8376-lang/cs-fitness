"""
CS Fitness — Samsung TV Control
Turns the gym TV on or off over the local network.

Usage:
  python tv_control.py on
  python tv_control.py off

Requirements:
  pip install samsungtvws

IMPORTANT: The TV must have "Quick Start+" (or "Instant On") enabled in its
settings so it stays on standby when "off". Without this, the TV loses its
network connection when powered off and cannot be woken remotely.

Settings > General > Network > Expert Settings > Power On with Mobile  (enable)
Settings > General > System Manager > Time > Clock > Auto               (enable)
"""

import sys
import time

TV_IP  = "192.168.3.132"
TV_PORT = 8002
TV_MAC  = ""   # Set to TV's MAC address to use Wake-on-LAN for tv_on e.g. "A4:2B:8C:1D:3E:F5"
               # Find it: TV Settings > General > Network > Network Status > MAC Address


def get_tv():
    try:
        from samsungtvws import SamsungTVWS
        return SamsungTVWS(host=TV_IP, port=TV_PORT, timeout=5)
    except ImportError:
        print("ERROR: samsungtvws not installed.")
        print("Run:  pip install samsungtvws")
        sys.exit(1)


def tv_on():
    print(f"Turning TV ON ({TV_IP})...")
    # Prefer Wake-on-LAN when a MAC address is configured (works even if fully off)
    if TV_MAC:
        try:
            from wakeonlan import send_magic_packet
            send_magic_packet(TV_MAC)
            print(f"  Wake-on-LAN sent to {TV_MAC}")
            return
        except ImportError:
            print("  wakeonlan not installed — falling back to Samsung API key.")
    # Fallback: Samsung API power key (requires TV in standby / Quick Start+)
    try:
        tv = get_tv()
        tv.send_key("KEY_POWER")
        print("  Power key sent.")
        time.sleep(2)
        tv.close()
    except Exception as e:
        print(f"  Could not reach TV: {e}")
        print("  Set TV_MAC in tv_control.py for more reliable wake, or enable Quick Start+.")


def tv_off():
    print(f"Turning TV OFF ({TV_IP})...")
    try:
        tv = get_tv()
        tv.send_key("KEY_POWER")
        print("  Power key sent.")
        time.sleep(2)
        tv.close()
    except Exception as e:
        print(f"  Could not reach TV: {e}")
        print("  Is the TV already off, or not on the same network?")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("on", "off"):
        print("Usage: python tv_control.py on|off")
        sys.exit(1)
    if sys.argv[1] == "on":
        tv_on()
    else:
        tv_off()
