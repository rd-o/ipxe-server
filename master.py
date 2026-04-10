#!/usr/bin/env python3
"""
Synchronised video master server.
Serves video files and coordinates start time for three clients.
"""

import os
import time
import json
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
VIDEO_ROOT = "./videos"          # directory containing 001/, 002/, ...
MAC_TO_ROLE = {
    "52:54:00:12:34:50": "left",
    "52:54:00:12:34:51": "center",
    "52:54:00:12:34:52": "right",
}
START_DELAY = 5.0                # seconds from /start command to actual playback

# ----------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------
registered_clients = {}    # mac -> {"role": str, "registered_at": float}
selected_set = None        # e.g. "001"
start_time = None          # absolute Unix timestamp when playback should begin

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_client_ip():
    """Return client IP address (for logging)."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For']
    return request.remote_addr

# ----------------------------------------------------------------------
# API endpoints
# ----------------------------------------------------------------------
@app.route('/register', methods=['POST'])
def register():
    """
    Register a client by its MAC address.
    Expects JSON: {"mac": "xx:xx:xx:xx:xx:xx"}
    """
    data = request.get_json()
    if not data or 'mac' not in data:
        return jsonify({"error": "Missing 'mac' field"}), 400

    mac = data['mac'].strip().lower()
    if mac not in MAC_TO_ROLE:
        return jsonify({"error": f"Unknown MAC address {mac}"}), 403

    role = MAC_TO_ROLE[mac]
    registered_clients[mac] = {
        "role": role,
        "registered_at": time.time(),
        "ip": get_client_ip()
    }
    print(f"[REGISTER] {mac} -> {role} from {get_client_ip()}")
    return jsonify({"status": "registered", "role": role}), 200


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

    if mac not in MAC_TO_ROLE:
        return jsonify({"error": "Unknown MAC"}), 403

    if start_time is None or selected_set is None:
        return jsonify({"status": "waiting"}), 200

    role = MAC_TO_ROLE[mac]
    video_url = f"http://{request.host}/videos/{selected_set}/{role}.mp4"
    return jsonify({
        "status": "ready",
        "video_url": video_url,
        "start_time": start_time,
        "set": selected_set
    }), 200


@app.route('/start', methods=['POST'])
def start_playback():
    """
    Admin endpoint to trigger the synchronised start.
    Expects JSON: {"set": "001"}
    """
    global selected_set, start_time
    data = request.get_json()
    if not data or 'set' not in data:
        return jsonify({"error": "Missing 'set' field"}), 400

    set_num = data['set'].strip()
    # Validate that the set directory exists
    set_path = os.path.join(VIDEO_ROOT, set_num)
    if not os.path.isdir(set_path):
        return jsonify({"error": f"Set directory {set_num} not found"}), 404

    # Require all three clients to be registered
    expected_macs = set(MAC_TO_ROLE.keys())
    registered_macs = set(registered_clients.keys())
    if not expected_macs.issubset(registered_macs):
        missing = expected_macs - registered_macs
        return jsonify({"error": f"Clients not registered: {missing}"}), 400

    selected_set = set_num
    start_time = time.time() + START_DELAY
    print(f"[START] Set {selected_set} will play at {start_time} "
          f"(in {START_DELAY} seconds)")

    return jsonify({
        "status": "start scheduled",
        "set": selected_set,
        "start_time": start_time
    }), 200


@app.route('/status', methods=['GET'])
def status():
    """Return current registration and start state."""
    return jsonify({
        "registered_clients": registered_clients,
        "selected_set": selected_set,
        "start_time": start_time,
        "start_delay": START_DELAY
    })


# ----------------------------------------------------------------------
# Video file serving
# ----------------------------------------------------------------------
@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Serve video files from VIDEO_ROOT."""
    return send_from_directory(VIDEO_ROOT, filename)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == '__main__':
    # Create video root if it doesn't exist
    os.makedirs(VIDEO_ROOT, exist_ok=True)
    print("Master server starting...")
    print("Expected MAC -> role mapping:")
    for mac, role in MAC_TO_ROLE.items():
        print(f"  {mac} -> {role}")
    print("\nAdmin endpoints:")
    print("  POST /start   (JSON: {\"set\": \"001\"})")
    print("  GET  /status")
    print("\nServing videos from:", os.path.abspath(VIDEO_ROOT))
    app.run(host='0.0.0.0', port=8000, debug=False)