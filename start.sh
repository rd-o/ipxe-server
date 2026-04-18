#!/bin/sh 

echo "Testing nginx config..."
nginx -t || { echo "nginx config failed!"; exit 1; }

echo "Starting nginx..."
nginx

echo "Starting dnsmasq..."
dnsmasq --no-daemon --log-dhcp
