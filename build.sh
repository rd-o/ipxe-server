#!/bin/bash -x
sudo docker build -t ipxe-server .
#sudo docker run -d --name ipxe --network host --privileged -v $(pwd)/videos/video.mp4:/var/www/html/video.mp4 ipxe-server
sudo docker stop  ipxe ; sudo docker rm ipxe
sudo docker run -d --name ipxe --network host --privileged -v $(pwd)/videos/008/video.mp4:/var/www/html/video.mp4 ipxe-server


