# iPXE Video Server

Synchronized video playback across multiple QEMU virtual machines using iPXE network boot.

## Architecture

- **Server**: Docker container running DHCP, TFTP, HTTP, and master coordination server
- **Clients**: iPXE-booted VMs that run slave.py to receive synchronized playback commands
- **Video**: Three synchronized video streams (left, center, right)

### MAC Address Mapping

| MAC Address       | Role   |
|-------------------|--------|
| 52:54:00:12:34:50 | left   |
| 52:54:00:12:34:51 | center |
| 52:54:00:12:34:52 | right  |

## Prerequisites

- Docker
- QEMU with KVM support
- Root access (for network/tap devices)

## Setup

### 1. Create TAP Interfaces

Run once after reboot:

```bash
./set_tap.sh
```

Creates tap0, tap1, tap2 for the three VMs.

### 2. Build and Run Server

```bash
sudo ./build.sh
```

This will:
- Build the Docker image `ipxe-server`
- Stop and remove any existing container named `ipxe`
- Start the container in host network mode

### 3. Start Master Server

In a separate terminal:

```bash
python3 master.py
```

## Videos Organization

Place video sets in the `videos/` directory. Each set should be a subdirectory named with a number (e.g., `001/`).

```
videos/
├── 001/
│   ├── left.mp4
│   ├── center.mp4
│   └── right.mp4
├── 002/
│   ├── left.mp4
│   ├── center.mp4
│   └── right.mp4
└── 003/
    ├── left.mp4
    ├── center.mp4
    └── right.mp4
```

### Quick Setup for Testing

Symlink the same video to all three positions:

```bash
mkdir -p videos/001
cd videos/001
ln -s ../video.mp4 left.mp4
ln -s ../video.mp4 center.mp4
ln -s ../video.mp4 right.mp4
```

## Start QEMU Clients

After the server is running, start the VMs:

```bash
./start_qemu_clients.sh
```

This launches three QEMU VMs with KVM acceleration, each connected to a different TAP interface.

Alternatively, start a single VM manually:

```bash
sudo qemu-system-x86_64 -enable-kvm -m 2G \
    -netdev tap,id=net0,ifname=tap0,script=no,downscript=no \
    -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:50
```

## Trigger Video Playback

### Check Client Status

```bash
curl http://localhost:8000/status
```

### Start a Video Set

```bash
curl -X POST http://localhost:8000/start -H "Content-Type: application/json" -d '{"set": "001"}'
```

The master server will:
1. Verify all three clients are registered
2. Schedule playback to start in 5 seconds
3. Notify all clients of the exact start timestamp

## API Endpoints

| Endpoint    | Method | Description                          |
|-------------|--------|--------------------------------------|
| `/register` | POST   | Client registration (JSON: `{"mac": "..."}`) |
| `/assign`   | GET    | Client polls for video URL and start time |
| `/start`    | POST   | Trigger playback (JSON: `{"set": "001"}`)   |
| `/status`   | GET    | View registered clients and state           |

## Files

- `Dockerfile` - Container image definition
- `build.sh` - Build and run script
- `master.py` - Coordination server (Flask)
- `slave.py` - Client script (runs on VMs)
- `rc.lua` - AwesomeWM configuration with autostart
- `set_tap.sh` - Create TAP interfaces
- `start_qemu_clients.sh` - Launch all test VMs
- `dnsmasq.conf` - DHCP/TFTP configuration
- `mac_stream.conf` - MAC addresses for streaming (legacy)

## Troubleshooting

### VMs can't boot from network
- Check `sudo systemctl status dnsmasq` inside container
- Verify TAP interfaces exist: `ip link show tap*`

### Clients not registering
- Ensure VMs have network connectivity: `ping 192.168.10.1`
- Check master.py is running without errors

### Video not playing
- Verify video files exist: `ls -la videos/001/`
- Check VLC is installed in the VM rootfs
- Look for errors in the xterm terminal window
