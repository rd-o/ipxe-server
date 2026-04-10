#!/usr/bin/env python3
"""
Synchronised video slave client.
Registers with master using its MAC address, waits for start command,
and plays the assigned video at the given absolute start time.
"""

import sys
import time
import uuid
import requests
import vlc

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
MASTER_URL = "http://192.168.10.1:8000"   # CHANGE THIS
POLL_INTERVAL = 0.5                       # seconds between /assign requests

# ----------------------------------------------------------------------
# Helper: get MAC address
# ----------------------------------------------------------------------
def get_mac_address():
    """Return MAC address as lowercase colon-separated hex string."""
    mac_num = uuid.getnode()
    mac_hex = ':'.join(f'{(mac_num >> (i*8)) & 0xff:02x}'
                       for i in reversed(range(6)))
    return mac_hex

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # 1. Obtain MAC address
    mac = get_mac_address()
    print(f"Local MAC address: {mac}")

    # 2. Register with master
    register_url = f"{MASTER_URL}/register"
    while True:
        try:
            resp = requests.post(register_url, json={"mac": mac}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            print(f"Registered as role: {data['role']}")
            break
        except Exception as e:
            print(f"Cannot connect to master, retrying...")
            time.sleep(POLL_INTERVAL)

    # 3. Poll /assign until we get the start command
    assign_url = f"{MASTER_URL}/assign"
    video_url = None
    start_time = None
    print("Waiting for master to schedule start...")
    while True:
        try:
            resp = requests.get(assign_url, params={"mac": mac}, timeout=2)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ready":
                video_url = data["video_url"]
                start_time = data["start_time"]
                print(f"Received start command: video={video_url}, start_time={start_time}")
                break
            else:
                # Still waiting
                time.sleep(POLL_INTERVAL)
        except requests.RequestException as e:
            print(f"Polling error: {e}, retrying in {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)

    # 4. Pre‑load video with VLC
    instance = vlc.Instance("--no-audio", "--fullscreen")
    player = instance.media_player_new()
    media = instance.media_new(video_url)
    player.set_media(media)
    player.set_fullscreen(True)

    # 5. Wait for the exact start time
    now = time.time()
    delay = start_time - now
    if delay > 0:
        print(f"Waiting {delay:.3f} seconds until start...")
        time.sleep(delay)
        # Small busy loop to compensate for sleep imprecision
        while time.time() < start_time:
            pass
    else:
        print(f"Warning: start_time is in the past (by {-delay:.3f}s). Starting immediately.")

    # 6. Start playback
    print("Playback started!")
    player.play()

    # 7. Keep script alive (wait for video end or Ctrl+C)
    try:
        while True:
            state = player.get_state()
            if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                print("Playback finished.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted, stopping playback.")
        player.stop()

if __name__ == "__main__":
    main()
