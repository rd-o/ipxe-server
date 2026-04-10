#!/bin/bash -x
# setup_br0_taps.sh – Bridge with IP 192.168.10.1 + 3 tap interfaces using brctl
# Run as root (sudo)

#set -e

BRIDGE="br0"
BRIDGE_IP="192.168.10.1/24"
TAP_PREFIX="tap"
NUM_TAPS=3

# Install bridge-utils if not present
#if ! command -v brctl &> /dev/null; then
#    echo "brctl not found. Installing bridge-utils..."
#    apt-get update && apt-get install -y bridge-utils
#fi

# Remove any existing bridge with same name (clean slate)
ip link delete "$BRIDGE" 2>/dev/null || true

# Create bridge using brctl
#brctl addbr "$BRIDGE"
#ip addr add "$BRIDGE_IP" dev "$BRIDGE"
#ip link set "$BRIDGE" up
ip link add name $BRIDGE type bridge
ip link set dev $BRIDGE up
ip address add $BRIDGE_IP dev br0

# Enable IP forwarding (optional, but safe)
#sysctl -w net.ipv4.ip_forward=1

# Load the bridge module if not already loaded
#modprobe bridge 2>/dev/null || true

# Create taps and attach to bridge
for i in $(seq 0 $((NUM_TAPS - 1))); do
    TAP="${TAP_PREFIX}${i}"
    ip tuntap add "$TAP" mode tap
    ip link set "$TAP" up
    #brctl addif "$BRIDGE" "$TAP"
    ip link set "$TAP" master br0
done

# Show result
echo "Bridge $BRIDGE with IP $(ip -4 addr show $BRIDGE | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+')"
brctl show "$BRIDGE"
echo "Taps created: $(ls /sys/class/net/ | grep '^tap[0-2]')"

echo "=========================================="
echo "Now run your Docker container with:"
echo "  docker run --network host ..."
echo "Inside the container, 192.168.10.1 is available on the host's br0."
echo "Start QEMU clients with:"
echo "  qemu-system-x86_64 ... -netdev tap,id=net0,ifname=tap0,script=no,downscript=no -device virtio-net-pci,netdev=net0"
echo "  (repeat for tap1, tap2)"
echo "Ensure your DHCP server (running in the container) gives addresses in 192.168.10.100-200."
echo "=========================================="
