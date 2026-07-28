#!/usr/bin/env python3
"""ardop_ptt_bridge.py — TCP bridge between pat and piardopc that asserts
both DTR and RTS on the FTDI cable when pat sends PTTON.

Pat's ARDOP path is:
  pat-winlink --addr :5000
    -> ARDOP TNC connect (configurable addr, default :8515)
    -> piardopc :8515 (drives audio + accepts TCP commands)
    -> companion probe: host+1 (8516 when direct, 8518 via this bridge)

Piardopc's -p flag only asserts RTS on the FTDI cable. The G90 in this
g90digi image needs BOTH DTR and RTS asserted to key (proven via the
JS8Call matrix test on 2026-07-26). This bridge forwards everything pat
sends to piardopc, and intercepts PTTON/PTTOFF to assert both lines in
parallel.

Pat's `ardop.addr` should point to this bridge's port (:8517 by default).
Piardopc keeps its default ports (:8515, :8516); the bridge talks to it
on both.

Companion port (:8518 -> :8516):
  Pat probes the companion port (host+1) after connecting to the ARDOP
  TNC. If the probe fails, pat gives up on ARDOP entirely and never sends
  a connect — making the bridge useless. So the bridge also listens on
  :8518 and forwards to piardopc :8516 without interception (no PTT
  commands on the companion protocol). The companion path is plain
  bidirectional TCP forwarding.

  Discovered 2026-07-28: the companion-port probe is FATAL, not noise.
  Sunday's 2026-07-26 writeup annotated it as "non-fatal" — wrong.

The bridge is intentionally tiny (~120 lines) and only handles the ARDOP
TNC text protocol that piardopc uses on :8515. The companion protocol on
:8516 is opaque and just gets forwarded as bytes. We rely on piardopc
being the source of truth for both protocols.

License: MIT-style, project-internal.
"""
import os
import fcntl
import socket
import threading
import time
import sys
import select

FTDI_DEV = "/dev/serial/by-id/usb-FTDI_USB__-__Serial-if00-port0"
PIARDOPC_HOST = "127.0.0.1"
PIARDOPC_PORT_ARDOP = 8515
PIARDOPC_PORT_COMP = 8516
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT_ARDOP = 8517
LISTEN_PORT_COMP = 8518

TIOCMGET = 0x5415
TIOCMSET = 0x5418
TIOCM_RTS = 0x004
TIOCM_DTR = 0x002


def open_ftdi():
    """Open the FTDI device once; the bridge keeps this fd open for its
    lifetime. Each TCP connection borrows the fd briefly to set lines."""
    return os.open(FTDI_DEV, os.O_RDWR | os.O_NOCTTY)


def get_flags(fd):
    return int.from_bytes(fcntl.ioctl(fd, TIOCMGET, bytes(8)), "little")


def set_flags(fd, flags):
    fcntl.ioctl(fd, TIOCMSET, flags.to_bytes(8, "little"))


def assert_ptt(fd, on):
    """Assert (on=True) or deassert (on=False) BOTH DTR and RTS."""
    flags = get_flags(fd)
    if on:
        new = flags | TIOCM_DTR | TIOCM_RTS
    else:
        new = flags & ~(TIOCM_DTR | TIOCM_RTS)
    set_flags(fd, new)
    cur = get_flags(fd)
    print("[ptt] on=%s RTS=%d DTR=%d" % (
        on, bool(cur & TIOCM_RTS), bool(cur & TIOCM_DTR)), flush=True)


def forward_plain(client_sock, piardopc_sock):
    """Plain bidirectional forwarder — no PTT interception.

    Used for the companion port (:8518 -> :8516) where the protocol is
    not the ARDOP TNC text command set."""
    try:
        while True:
            r, _, _ = select.select([client_sock, piardopc_sock], [], [], 0.5)
            if client_sock in r:
                chunk = client_sock.recv(4096)
                if not chunk:
                    return
                try:
                    piardopc_sock.sendall(chunk)
                except OSError:
                    pass
            if piardopc_sock in r:
                chunk = piardopc_sock.recv(4096)
                if not chunk:
                    return
                try:
                    client_sock.sendall(chunk)
                except OSError:
                    pass
    except OSError:
        return


def relay_ardop(client_sock, piardopc_sock, ftdi_fd):
    """Bidirectional relay between pat and piardopc with PTT interception.

    Reads from client (pat), forwards to piardopc, and intercepts the
    ARDOP TNC commands PTTON/PTTOFF to assert both DTR and RTS on the
    FTDI cable before forwarding.

    Reads from piardopc, forwards back to client unchanged."""
    try:
        client_buf = b""

        def write_all(sock, data):
            try:
                sock.sendall(data)
            except OSError:
                pass

        while True:
            r, _, _ = select.select([client_sock, piardopc_sock], [], [], 0.5)
            if client_sock in r:
                chunk = client_sock.recv(4096)
                if not chunk:
                    return
                client_buf += chunk
                # ARDOP TNC commands are CRLF-terminated; flush complete ones.
                while b"\n" in client_buf:
                    line, _, rest = client_buf.partition(b"\n")
                    client_buf = rest
                    cmd = line.strip()
                    # Interceptor: PTTON and PTTOFF toggle PTT in parallel
                    # with forwarding to piardopc.
                    if cmd == b"PTTON":
                        assert_ptt(ftdi_fd, True)
                        write_all(piardopc_sock, line + b"\r\n")
                    elif cmd == b"PTTOFF":
                        assert_ptt(ftdi_fd, False)
                        write_all(piardopc_sock, line + b"\r\n")
                    else:
                        write_all(piardopc_sock, line + b"\r\n")
            if piardopc_sock in r:
                chunk = piardopc_sock.recv(4096)
                if not chunk:
                    return
                write_all(client_sock, chunk)
    except OSError:
        return


def handle_connection(client_sock, addr, kind, ftdi_fd):
    """Handle a connection: 'ardop' (with PTT intercept) or 'companion' (plain)."""
    print("[conn] %s from %s:%d" % (kind, addr[0], addr[1]), flush=True)
    client_sock.settimeout(60)
    if kind == "ardop":
        upstream_port = PIARDOPC_PORT_ARDOP
    else:
        upstream_port = PIARDOPC_PORT_COMP
    try:
        piardopc_sock = socket.create_connection(
            (PIARDOPC_HOST, upstream_port), timeout=10)
    except OSError as e:
        print("[conn] piardopc :%d connect failed: %s" %
              (upstream_port, e), flush=True)
        client_sock.close()
        return
    try:
        if kind == "ardop":
            relay_ardop(client_sock, piardopc_sock, ftdi_fd)
        else:
            forward_plain(client_sock, piardopc_sock)
    finally:
        client_sock.close()
        piardopc_sock.close()
        print("[conn] %s:%d closed" % addr, flush=True)


def accept_loop(srv, kind, ftdi_fd):
    """Accept connections on `srv` and dispatch by kind."""
    while True:
        client_sock, addr = srv.accept()
        t = threading.Thread(
            target=handle_connection,
            args=(client_sock, addr, kind, ftdi_fd), daemon=True)
        t.start()


def main():
    ftdi_fd = open_ftdi()
    set_flags(ftdi_fd, 0)  # start with both lines low
    print("[bridge] FTDI %s opened, lines low" % FTDI_DEV, flush=True)

    ardop_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ardop_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ardop_srv.bind((LISTEN_HOST, LISTEN_PORT_ARDOP))
    ardop_srv.listen(8)
    print("[bridge] listening on %s:%d -> piardopc :%d (ARDOP, PTT intercept)" %
          (LISTEN_HOST, LISTEN_PORT_ARDOP, PIARDOPC_PORT_ARDOP), flush=True)

    comp_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    comp_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    comp_srv.bind((LISTEN_HOST, LISTEN_PORT_COMP))
    comp_srv.listen(8)
    print("[bridge] listening on %s:%d -> piardopc :%d (companion, plain forward)" %
          (LISTEN_HOST, LISTEN_PORT_COMP, PIARDOPC_PORT_COMP), flush=True)

    t_ardop = threading.Thread(
        target=accept_loop, args=(ardop_srv, "ardop", ftdi_fd), daemon=True)
    t_comp = threading.Thread(
        target=accept_loop, args=(comp_srv, "companion", ftdi_fd), daemon=True)
    t_ardop.start()
    t_comp.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[bridge] shutting down", flush=True)
    finally:
        set_flags(ftdi_fd, 0)
        os.close(ftdi_fd)
        ardop_srv.close()
        comp_srv.close()


if __name__ == "__main__":
    main()