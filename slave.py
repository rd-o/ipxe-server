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


def prevent_sleep():
    """Prevent monitor from sleeping and machine from powering off."""
    try:
        subprocess.run(["xset", "s", "off"], check=False)
        subprocess.run(["xset", "dpms", "0", "0", "off"], check=False)
        subprocess.run(["xset", "+dpms"], check=False)
    except Exception:
        pass


def start_ssh():
    """Start SSH server."""
    try:
        subprocess.run(["pkill", "-9", "sshd"], check=False)
        subprocess.run(["/usr/sbin/sshd"], check=False)
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
vlc_instance = None
vlc_player = None


def cleanup_vlc():
    global vlc_instance, vlc_player
    print("[CLEANUP] Stopping old VLC...")
    if vlc_player:
        try:
            vlc_player.stop()
            time.sleep(0.2)
        except:
            pass
    if vlc_instance:
        try:
            vlc_instance.release()
            time.sleep(0.2)
        except:
            pass
    vlc_instance = None
    vlc_player = None
    for _ in range(3):
        subprocess.run(['pkill', '-9', 'vlc'], check=False)
        time.sleep(0.2)
    print("[CLEANUP] Old VLC stopped")


def create_vlc(ascii_mode):
    global vlc_instance, vlc_player
    vlc_opts = ["--no-audio", "--no-video-title-show"]
    if ascii_mode:
        try:
            result = subprocess.run(["which", "cacaview"], capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                ascii_mode = False
                print("[VLC] caca not available, using fullscreen")
        except:
            ascii_mode = False
        if ascii_mode:
            vlc_opts.extend(["--vout", "caca"])
    else:
        vlc_opts.append("--fullscreen")
    vlc_instance = vlc.Instance(*vlc_opts)
    vlc_player = vlc_instance.media_player_new()
    if not ascii_mode:
        vlc_player.set_fullscreen(True)
    time.sleep(0.2)


def main():
    prevent_sleep()
    start_ssh()

    time_offset = 0.0
    loop_count = 1
    current_loop = 0
    last_reset_trigger = 0
    video_url = None
    playback_time = None
    is_webcam = False
    is_ascii = False
    start_time_global = None

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
            time_offset = server_time - time.time()
            print(f"Time offset from server: {time_offset:+.3f}s")
            break
        except Exception as e:
            print(f"Cannot connect to master, retrying...")
            time.sleep(POLL_INTERVAL)

    # 3. Poll /assign until we get the start command
    assign_url = f"{MASTER_URL}/assign"
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
                loop_count = data.get("loop", 1)
                playback_time = data.get("playback_time")
                is_webcam = data.get("is_webcam", False)
                is_ascii = data.get("is_ascii", False)
                last_reset_trigger = data.get("reset_trigger", 0)
                server_time = data.get("server_time", time.time())
                time_offset = server_time - time.time()
                start_time_global = start_time
                print(f"Received start command: video={video_url}, start_time={start_time}, offset={time_offset:+.3f}s, loop={loop_count}, webcam={is_webcam}, ascii={is_ascii}, playback_time={playback_time}")
                current_loop = 0
                break
            else:
                time.sleep(POLL_INTERVAL)
        except requests.RequestException as e:
            print(f"Polling error: {e}, retrying in {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)

    # 4. Pre‑load video with VLC
    cleanup_vlc()
    create_vlc(is_ascii)

    def set_and_play(url, position=None):
        media = vlc_instance.media_new(url)
        vlc_player.set_media(media)
        if position is not None:
            vlc_player.set_time(int(position * 1000))
        vlc_player.play()

    # 5. Wait for the exact start time
    now = time.time() + time_offset
    delay = start_time - now
    if delay > 0:
        print(f"Waiting {delay:.3f} seconds until start...")
        time.sleep(delay)
        while (time.time() + time_offset) < start_time:
            pass
    else:
        print(f"Warning: start_time is in the past (by {-delay:.3f}s). Starting immediately.")

    # 6. Start playback
    print("Playback started!")
    set_and_play(video_url)
    current_loop += 1

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
                    new_loop_count = data.get("loop")
                    new_reset_trigger = data.get("reset_trigger", 0)
                    server_time = data.get("server_time", time.time())
                    time_offset = server_time - time.time()

                    if new_reset_trigger != last_reset_trigger:
                        print(f"New client connected, resetting playback...")
                        cleanup_vlc()
                        video_url = new_video_url
                        start_time = new_start_time
                        loop_count = new_loop_count
                        is_ascii = data.get("is_ascii", False)
                        is_webcam = data.get("is_webcam", False)
                        current_loop = 0
                        last_reset_trigger = new_reset_trigger
                        create_vlc(is_ascii)
                        set_and_play(video_url)
                        current_loop += 1

                    if new_video_url != video_url or (is_ascii != data.get("is_ascii", False)):
                        print(f"New command received: video={new_video_url}, start_time={new_start_time}, ascii={data.get('is_ascii', False)}")
                        cleanup_vlc()
                        video_url = new_video_url
                        start_time = new_start_time
                        loop_count = new_loop_count
                        is_ascii = data.get("is_ascii", False)
                        is_webcam = data.get("is_webcam", False)
                        current_loop = 0
                        create_vlc(is_ascii)
                        set_and_play(video_url)
                        current_loop += 1
                    elif new_start_time != start_time:
                        start_time = new_start_time
                        now = time.time() + time_offset
                        delay = start_time - now
                        if delay > 0:
                            time.sleep(delay)
                            while (time.time() + time_offset) < start_time:
                                pass
                        vlc_player.play()
                        current_loop += 1
            except requests.RequestException:
                pass

            state = vlc_player.get_state()
            if is_webcam and playback_time:
                elapsed = time.time() - start_time_global
                if elapsed >= playback_time * 60:
                    print(f"Webcam playback time ({playback_time} min) reached, requesting next video...")
                    try:
                        resp = requests.post(f"{MASTER_URL}/finished", json={"mac": mac}, timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            video_url = data["video_url"]
                            start_time = data["start_time"]
                            loop_count = data.get("loop", 1)
                            playback_time = data.get("playback_time")
                            is_webcam = data.get("is_webcam", False)
                            last_reset_trigger = data.get("reset_trigger", 0)
                            current_loop = 0
                            start_time_global = start_time
                            print(f"Next video: {video_url}, loop={loop_count}, webcam={is_webcam}")
                            cleanup_vlc()
                            create_vlc(is_ascii)
                            set_and_play(video_url)
                            current_loop += 1
                    except:
                        print(f"No more videos, stopping.")

            if state in (vlc.State.Stopped, vlc.State.Error, vlc.State.Ended):
                if not is_webcam:
                    if loop_count == 0 or current_loop < loop_count:
                        print(f"Playback ended, looping (loop {current_loop}{'/' + str(loop_count) if loop_count else ''})...")
                        cleanup_vlc()
                        create_vlc(is_ascii)
                        set_and_play(video_url)
                        current_loop += 1
                    else:
                        print(f"Loops finished, requesting next video...")
                        try:
                            resp = requests.post(f"{MASTER_URL}/finished", json={"mac": mac}, timeout=5)
                            if resp.status_code == 200:
                                data = resp.json()
                                video_url = data["video_url"]
                                start_time = data["start_time"]
                                loop_count = data.get("loop", 1)
                                playback_time = data.get("playback_time")
                                is_webcam = data.get("is_webcam", False)
                                last_reset_trigger = data.get("reset_trigger", 0)
                                current_loop = 0
                                start_time_global = start_time
                                print(f"Next video: {video_url}, loop={loop_count}, webcam={is_webcam}")
                                cleanup_vlc()
                                create_vlc(is_ascii)
                                set_and_play(video_url)
                                current_loop += 1
                        except:
                            print(f"No more videos, stopping.")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("Interrupted, stopping playback.")
        vlc_player.stop()

if __name__ == "__main__":
    main()