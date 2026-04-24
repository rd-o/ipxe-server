#!/bin/bash -x 
sudo docker build -t master-server .
sudo docker stop master ; sudo docker rm master
#sudo docker run -d --name master --network host --privileged -v ./videos:/app/videos:ro master-server 
sudo docker run -v /dev:/dev -d --name master --network host --privileged -v ./videos:/app/videos:ro master-server 
