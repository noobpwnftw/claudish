# GNOME Shell on Wayland, headless, with IBus: the default desktop of Ubuntu and Fedora.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      gnome-shell mutter ibus ibus-gtk3 python3 python3-gi gir1.2-ibus-1.0 gir1.2-gtk-3.0 \
      dbus dbus-user-session xkb-data locales fonts-dejavu-core gsettings-desktop-schemas \
    && rm -rf /var/lib/apt/lists/* && locale-gen en_US.UTF-8 \
    && useradd -m -u 1001 tester
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
USER tester
WORKDIR /home/tester
