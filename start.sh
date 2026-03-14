#!/bin/sh

echo "Starting nginx..."
service nginx start

echo "Starting dnsmasq..."
dnsmasq --no-daemon --log-dhcp
