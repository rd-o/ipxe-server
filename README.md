```
sudo ip addr add 192.168.10.1/24 dev enp70s0
sudo ip link set enp70s0 up
sudo docker stop  ipxe ; sudo docker rm ipxe
sudo docker build -t ipxe-server .
sudo docker run -d --name ipxe --network host --privileged ipxe-server

sudo docker exec -it ipxe bash
```
