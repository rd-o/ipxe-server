```
sudo docker stop  ipxe ; sudo docker rm ipxe
sudo docker build -t ipxe-server .
sudo docker run -d --name ipxe --network host --privileged ipxe-server
```
