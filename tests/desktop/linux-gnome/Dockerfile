# GNOME Shell on Wayland, headless, with IBus: the default desktop of Ubuntu and Fedora.
# systemd is PID 1 so logind and a user session exist, as GNOME Shell requires.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus dbus-user-session libpam-systemd \
      gnome-shell mutter ibus ibus-gtk3 python3 python3-gi gir1.2-ibus-1.0 gir1.2-gtk-3.0 \
      xkb-data locales fonts-dejavu-core gsettings-desktop-schemas \
    && rm -rf /var/lib/apt/lists/* && locale-gen en_US.UTF-8 \
    && useradd -m -u 1001 tester && mkdir -p /var/lib/systemd/linger && touch /var/lib/systemd/linger/tester
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
