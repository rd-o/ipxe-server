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
    libopencv-dev \
    python3-opencv \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
    libcaca0 \
    && apt-get clean

# Prepare directories
RUN mkdir -p /srv/tftp /var/www/html /build/rootfs

COPY main.sh /root/main.sh
RUN chmod +x /root/main.sh

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
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-libav \
        xdotool \
        awesome \
        xterm \
        python3-pip \
        python3-requests \
        vlc \
        python3-vlc \
        openssh-server \
        caca-utils \
        python3-opencv \
        python3-pygame \
        && chroot /build/rootfs apt-get clean

# After installing all packages, regenerate the initramfs
RUN chroot /build/rootfs update-initramfs -u -k all

# --- Configure automatic X session ---

# Set up a simple user (optional, but cleaner). Here we rely on root for simplicity.
# Enable autologin on tty1 using systemd-getty-generator
RUN mkdir -p /build/rootfs/etc/systemd/system/getty@tty1.service.d && \
    echo '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --noclear %I $TERM' \
    > /build/rootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf

# Create .xinitrc for mpv mode (fullscreen video)
RUN echo '#!/bin/sh\nmpv --fs --no-border --keepaspect=no http://192.168.10.1/video.mp4' > /build/rootfs/root/.xinitrc && \
    chmod +x /build/rootfs/root/.xinitrc

# Create .xinitrc for awesomewm mode
RUN echo '#!/bin/sh\n\
exec awesome' > /build/rootfs/root/.xinitrc.awesome && \
    chmod +x /build/rootfs/root/.xinitrc.awesome

# Copy awesomewm config with autostart
RUN mkdir -p /build/rootfs/root/.config/awesome
COPY rc.lua /build/rootfs/root/.config/awesome/rc.lua

# Automatically start X on login (root will be logged in automatically)
# Select window manager via WINDOW_MANAGER env var (mpv or awesome, default: mpv)
RUN printf '#!/bin/sh\n\
        export SDL_AUDIODRIVER=pulseaudio\n\
        (sleep 3 && /usr/bin/pulseaudio --start --log-target=syslog 2>/dev/null) &\n\
        (sleep 5 && /usr/sbin/sshd) &\n\
        ln -sf /root/.xinitrc.awesome /root/.xinitrc\n\
        exec startx\n\
\n' > /build/rootfs/root/.profile && \
    chmod +x /build/rootfs/root/.profile

# --- Configure Xorg resolution to 800x600 ---
RUN mkdir -p /build/rootfs/etc/X11/xorg.conf.d && \
    printf 'Section "Screen"\n    Identifier "Screen0"\n    DefaultDepth 24\n    SubSection "Display"\n        Modes "800x600"\n    EndSubSection\nEndSection\n' > /build/rootfs/etc/X11/xorg.conf.d/10-modes.conf

# --- Extract kernel and initrd from the chroot ---
RUN cp /build/rootfs/boot/vmlinuz-* /var/www/html/vmlinuz && \
    cp /build/rootfs/boot/initrd.img-* /var/www/html/initrd.img

COPY slave.py /build/rootfs/root/slave.py
RUN chmod +x /build/rootfs/root/slave.py

COPY client.sh /build/rootfs/root/client.sh
RUN chmod +x /build/rootfs/root/client.sh

# Configure SSH for root login
RUN sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /build/rootfs/etc/ssh/sshd_config && \
    sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /build/rootfs/etc/ssh/sshd_config && \
    echo ' PermitRootLogin yes' >> /build/rootfs/etc/ssh/sshd_config

# Build squashfs filesystem (now with .squashfs extension)
RUN mksquashfs /build/rootfs /var/www/html/rootfs.squashfs -comp xz -e boot

# iPXE boot script – use the new filename
RUN printf '#!ipxe\n\
dhcp\n\
kernel http://192.168.10.1/vmlinuz initrd=initrd.img boot=live components ip=dhcp fetch=http://192.168.10.1/rootfs.squashfs\n\
initrd http://192.168.10.1/initrd.img\n\
boot\n' > /var/www/html/boot.ipxe

# Configure nginx for static file serving on specific IP
RUN rm -f /etc/nginx/sites-enabled/default && \
    mkdir -p /var/www/html && \
    printf 'server {\n    listen 192.168.10.1:80;\n    root /var/www/html;\n    index index.html index.htm;\n    location / {\n        autoindex on;\n    }\n}' > /etc/nginx/sites-available/default && \
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default && \
    echo "iPXE Boot Server" > /var/www/html/index.html

# Copy configuration files (your existing dnsmasq.conf and start.sh)
COPY dnsmasq.conf /etc/dnsmasq.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose ports
EXPOSE 67/udp 69/udp 80

CMD ["/start.sh"]
