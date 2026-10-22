# systemd as PID 1 with a lingering user, to test `claudish service` for real (systemd user units).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv dbus dbus-user-session python3 \
    ca-certificates libgomp1 libstdc++6 libssl3t64 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1001 tester && mkdir -p /var/lib/systemd/linger && touch /var/lib/systemd/linger/tester
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
