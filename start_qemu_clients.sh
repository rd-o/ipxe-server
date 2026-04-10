sudo qemu-system-x86_64 -enable-kvm -m 2G  -netdev tap,id=net0,ifname=tap0,script=no,downscript=no -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:50 &
sudo qemu-system-x86_64 -enable-kvm -m 2G  -netdev tap,id=net0,ifname=tap1,script=no,downscript=no -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:51 &
sudo qemu-system-x86_64 -enable-kvm -m 2G  -netdev tap,id=net0,ifname=tap2,script=no,downscript=no -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:52 &
