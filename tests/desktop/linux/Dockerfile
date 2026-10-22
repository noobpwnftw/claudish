# Real IBus + GTK desktop for Claudish acceptance tests (no display hardware needed).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ibus ibus-gtk3 python3 python3-gi gir1.2-ibus-1.0 gir1.2-gtk-3.0 \
      xvfb xdotool x11-utils imagemagick dbus dbus-x11 xkb-data locales fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* && locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
RUN useradd -m tester
USER tester
WORKDIR /home/tester
