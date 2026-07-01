"""
CS Fitness — Samsung TV Connection Tester
Run from Terminal:  python3 tv_test.py

Tests connectivity to the gym TV and lets you send commands interactively.
"""

import socket
import subprocess
import sys
import time

TV_IP   = "192.168.3.132"
TV_PORT = 8002
TV_MAC  = ""   # Set this to the TV's MAC address to enable Wake-on-LAN e.g. "A4:2B:8C:1D:3E:F5"


def check_ping():
    print(f"  Pinging {TV_IP}...", end=" ", flush=True)
    # Cross-platform ping: Windows uses -n/-w, macOS/Linux uses -c/-W
    if sys.platform == "win32":
        args = ["ping", "-n", "1", "-w", "2000", TV_IP]
    else:
        args = ["ping", "-c", "1", "-W", "2000", TV_IP]
    result = subprocess.run(args, capture_output=True)
    if result.returncode == 0:
        print("OK — TV is reachable on the network")
        return True
    else:
        print("FAILED — TV not reachable. Is it powered on / in standby?")
        return False


def check_port():
    print(f"  Checking port {TV_PORT}...", end=" ", flush=True)
    try:
        s = socket.create_connection((TV_IP, TV_PORT), timeout=3)
        s.close()
        print("OK — Samsung API port is open")
        return True
    except Exception as e:
        print(f"FAILED — {e}")
        print("  (TV may be fully off, not in standby. Enable Quick Start+ in TV settings.)")
        return False


def get_tv():
    try:
        from samsungtvws import SamsungTVWS
        return SamsungTVWS(host=TV_IP, port=TV_PORT, timeout=5)
    except ImportError:
        print("\nERROR: samsungtvws not installed.")
        print("Run:  pip3 install samsungtvws")
        sys.exit(1)


def send_key(key):
    try:
        tv = get_tv()
        tv.send_key(key)
        time.sleep(0.5)
        tv.close()
        print(f"  Sent: {key}")
    except Exception as e:
        print(f"  Failed to send {key}: {e}")


def wake_on_lan():
    if not TV_MAC:
        print("  TV_MAC not set in tv_test.py — edit the file and add the MAC address.")
        print("  Find it on the TV: Settings > General > Network > Network Status > MAC Address")
        return
    try:
        from wakeonlan import send_magic_packet
        send_magic_packet(TV_MAC)
        print(f"  WoL magic packet sent to {TV_MAC}")
    except ImportError:
        print("  wakeonlan not installed. Run:  pip3 install wakeonlan")


def interactive_menu():
    print("\n  Commands:")
    print("  [1] Power toggle (on←→off via Samsung API — TV must be in standby)")
    print("  [2] Wake-on-LAN  (turn on from fully off — requires MAC address set)")
    print("  [3] Volume up")
    print("  [4] Volume down")
    print("  [5] Mute")
    print("  [6] HOME key (opens TV menu)")
    print("  [7] Send custom key")
    print("  [q] Quit")

    while True:
        choice = input("\n  > ").strip().lower()
        if   choice == "1": send_key("KEY_POWER")
        elif choice == "2": wake_on_lan()
        elif choice == "3": send_key("KEY_VOLUP")
        elif choice == "4": send_key("KEY_VOLDOWN")
        elif choice == "5": send_key("KEY_MUTE")
        elif choice == "6": send_key("KEY_HOME")
        elif choice == "7":
            k = input("  Key name (e.g. KEY_POWER): ").strip()
            if k: send_key(k)
        elif choice == "q":
            print("  Done.")
            break
        else:
            print("  Unknown option.")


def main():
    print()
    print("CS FITNESS — TV CONNECTION TEST")
    print("================================")
    print(f"  TV IP:   {TV_IP}")
    print(f"  TV Port: {TV_PORT}")
    print()

    reachable = check_ping()
    if not reachable:
        print("\n  Cannot continue — TV is not on the network.")
        print("  Make sure you are on the same WiFi as the gym TV.")
        sys.exit(1)

    port_open = check_port()
    if not port_open:
        print("\n  Network OK but Samsung API port is closed.")
        print("  The TV is likely fully powered off.")
        print("  Enable Quick Start+ on the TV to keep it in standby:")
        print("    Settings > General > System Manager > Quick Start+")
        sys.exit(1)

    print("\n  TV is reachable and API port is open.")
    interactive_menu()


if __name__ == "__main__":
    main()
