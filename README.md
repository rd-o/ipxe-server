docker run -d --name ipxe --network host --cap-add NET_ADMIN --cap-add NET_RAW -v $(pwd)/tftp:/srv/tftp -v $(pwd)/www:/var/www/html ipxe-server
