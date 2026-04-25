#!/usr/bin/env python3
"""
Synchronised video master server.
Serves video files and coordinates start time for three clients.
"""

import os
import time
import json
import subprocess
import threading
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
VIDEO_ROOT = "./videos"          # directory containing 001/, 002/, ...
ROLE_ORDER = ["left", "center", "right"]
START_DELAY = 5.0                # seconds from /start command to actual playback

# ----------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------
registered_clients = {}    # mac -> {"role": str, "registered_at": float}
current_set = None         # e.g. "001"
next_set = "001"         # next set to play after current finishes
start_time = None          # absolute Unix timestamp when playback should begin
loop_count = 1            # loop value from rules.conf (default: 1)
reset_trigger = 0          # increments when we need to reset clients
webcam_enabled = False     # webcam stream enabled
playback_time = None       # playback time in minutes
webcam_device = None       # detected webcam device
ascii_enabled = False      # ASCII art mode
split_enabled = False      # Split video mode (gst-launch)
_start_called = False      # Tracks if /start was explicitly called

ASCII_CHARS = "@#S%?*+;:,. "

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_client_ip():
    """Return client IP address (for logging)."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For']
    return request.remote_addr


def load_rules(set_num):
    """Load rules from videos/<set_num>/rules.conf."""
    global loop_count, webcam_enabled, playback_time, ascii_enabled, split_enabled
    rules_file = os.path.join(VIDEO_ROOT, set_num, "rules.conf")
    webcam_enabled = False
    playback_time = None
    ascii_enabled = False
    split_enabled = False
    try:
        with open(rules_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('LOOP='):
                    loop_count = int(line.split('=', 1)[1])
                elif line.startswith('WEBCAM='):
                    webcam_enabled = int(line.split('=', 1)[1]) == 1
                elif line.startswith('PLAYBACK_TIME='):
                    playback_time = int(line.split('=', 1)[1])
                elif line.startswith('AA='):
                    ascii_enabled = int(line.split('=', 1)[1]) == 1
                elif line.startswith('SPLIT='):
                    split_enabled = int(line.split('=', 1)[1]) == 1
    except FileNotFoundError:
        loop_count = 1
    import sys
    print(f"[DEBUG load_rules] set={set_num}, webcam={webcam_enabled}, ascii={ascii_enabled}", flush=True)


def detect_webcam():
    """Detect available webcam. Returns the last openable device or None."""
    global webcam_device
    print("[DEBUG] detect_webcam called, webcam_enabled=", webcam_enabled)
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.split('\n'):
            if '/dev/video' in line:
                devices.append(line.strip())
        print(f"[DEBUG] Found devices: {devices}")
        for device in reversed(devices):
            print(f"[DEBUG] Trying device: {device}")
            try:
                cap = cv2.VideoCapture(device)
                if cap.isOpened():
                    cap.release()
                    webcam_device = device
                    print(f"[DEBUG] Selected device: {webcam_device}")
                    return webcam_device
                else:
                    cap.release()
            except Exception as e:
                print(f"[DEBUG] Failed to open {device}: {e}")
    except Exception as e:
        print(f"Webcam detection failed: {e}")
    print("[DEBUG] No webcam found")
    return None


def get_next_set(current):
    """Get next set number in order."""
    try:
        sets = sorted([d for d in os.listdir(VIDEO_ROOT) if os.path.isdir(os.path.join(VIDEO_ROOT, d))])
        idx = sets.index(current) if current in sets else -1
        next_idx = (idx + 1) % len(sets)
        return sets[next_idx]
    except:
        return "001"


def reset_playback():
    """Reset playback state to trigger restart for all clients."""
    global start_time, reset_trigger, current_set, next_set
    if current_set is None:
        current_set = "001"
    load_rules(current_set)
    next_set = get_next_set(current_set)
    if not _start_called:
        start_time = time.time() + 2.0
        reset_trigger += 1
    print(f"[RESET] Playback reset for new client, will start in 2s, loop={loop_count}, next={next_set}")


# ----------------------------------------------------------------------
# API endpoints
# ----------------------------------------------------------------------
@app.route('/register', methods=['POST'])
def register():
    """
    Register a client by its MAC address.
    Expects JSON: {"mac": "xx:xx:xx:xx:xx:xx"}
    Role is assigned deterministically from MAC hash.
    """
    data = request.get_json()
    if not data or 'mac' not in data:
        return jsonify({"error": "Missing 'mac' field"}), 400

    mac = data['mac'].strip().lower()

    if mac in registered_clients:
        role = registered_clients[mac]["role"]
        print(f"[RE-REGISTER] {mac} -> {role} from {get_client_ip()}")
        return jsonify({"status": "registered", "role": role, "server_time": time.time(), "reset_trigger": reset_trigger}), 200

    role = ROLE_ORDER[len(registered_clients) % len(ROLE_ORDER)]
    registered_clients[mac] = {
        "role": role,
        "registered_at": time.time(),
        "ip": get_client_ip()
    }
    print(f"[REGISTER] {mac} -> {role} from {get_client_ip()}")
    reset_playback()
    return jsonify({"status": "registered", "role": role, "server_time": time.time(), "reset_trigger": reset_trigger}), 200


@app.route('/assign', methods=['GET'])
def assign():
    """
    Client polls this endpoint to obtain the video URL and start time.
    Query parameter: ?mac=xx:xx:xx:xx:xx:xx
    Returns:
        - If start is not ready: {"status": "waiting"}
        - If ready: {"video_url": "...", "start_time": 123456.789, "set": "001"}
    """
    mac = request.args.get('mac')
    if not mac:
        return jsonify({"error": "Missing 'mac' parameter"}), 400
    mac = mac.strip().lower()

    if mac not in registered_clients:
        return jsonify({"error": "Not registered"}), 403

    if start_time is None or current_set is None:
        import sys
        print(f"[DEBUG assign] waiting: start_time={start_time}, current_set={current_set}", flush=True)
        return jsonify({"status": "waiting"}), 200

    if time.time() > start_time + 10:
        import sys
        print(f"[DEBUG assign] waiting: start_time expired", flush=True)
        return jsonify({"status": "waiting"}), 200

    role = registered_clients[mac]["role"]
    print(f"[DEBUG assign] split={split_enabled}, webcam={webcam_enabled}, ascii={ascii_enabled}")

    if split_enabled:
        video_path = os.path.join(VIDEO_ROOT, current_set, "video.mp4")
        reset_split(video_path)
        video_url = f"http://{request.host}/client"
    elif webcam_enabled and ascii_enabled:
        video_url = f"http://{request.host}/ascii"
        print(f"[DEBUG assign] Using /ascii URL: {video_url}")
    elif webcam_enabled:
        video_url = f"http://{request.host}/webcam"
    else:
        video_url = f"http://{request.host}/videos/{current_set}/{role}.mp4"

    return jsonify({
        "status": "ready",
        "video_url": video_url,
        "start_time": start_time,
        "set": current_set,
        "loop": loop_count,
        "playback_time": playback_time,
        "is_webcam": webcam_enabled,
        "is_ascii": ascii_enabled,
        "is_split": split_enabled,
        "reset_trigger": reset_trigger,
        "server_time": time.time()
    }), 200


@app.route('/start', methods=['POST'])
def start_playback():
    """
    Admin endpoint to trigger the synchronised start.
    Expects JSON: {"set": "001"}
    """
    global current_set, start_time
    data = request.get_json()
    if not data or 'set' not in data:
        return jsonify({"error": "Missing 'set' field"}), 400

    set_num = data['set'].strip()
    set_path = os.path.join(VIDEO_ROOT, set_num)
    if not os.path.isdir(set_path):
        return jsonify({"error": f"Set directory {set_num} not found"}), 404

    load_rules(set_num)

    print(f"[START] Set {set_num}: SPLIT={split_enabled}, WEBCAM={webcam_enabled}")
    global _start_called
    _start_called = True
    current_set = set_num
    next_set = get_next_set(current_set)
    start_time = time.time() + START_DELAY
    if not webcam_enabled:
        close_webcam()
    if split_enabled:
        video_path = os.path.join(VIDEO_ROOT, current_set, "video.mp4")
        print(f"[SPLIT] Starting with video path: {video_path}")
        start_split(video_path)
    else:
        print(f"[START] stop_split() called - split_enabled is: {split_enabled}")
        stop_split()
    print(f"[START] Set {current_set} will play"
          f"(in {START_DELAY} seconds), loop={loop_count}, next={next_set}")

    return jsonify({
        "status": "start scheduled",
        "set": current_set,
        "start_time": start_time,
        "loop": loop_count
    }), 200


@app.route('/finished', methods=['POST'])
def playback_finished():
    """
    Called by slave when video loop finishes.
    Returns next video URL in order.
    """
    global current_set, start_time, reset_trigger
    current_set = get_next_set(current_set)
    load_rules(current_set)
    start_time = time.time() + START_DELAY
    reset_trigger += 1

    role = "left"
    video_url = f"http://{request.host}/videos/{current_set}/{role}.mp4"

    return jsonify({
        "status": "next",
        "video_url": video_url,
        "start_time": start_time,
        "set": current_set,
        "loop": loop_count,
        "reset_trigger": reset_trigger,
        "server_time": time.time()
    }), 200


@app.route('/status', methods=['GET'])
def status():
    """Return current registration and start state."""
    return jsonify({
        "registered_clients": registered_clients,
        "current_set": current_set,
        "start_time": start_time,
        "start_delay": START_DELAY,
        "loop": loop_count,
        "reset_trigger": reset_trigger
    })


# ----------------------------------------------------------------------
# Video file serving
# ----------------------------------------------------------------------
@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Serve video files from VIDEO_ROOT."""
    return send_from_directory(VIDEO_ROOT, filename)


# ----------------------------------------------------------------------
# Webcam streaming
# ----------------------------------------------------------------------
_webcam_capture = None
_webcam_device = None
_clients_lock = threading.Lock()
_clients = []
_ascii_clients_lock = threading.Lock()
_ascii_clients = []


def close_webcam():
    """Release webcam capture and clear all client queues."""
    global _webcam_capture, _clients, _ascii_clients
    if _webcam_capture is not None:
        _webcam_capture.release()
        _webcam_capture = None
        print("[WEBCAM] Capture stopped")
    with _clients_lock:
        _clients = []
    with _ascii_clients_lock:
        _ascii_clients = []


def frame_to_ascii(frame, cols, rows):
    """Convert frame to ASCII art string."""
    small_frame = cv2.resize(frame, (cols, rows))
    gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
    indices = (gray / 255 * (len(ASCII_CHARS) - 1)).astype(int)
    lines = []
    for y in range(rows):
        line = ''.join(ASCII_CHARS[indices[y, x]] for x in range(cols))
        lines.append(line)
    return '\n'.join(lines)


def _capture_frames():
    """Background thread that captures frames and broadcasts to all clients."""
    global _webcam_capture, _webcam_device
    import sys
    print(f"[DEBUG] _capture_frames started, webcam_enabled={webcam_enabled}, ascii_enabled={ascii_enabled}", flush=True)
    consecutive_failures = 0
    while True:
        try:
            if _webcam_capture is None:
                if webcam_enabled:
                    print("[DEBUG] Attempting to open webcam...", flush=True)
                    device = detect_webcam()
                    print(f"[DEBUG] detect_webcam returned: {device}", flush=True)
                    if device is not None:
                        _webcam_capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
                        print(f"[DEBUG] VideoCapture created, isOpened={_webcam_capture.isOpened()}", flush=True)
                        if _webcam_capture.isOpened():
                            _webcam_device = device
                            print(f"[WEBCAM] Capture started on {device}", flush=True)
                            consecutive_failures = 0
                        else:
                            _webcam_capture.release()
                            _webcam_capture = None
                            print("[WEBCAM] Cannot open webcam", flush=True)
                    else:
                        print("[WEBCAM] No webcam detected", flush=True)
                else:
                    print("[DEBUG] webcam_enabled is False, skipping", flush=True)
                if _webcam_capture is None:
                    print("[DEBUG] Sleeping 0.5s, no capture device", flush=True)
                    time.sleep(0.5)
                    continue

            ret, frame = _webcam_capture.read()
            if not ret:
                consecutive_failures += 1
                print(f"[DEBUG] Frame read failed ({consecutive_failures})", flush=True)
                if consecutive_failures >= 5:
                    print("[WEBCAM] Too many failures, releasing capture", flush=True)
                    _webcam_capture.release()
                    _webcam_capture = None
                    consecutive_failures = 0
                time.sleep(0.1)
                continue
            consecutive_failures = 0

            if ascii_enabled:
                cols, rows = 160, 45
                ascii_text = frame_to_ascii(frame, cols, rows)
                with _ascii_clients_lock:
                    for client in _ascii_clients[:]:
                        try:
                            client.put(ascii_text)
                        except:
                            pass

            with _clients_lock:
                for client in _clients[:]:
                    try:
                        _, jpeg = cv2.imencode('.jpg', frame)
                        client.put(jpeg.tobytes())
                    except:
                        pass

            time.sleep(1.0 / 15.0)
        except Exception as e:
            print(f"[DEBUG] Exception in _capture_frames: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(1)


def _start_capture_thread():
    """Start the background capture thread if not already running."""
    if not hasattr(_start_capture_thread, 'started'):
        thread = threading.Thread(target=_capture_frames, daemon=True)
        thread.start()
        _start_capture_thread.started = True


@app.route('/webcam')
def webcam_stream():
    """Serve webcam MJPEG stream to a single client."""
    import queue

    _start_capture_thread()

    frame_queue = queue.Queue(maxsize=2)
    with _clients_lock:
        _clients.append(frame_queue)

    def generate():
        try:
            while True:
                try:
                    frame_bytes = frame_queue.get(timeout=5)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except queue.Empty:
                    break
        finally:
            with _clients_lock:
                try:
                    _clients.remove(frame_queue)
                except ValueError:
                    pass

    return Response(generate(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/ascii')
def ascii_stream():
    """Serve ASCII art stream to clients."""
    import queue

    _start_capture_thread()

    ascii_queue = queue.Queue(maxsize=2)
    ascii_queue.ascii_cache = ""
    with _ascii_clients_lock:
        _ascii_clients.append(ascii_queue)

    def generate():
        try:
            while True:
                try:
                    ascii_text = ascii_queue.get(timeout=5)
                    ascii_queue.ascii_cache = ascii_text
                    yield f"data: {ascii_text}\n\n"
                except queue.Empty:
                    break
        finally:
            with _ascii_clients_lock:
                try:
                    _ascii_clients.remove(ascii_queue)
                except ValueError:
                    pass

    return Response(generate(),
                   mimetype='text/event-stream')





# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
import signal
import sys

main_sh_process = None
current_split_video = None


def stop_split():
    global main_sh_process
    if main_sh_process:
        print("[SPLIT] Stopping main.sh process...")
        main_sh_process.terminate()
        main_sh_process = None


def start_split(video_path):
    global main_sh_process, current_split_video
    stop_split()
    script_path = os.path.join(os.path.dirname(__file__), 'main.sh')
    if not os.path.exists(script_path):
        print(f"[SPLIT] main.sh not found")
        return
    current_split_video = video_path
    main_sh_process = subprocess.Popen(
        [script_path, video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"[SPLIT] Started streaming {video_path}")


def reset_split(new_video_path):
    global current_split_video
    if current_split_video != new_video_path:
        start_split(new_video_path)


def signal_handler(sig, frame):
    stop_split()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == '__main__':
    os.makedirs(VIDEO_ROOT, exist_ok=True)
    reset_playback()
    print("Master server starting...")
    print("Available roles:", ", ".join(ROLE_ORDER))
    print("\nAdmin endpoints:")
    print("  POST /start   (JSON: {\"set\": \"001\"})")
    print("  GET  /status")
    print("\nServing videos from:", os.path.abspath(VIDEO_ROOT))
    app.run(host='0.0.0.0', port=8000, debug=True)
