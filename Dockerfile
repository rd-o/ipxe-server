FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    debootstrap \
    squashfs-tools \
    nginx \
    dnsmasq \
    ipxe \
    wget \
    curl \
    xz-utils \
    live-boot \
    && apt-get clean

# directories
RUN mkdir -p /srv/tftp \
    /var/www/html \
    /build/rootfs

# copy iPXE loaders
RUN cp /usr/lib/ipxe/undionly.kpxe /srv/tftp/ && \
    cp /usr/lib/ipxe/ipxe.efi /srv/tftp/

# build Debian root
RUN debootstrap bookworm /build/rootfs http://deb.debian.org/debian

# install runtime packages
RUN chroot /build/rootfs apt-get update && \
    chroot /build/rootfs apt-get install -y \
        live-boot \
        systemd-sysv \
        xorg \
        mpv \
        openbox \
        xinit \
        network-manager \
        && chroot /build/rootfs apt-get clean

# autostart video
RUN echo '#!/bin/sh\nmpv --fs http://192.168.10.1/video.mp4' > /build/rootfs/root/.xinitrc && \
    chmod +x /build/rootfs/root/.xinitrc

# autostart X
RUN echo '#!/bin/sh\nstartx' > /build/rootfs/etc/profile.d/startx.sh && \
    chmod +x /build/rootfs/etc/profile.d/startx.sh

# build squashfs
RUN mksquashfs /build/rootfs /var/www/html/rootfs.img -comp xz -e boot

RUN apt-get update && apt-get install -y libarchive-tools

RUN wget -O /tmp/live.iso \
https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-13.3.0-amd64-standard.iso

# extract full live directory
RUN mkdir /tmp/live && \
    bsdtar -xf /tmp/live.iso -C /tmp live

RUN cp /tmp/live/vmlinuz /var/www/html/ && \
    cp /tmp/live/initrd.img /var/www/html/

# iPXE script
RUN printf '#!ipxe\n\
dhcp\n\
kernel http://192.168.10.1/vmlinuz boot=live fetch=http://192.168.10.1/rootfs.img ip=dhcp toram\n\
initrd http://192.168.10.1/initrd.img\n\
boot\n\' > /var/www/html/boot.ipxe

COPY dnsmasq.conf /etc/dnsmasq.conf
COPY start.sh /start.sh

RUN chmod +x /start.sh

EXPOSE 67/udp
EXPOSE 69/udp
EXPOSE 80

CMD ["/start.sh"]
