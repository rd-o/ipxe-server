FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

# Install host tools
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
    systemd-container \
    && apt-get clean

# Prepare directories
RUN mkdir -p /srv/tftp /var/www/html /build/rootfs

# Copy iPXE loaders
RUN cp /usr/lib/ipxe/undionly.kpxe /srv/tftp/ && \
    cp /usr/lib/ipxe/ipxe.efi /srv/tftp/

# Build custom root filesystem with debootstrap
RUN debootstrap bookworm /build/rootfs http://deb.debian.org/debian

# Add non-free firmware repository
RUN echo "deb http://deb.debian.org/debian bookworm main non-free-firmware" > /build/rootfs/etc/apt/sources.list

# Install packages inside the chroot
RUN chroot /build/rootfs apt-get update && \
    chroot /build/rootfs apt-get install -y \
        live-boot \
        systemd-sysv \
        xorg \
        mpv \
        openbox \
        xinit \
        network-manager \
        linux-image-amd64 \
        firmware-linux \
        alsa-utils \
        pulseaudio \
        && chroot /build/rootfs apt-get clean

# After installing all packages, regenerate the initramfs
RUN chroot /build/rootfs update-initramfs -u -k all

# --- Configure automatic X session ---

# Set up a simple user (optional, but cleaner). Here we rely on root for simplicity.
# Enable autologin on tty1 using systemd-getty-generator
RUN mkdir -p /build/rootfs/etc/systemd/system/getty@tty1.service.d && \
    echo '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --noclear %I $TERM' \
    > /build/rootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf

# Create .xinitrc to launch mpv fullscreen
RUN echo '#!/bin/sh\nmpv --fs http://192.168.10.1/video.mp4' > /build/rootfs/root/.xinitrc && \
    chmod +x /build/rootfs/root/.xinitrc

# Automatically start X on login (root will be logged in automatically)
RUN echo 'if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then\n    startx\nfi' \
    >> /build/rootfs/root/.profile

# --- Extract kernel and initrd from the chroot ---
RUN cp /build/rootfs/boot/vmlinuz-* /var/www/html/vmlinuz && \
    cp /build/rootfs/boot/initrd.img-* /var/www/html/initrd.img

# Build squashfs filesystem (now with .squashfs extension)
RUN mksquashfs /build/rootfs /var/www/html/rootfs.squashfs -comp xz -e boot

# iPXE boot script – use the new filename
RUN printf '#!ipxe\n\
dhcp\n\
kernel http://192.168.10.1/vmlinuz initrd=initrd.img boot=live components ip=dhcp fetch=http://192.168.10.1/rootfs.squashfs\n\
initrd http://192.168.10.1/initrd.img\n\
boot\n' > /var/www/html/boot.ipxe

# Copy configuration files (your existing dnsmasq.conf and start.sh)
COPY dnsmasq.conf /etc/dnsmasq.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose ports
EXPOSE 67/udp 69/udp 80

CMD ["/start.sh"]
