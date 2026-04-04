# Config

```
sudo ip addr add 192.168.10.1/24 dev enp70s0
sudo ip link set enp70s0 up
sudo docker stop  ipxe ; sudo docker rm ipxe
sudo docker build -t ipxe-server .
sudo docker run -d --name ipxe --network host --privileged ipxe-server

sudo docker exec -it ipxe bash
```

# Config qemu client
```
sudo ip tuntap add tap0 mode tap
sudo ip addr add 192.168.10.1/24 dev tap0
sudo ip link set tap0 up



qemu-system-x86_64 -boot order=n -netdev tap,id=net0,ifname=tap0,script=no,downscript=no -device e1000,netdev=net0,mac=52:54:00:12:34:56 -m 2G
```


# remove IP
```
sudo ip addr del 192.168.10.1/24 dev enp70s0
```
