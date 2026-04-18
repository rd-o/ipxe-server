#!/usr/bin/env python3
"""
Synchronised video slave client.
Registers with master using its MAC address, waits for start command,
and plays the assigned video at the given absolute start time.
"""

import sys
import time
import uuid
import subprocess
import requests
import vlc

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
MASTER_URL = "http://192.168.10.1:8000"   # CHANGE THIS
POLL_INTERVAL = 0.5                       # seconds between /assign requests

time_offset = 0.0


def prevent_sleep():
    """Prevent monitor from sleeping and machine from powering off."""
    try:
        subprocess.run(["xset", "s", "off"], check=False)
        subprocess.run(["xset", "dpms", "0", "0", "off"], check=False)
        subprocess.run(["xset", "+dpms"], check=False)
    except Exception:
        pass

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
    prevent_sleep()

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
            server_time = data.get("server_time", time.time())
            global time_offset
            time_offset = server_time - time.time()
            print(f"Time offset from server: {time_offset:+.3f}s")
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
                server_time = data.get("server_time", time.time())
                time_offset = server_time - time.time()
                print(f"Received start command: video={video_url}, start_time={start_time}, offset={time_offset:+.3f}s")
                break
            else:
                # Still waiting
                time.sleep(POLL_INTERVAL)
        except requests.RequestException as e:
            print(f"Polling error: {e}, retrying in {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)

    # 4. Pre‑load video with VLC
    instance = vlc.Instance("--no-audio", "--fullscreen", "--loop")
    player = instance.media_player_new()
    media = instance.media_new(video_url)
    player.set_media(media)
    player.set_fullscreen(True)

    # 5. Wait for the exact start time
    now = time.time() + time_offset
    delay = start_time - now
    if delay > 0:
        print(f"Waiting {delay:.3f} seconds until start...")
        time.sleep(delay)
        # Small busy loop to compensate for sleep imprecision
        while (time.time() + time_offset) < start_time:
            pass
    else:
        print(f"Warning: start_time is in the past (by {-delay:.3f}s). Starting immediately.")

    # 6. Start playback
    print("Playback started!")
    player.play()

    # 7. Keep looping video and poll for new commands
    try:
        while True:
            try:
                resp = requests.get(assign_url, params={"mac": mac}, timeout=2)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "ready":
                    new_video_url = data["video_url"]
                    new_start_time = data["start_time"]
                    server_time = data.get("server_time", time.time())
                    time_offset = server_time - time.time()
                    if new_video_url != video_url:
                        print(f"New command received: video={new_video_url}, start_time={new_start_time}")
                        video_url = new_video_url
                        start_time = new_start_time
                        media = instance.media_new(video_url)
                        player.set_media(media)
                        player.play()
                    elif new_start_time != start_time:
                        video_url = new_video_url
                        start_time = new_start_time
                        now = time.time() + time_offset
                        delay = start_time - now
                        if delay > 0:
                            time.sleep(delay)
                            while (time.time() + time_offset) < start_time:
                                pass
                        player.play()
            except requests.RequestException:
                pass

            state = player.get_state()
            if state in (vlc.State.Stopped, vlc.State.Error, vlc.State.Ended):
                print("Playback stopped/error/ended, restarting...")
                player.play()

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("Interrupted, stopping playback.")
        player.stop()

if __name__ == "__main__":
    main()
