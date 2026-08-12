"""UDP listener thread that receives GT7 packets from SimHub."""
from __future__ import annotations
import socket
import threading
import time
from collections import deque
from typing import Callable

from pitcrew.diagnostics import log


class BindFailed(OSError):
    """The port could not be opened, so nothing will ever arrive on it.

    Raised rather than logged because the alternative - a listener that runs
    and receives nothing - is indistinguishable from a console that is not
    streaming, and CLAUDE.md 7 requires the connection to fail loudly.
    """


def probe_port(port: int) -> str | None:
    """Try to bind `port`. Returns the reason it failed, or None if it is free.

    A dry run for the Settings screen, so a port that is already taken is
    found while he is looking at the setting rather than when he goes out.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError as exc:
        return str(exc)
    finally:
        sock.close()
    return None


class UDPListener(threading.Thread):
    """Daemon thread that reads UDP packets and calls `callback(data: bytes)`."""

    def __init__(self, host: str, port: int, callback: Callable[[bytes], None],
                 *, source_ip: str | None = None) -> None:
        super().__init__(daemon=True, name="UDPListener")
        self._host = host
        self._port = port
        self._callback = callback
        # When set, packets from any other address are dropped before they
        # reach the parser. Without it a stray packet on the same port decodes
        # to nonsense and is counted as a decode error, which reads as "the
        # relay is broken" rather than "something else is talking".
        self._source_ip = (source_ip or "").strip() or None
        self._stop_event = threading.Event()
        self._packet_timestamps: deque[float] = deque(maxlen=120)
        self._total_received = 0
        self._parse_errors = 0
        self._foreign_dropped = 0
        self._connected = False
        self._bind_error: str | None = None

    @property
    def packet_rate(self) -> float:
        """Packets per second over the last ~2 seconds."""
        ts = self._packet_timestamps
        if len(ts) < 2:
            return 0.0
        return (len(ts) - 1) / (ts[-1] - ts[0])

    @property
    def total_received(self) -> int:
        return self._total_received

    @property
    def connected(self) -> bool:
        return self._connected

    def increment_errors(self) -> None:
        self._parse_errors += 1

    @property
    def parse_errors(self) -> int:
        return self._parse_errors

    @property
    def foreign_dropped(self) -> int:
        """Packets refused because they came from the wrong address."""
        return self._foreign_dropped

    @property
    def source_ip(self) -> str | None:
        return self._source_ip

    @property
    def bind_error(self) -> str | None:
        """Why the port could not be opened, if it could not.

        A listener that failed to bind receives nothing, which looks exactly
        like a console that is not streaming. This is what tells the two
        apart.
        """
        return self._bind_error

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Bind to INADDR_ANY so we receive regardless of which interface SimHub uses
            sock.bind(("0.0.0.0", self._port))
        except OSError as e:
            log("udp").error("bind failed on port %s: %s - is another "
                             "copy of Pit Crew already running?",
                             self._port, e)
            self._bind_error = str(e)
            return
        sock.settimeout(1.0)

        last_packet_time = time.monotonic()
        self._connected = False

        while not self._stop_event.is_set():
            try:
                data, sender = sock.recvfrom(4096)
            except socket.timeout:
                if time.monotonic() - last_packet_time > 3.0:
                    self._connected = False
                continue
            except OSError:
                break

            if self._source_ip and sender[0] != self._source_ip:
                self._foreign_dropped += 1
                if self._foreign_dropped == 1:
                    log("udp").warning(
                        "dropping packets from %s: the source filter is set "
                        "to %s. Clear it on the Settings screen if the "
                        "console's address changed.",
                        sender[0], self._source_ip)
                continue

            now = time.monotonic()
            last_packet_time = now
            self._packet_timestamps.append(now)
            self._total_received += 1
            self._connected = True

            try:
                self._callback(data)
            except Exception as exc:
                log("udp").error("packet handler raised: %s: %s",
                                 type(exc).__name__, exc, exc_info=True)

        sock.close()
