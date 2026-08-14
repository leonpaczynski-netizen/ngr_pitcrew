"""UDP listener thread, from SimHub's relay or straight off the PS5.

Two sources, one socket, and the difference between them is a single byte.

**SimHub relay.** SimHub does the talking to the console and re-broadcasts
the raw encrypted packets to a local port. Nothing has to be sent; the
listener binds and waits.

**Direct.** The console streams to nobody until it is asked, and it stops
when the asking stops, so the same socket that receives has to send a
heartbeat on a timer. It must be the *same* socket: GT7 streams back to the
address and port the heartbeat came from, so sending from a second socket
produces a console dutifully streaming to a port nothing is listening on.

The heartbeat is one character and it chooses the packet format. `C` is the
368-byte superset and the only one carrying current-lap time in
milliseconds, which live strategy needs, so `C` is what is asked for. If
nothing decodes under it the listener falls back to `A` and **says so**
rather than sitting there receiving nothing - CLAUDE.md 3.1 and 7 both: the
connection fails loudly, because a stream of zeros is the one failure mode
that survives all the way into a setup recommendation.
"""
from __future__ import annotations
import socket
import threading
import time
from collections import deque
from typing import Callable

from pitcrew.diagnostics import log

# GT7's own pair. The console listens for heartbeats on 33739 and streams to
# whichever address and port asked. **Unverified against hardware** -
# CLAUDE.md 3.1 flags this pair as verify-before-building, and it is what the
# connection self-test exists to check rather than assume.
GT7_HEARTBEAT_PORT = 33739
GT7_STREAM_PORT = 33740

# Which packet format to ask for. `C` is the 368-byte superset and the only
# one carrying current-lap time in ms.
HEARTBEAT_C = b"C"
HEARTBEAT_A = b"A"

# Published implementations re-send anywhere from every 100 packets (~1.7 s)
# to every 1000 (~16 s). One second is comfortably inside all of them.
HEARTBEAT_INTERVAL_S = 1.0

# Stream silence this long is a dropped connection, so ask again rather than
# waiting for the timer.
SILENCE_S = 1.0

# How long to keep asking in one format before concluding it will not come
# and trying the other.
FORMAT_PATIENCE_S = 4.0


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

    def _send_heartbeat(self, sock: socket.socket) -> None:
        """Ask the console to keep streaming, from the receiving socket.

        Deliberately the same socket. GT7 streams back to whatever address
        and port asked it to, so a heartbeat sent from a second socket
        produces a console streaming faithfully to a port nothing is bound
        to - which looks, from here, exactly like a console switched off.
        """
        try:
            sock.sendto(self._heartbeat,
                        (self._heartbeat_to, GT7_HEARTBEAT_PORT))
            self._heartbeats_sent += 1
            self._send_error = None
        except OSError as exc:
            if self._send_error is None:
                log("udp").error(
                    "heartbeat to %s:%s failed: %s - the console will not "
                    "stream to an address that has not asked it to.",
                    self._heartbeat_to, GT7_HEARTBEAT_PORT, exc)
            self._send_error = str(exc)
    return None


class UDPListener(threading.Thread):
    """Daemon thread that reads UDP packets and calls `callback(data: bytes)`."""

    def __init__(self, host: str, port: int, callback: Callable[[bytes], None],
                 *, source_ip: str | None = None,
                 heartbeat_to: str | None = None) -> None:
        super().__init__(daemon=True, name="UDPListener")
        self._host = host
        self._port = port
        self._callback = callback
        # The console's address, when talking to it directly. None means
        # something else is doing the asking and this only listens.
        self._heartbeat_to = (heartbeat_to or "").strip() or None
        self._heartbeat = HEARTBEAT_C
        self._heartbeats_sent = 0
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
        self._send_error: str | None = None

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
    def heartbeating(self) -> bool:
        return self._heartbeat_to is not None

    @property
    def heartbeat_format(self) -> str:
        """Which packet format is being asked for, as its heartbeat letter."""
        return self._heartbeat.decode()

    @property
    def heartbeats_sent(self) -> int:
        return self._heartbeats_sent

    @property
    def send_error(self) -> str | None:
        """Why the heartbeat could not be sent, if it could not.

        A console that is never asked streams nothing, which looks exactly
        like a console that is switched off. This tells them apart.
        """
        return self._send_error

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
        sock.settimeout(0.5)

        started = last_packet_time = time.monotonic()
        last_heartbeat = 0.0
        self._connected = False
        switched_format = False

        while not self._stop_event.is_set():
            now = time.monotonic()
            if self._heartbeat_to is not None:
                silent = now - last_packet_time
                due = now - last_heartbeat >= HEARTBEAT_INTERVAL_S
                if due or (silent > SILENCE_S and self._total_received):
                    self._send_heartbeat(sock)
                    last_heartbeat = now
                # Nothing at all under `C` for a few seconds means this
                # console will not speak it. Fall back once, loudly, and
                # let the export declare the format it actually got.
                if (not switched_format and not self._total_received
                        and now - started > FORMAT_PATIENCE_S):
                    switched_format = True
                    self._heartbeat = HEARTBEAT_A
                    log("udp").warning(
                        "no packet decoded in %.0f s of asking %s:%s for "
                        "format C - falling back to A. Format C carries "
                        "current-lap time in ms and A does not, so live "
                        "strategy will be working without it.",
                        FORMAT_PATIENCE_S, self._heartbeat_to,
                        GT7_HEARTBEAT_PORT)

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

    def _send_heartbeat(self, sock: socket.socket) -> None:
        """Ask the console to keep streaming, from the receiving socket.

        Deliberately the same socket. GT7 streams back to whatever address
        and port asked it to, so a heartbeat sent from a second socket
        produces a console streaming faithfully to a port nothing is bound
        to - which looks, from here, exactly like a console switched off.
        """
        try:
            sock.sendto(self._heartbeat,
                        (self._heartbeat_to, GT7_HEARTBEAT_PORT))
            self._heartbeats_sent += 1
            self._send_error = None
        except OSError as exc:
            if self._send_error is None:
                log("udp").error(
                    "heartbeat to %s:%s failed: %s - the console will not "
                    "stream to an address that has not asked it to.",
                    self._heartbeat_to, GT7_HEARTBEAT_PORT, exc)
            self._send_error = str(exc)
