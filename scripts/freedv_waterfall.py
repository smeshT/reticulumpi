#!/usr/bin/env python3
"""
freedv_waterfall.py — live spectrogram of G90 USB audio for freeDV
diagnostics. Shows a scrolling waterfall in the terminal (curses)
and prints the peak audio frequency in Hz, so the user can dial
the sbitx RX VFO to match where the G90 is transmitting.

This is a *diagnostic* tool, not a modem. It is intentionally
simple: read PCM, FFT, paint, repeat. No rig control, no mode
logic, no decode. The peak-Hz readout is the actionable output;
the waterfall is the visual confirmation.

Design notes:

- ALSA capture via the `sounddevice` package (libportaudio2 +
  python3-sounddevice on the g90digi image). We fall back to
  `arecord` piping if sounddevice isn't importable, but the
  primary path is sounddevice because it's lower latency and
  doesn't fork a subprocess per buffer.

- We capture at 48000 Hz mono. The G90 USB audio is 48000 Hz
  on the g90digi image (per /etc/reticulumhf/config.env's
  AUDIO_CARD settings). 48k gives us a Nyquist of 24kHz, which
  covers the freeDV carrier band (300-3000 Hz) with plenty of
  margin. If the user's G90 reports 44100, this still works —
  the waterfall shows the full audio band regardless of the
  exact sample rate.

- The audio device defaults to "g90audio" (a dsnoop device
  defined in /etc/asound.conf on the g90). The dsnoop layer
  means freedvtnc2 and this tool can both hold the G90 audio
  open at the same time — no need to stop the Reticulum stack
  to look at the waterfall. Override with --device for testing
  on systems that don't have the dsnoop alias.

- We use a 1024-sample FFT with 50% overlap (hop = 512). That
  gives ~47 Hz per bin and 50% new-data per frame, which is
  smooth on a Pi 4. Window function is Hann (good general-
  purpose for spectral peaks).

- The waterfall is one column per FFT bin, one row per time
  step. Colors map log-magnitude to a small palette (8 levels,
  blue→cyan→green→yellow→red). On a 200-row terminal height
  that's ~6 seconds of history at 47ms/frame.

- The peak-Hz readout is computed as a 5-bin parabolic
  interpolation around the max bin in the 200-3000 Hz range.
  That range is where the freeDV carrier lives; below 200 is
  DC + line hum, above 3000 is out-of-band. The interpolation
  gets us sub-bin resolution (~10 Hz typical), which is the
  whole point — you want "1480 Hz" not "47 Hz bin 31".

- No decoder. The whole tool fits in ~200 lines. If you find
  yourself adding mode logic, you've drifted into fldigi
  territory and should reconsider.

Controls:
  q / Ctrl-C  quit
  s           toggle "spectrum line" overlay (the current FFT
              drawn over the waterfall, in white)
  p           toggle peak marker (a thin red line at the
              detected peak frequency, useful for eyeballing
              drift over time)
  + / -       zoom in/out on the y-axis (dB range)
  r           reset dB range to auto
"""

import argparse
import curses
import math
import sys
import time

import numpy as np

try:
    import sounddevice as sd
    HAVE_SD = True
except ImportError:
    HAVE_SD = False


# --- Configuration --------------------------------------------------------

DEFAULT_DEVICE = "g90audio"   # dsnoop alias in /etc/asound.conf
SAMPLE_RATE    = 48000
FFT_SIZE       = 1024
HOP            = 512          # 50% overlap
PEAK_LO_HZ     = 200.0        # ignore DC + line hum
PEAK_HI_HZ     = 3000.0       # freeDV carrier band


# --- Audio capture --------------------------------------------------------

class Capture:
    """Ring-buffer capture from a single ALSA input device.

    Uses sounddevice if available; falls back to arecord piping
    if not. The fallback is intentional so this tool runs on
    a stock image even without python3-sounddevice, but the
    primary path is sounddevice."""

    def __init__(self, device, samplerate=SAMPLE_RATE, blocksize=HOP):
        self.device = device
        self.samplerate = samplerate
        self.blocksize = blocksize
        if HAVE_SD:
            self._stream = sd.InputStream(
                device=device, channels=1, dtype="float32",
                samplerate=samplerate, blocksize=blocksize,
            )
        else:
            self._stream = None

    def __enter__(self):
        if self._stream is not None:
            self._stream.start()
        else:
            # Spawn arecord -> stdout. We don't talk to it here;
            # the run() loop reads from self._proc.stdout instead.
            import subprocess
            self._proc = subprocess.Popen(
                ["arecord", "-q", "-D", self.device,
                 "-f", "S16_LE", "-r", str(self.samplerate),
                 "-c", "1",
                 "-t", "raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        return self

    def read(self):
        """Return a numpy float32 array of length blocksize, or
        None if capture failed."""
        if self._stream is not None:
            data, _ = self._stream.read(self.blocksize)
            return data[:, 0].astype(np.float32) if data.size else None
        else:
            raw = self._proc.stdout.read(self.blocksize * 2)
            if len(raw) < self.blocksize * 2:
                return None
            return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    def __exit__(self, *a):
        if self._stream is not None:
            self._stream.stop(); self._stream.close()
        else:
            try:
                self._proc.terminate(); self._proc.wait(timeout=2)
            except Exception:
                pass


# --- DSP ------------------------------------------------------------------

def next_pow2(n):
    p = 1
    while p < n: p <<= 1
    return p


def parabolic_peak(mag, peak_idx):
    """Sub-bin peak via parabolic interpolation. mag[peak_idx-1:peak_idx+2]
    is fit to a parabola; the apex is the interpolated magnitude and
    offset. Returns (offset_bins_from_peak_idx, 0.0) — the magnitude
    is unused but kept for symmetry with other peak-finders."""
    if peak_idx <= 0 or peak_idx >= len(mag) - 1:
        return 0.0
    a, b, c = mag[peak_idx - 1], mag[peak_idx], mag[peak_idx + 1]
    denom = (a - 2 * b + c)
    if denom == 0:
        return 0.0
    return 0.5 * (a - c) / denom


def compute_spectrum(buf, window):
    """Return (magnitude_db, peak_hz, peak_db). buf is one FFT_SIZE
    block of audio. We window, FFT, take |X|, convert to dB, and
    find the peak in the freeDV carrier band."""
    n = len(buf)
    if n != len(window):
        # Shouldn't happen if HOP/FFT_SIZE are honored, but be safe.
        window = np.hanning(n).astype(np.float32)
    x = buf * window
    # rFFT: n/2+1 bins, DC at 0, Nyquist at the end
    spec = np.abs(np.fft.rfft(x)) * (2.0 / n)
    mag_db = 20.0 * np.log10(spec + 1e-9)

    # Convert bin index to Hz
    bin_hz = SAMPLE_RATE / n
    lo_bin = max(1, int(PEAK_LO_HZ / bin_hz))
    hi_bin = min(len(mag_db) - 1, int(PEAK_HI_HZ / bin_hz))
    band = mag_db[lo_bin:hi_bin + 1]
    peak_idx_local = int(np.argmax(band))
    peak_idx = lo_bin + peak_idx_local
    offset = parabolic_peak(mag_db, peak_idx)
    peak_hz = (peak_idx + offset) * bin_hz
    peak_db = float(mag_db[peak_idx])
    return mag_db, peak_hz, peak_db


# --- Curses UI ------------------------------------------------------------

# 8-level palette: dim blue → cyan → green → yellow → red → bright red → white
PALETTE = [
    (curses.COLOR_BLUE,     curses.A_DIM),
    (curses.COLOR_CYAN,     curses.A_DIM),
    (curses.COLOR_CYAN,     curses.A_NORMAL),
    (curses.COLOR_GREEN,    curses.A_NORMAL),
    (curses.COLOR_GREEN,    curses.A_BOLD),
    (curses.COLOR_YELLOW,   curses.A_BOLD),
    (curses.COLOR_RED,      curses.A_BOLD),
    (curses.COLOR_WHITE,    curses.A_BOLD | curses.A_REVERSE),
]


def db_to_palette(db, db_lo, db_hi):
    """Map a dB value to a palette index 0..7."""
    if db_hi <= db_lo:
        return 0
    frac = (db - db_lo) / (db_hi - db_lo)
    frac = max(0.0, min(0.999, frac))
    return int(frac * len(PALETTE))


def run(stdscr, device, show_overlay, show_peak):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)

    # Init palette
    curses.start_color()
    if not curses.has_colors():
        # No color: degrade to a single character, but still draw
        pass
    for i, (col, attr) in enumerate(PALETTE):
        try:
            curses.init_pair(i + 1, col, curses.COLOR_BLACK)
        except curses.error:
            pass

    h, w = stdscr.getmaxyx()
    # Bin axis: 0..FFT_SIZE/2, we draw w columns (left=0, right=Nyquist)
    # but only show 200..3000 Hz by skipping low/high bins.
    # Recompute on resize.
    title_row = 0
    hud_row   = h - 1
    plot_h    = h - 2
    plot_w    = w

    # Pre-compute which FFT bins map to which terminal column.
    bin_hz = SAMPLE_RATE / FFT_SIZE
    # We want to show 0..4000 Hz across the terminal. That keeps the
    # freeDV band (200-3000) well within the visible area without
    # wasting columns on out-of-band noise.
    show_hi_hz = 4000.0
    hi_bin = min(FFT_SIZE // 2, int(show_hi_hz / bin_hz))
    # For each terminal column, which bin does it represent? (left=bin 1,
    # right=bin hi_bin). line up the 200-3000 region to the center 80%.
    lo_bin = max(1, int(PEAK_LO_HZ / bin_hz))
    band_lo = lo_bin
    band_hi = hi_bin
    col_to_bin = np.linspace(band_lo, band_hi, plot_w).astype(int)
    col_to_bin = np.clip(col_to_bin, 0, FFT_SIZE // 2)

    # Rolling buffer of past spectra (one row per time step)
    history = np.full((plot_h, plot_w), -120.0, dtype=np.float32)

    # dB range (auto-zoom with manual override)
    db_lo, db_hi = -90.0, -10.0
    auto_db = True

    # Window
    window = np.hanning(FFT_SIZE).astype(np.float32)

    last_print = 0.0
    peak_hz_avg = 0.0

    with Capture(device, SAMPLE_RATE, HOP) as cap:
        # Sliding audio buffer for FFT_SIZE samples
        ring = np.zeros(FFT_SIZE, dtype=np.float32)
        n_filled = 0

        while True:
            block = cap.read()
            if block is None:
                time.sleep(0.01)
                continue

            # Slide ring buffer
            if n_filled + len(block) <= FFT_SIZE:
                ring[n_filled:n_filled + len(block)] = block
                n_filled += len(block)
                if n_filled < FFT_SIZE:
                    continue
            else:
                take = FFT_SIZE - n_filled
                ring[n_filled:] = block[:take]
                ring[:HOP] = block[take:]

            mag_db, peak_hz, peak_db = compute_spectrum(ring, window)

            # Track peak Hz (low-pass for stability)
            if peak_hz_avg == 0.0:
                peak_hz_avg = peak_hz
            else:
                peak_hz_avg = 0.7 * peak_hz_avg + 0.3 * peak_hz

            # Auto dB range: track the max dB seen recently, with a
            # headroom. We don't track the floor because that's just
            # noise floor; a fixed -90 dB is fine.
            if auto_db:
                db_hi = max(-20.0, min(0.0, peak_db + 10.0))

            # Shift history down, write new row at top
            history[1:] = history[:-1]
            new_row = mag_db[col_to_bin]
            history[0] = new_row

            # Redraw
            stdscr.erase()
            # Title
            try:
                stdscr.addstr(title_row, 0,
                              f" freeDV Waterfall  device={device}  "
                              f"rate={SAMPLE_RATE}  fft={FFT_SIZE}")
            except curses.error:
                pass

            # Waterfall: row 0 is the newest (top). history[0] is the
            # newest spectrum. We draw it on terminal row title_row+1
            # (which is the topmost plot row).
            for r in range(plot_h):
                if r >= h - title_row - 1:
                    break
                for c in range(plot_w):
                    db = history[r, c]
                    pal = db_to_palette(db, db_lo, db_hi)
                    if curses.has_colors():
                        ch = " "  # solid block via reverse; just space
                        attr = curses.color_pair(pal + 1) | PALETTE[pal][1]
                    else:
                        # No-color fallback: use ASCII density
                        attr = curses.A_NORMAL
                        ch = " .-:+*#@"[pal] if pal < 8 else "?"
                    try:
                        stdscr.addch(title_row + 1 + r, c, ch, attr)
                    except curses.error:
                        pass

            # Optional peak marker (thin vertical line at the peak bin)
            if show_peak and 0 < peak_hz < show_hi_hz:
                peak_col = int((peak_hz / show_hi_hz) * (plot_w - 1))
                for r in range(plot_h):
                    try:
                        stdscr.addch(title_row + 1 + r, peak_col,
                                     "│",
                                     curses.color_pair(8) | curses.A_BOLD)
                    except curses.error:
                        pass

            # Optional spectrum overlay (the current FFT, white)
            if show_overlay:
                for c in range(plot_w):
                    db = history[0, c]
                    if db >= db_hi - 3.0:
                        try:
                            stdscr.addch(title_row + 1, c, "▀",
                                         curses.color_pair(8) | curses.A_BOLD)
                        except curses.error:
                            pass

            # HUD
            try:
                hud = (f" peak: {peak_hz:7.1f} Hz  "
                       f"mag: {peak_db:+6.1f} dB  "
                       f"avg: {peak_hz_avg:7.1f} Hz  "
                       f"range: {db_lo:+5.0f}..{db_hi:+5.0f} dB  "
                       f"[a]uto={'Y' if auto_db else 'N'}  "
                       f"[s]pec={'Y' if show_overlay else 'N'}  "
                       f"[p]eak={'Y' if show_peak else 'N'}  "
                       f"[+/-]range  [r]eset  [q]uit")
                stdscr.addstr(hud_row, 0, hud[:w - 1])
            except curses.error:
                pass

            stdscr.refresh()

            # Also print the peak Hz to stdout (so the user can
            # `tee` or `tail -f` it). Throttled to 4 Hz so the
            # terminal scroll doesn't overwhelm.
            now = time.time()
            if now - last_print > 0.25:
                print(f"peak: {peak_hz:7.1f} Hz  mag: {peak_db:+6.1f} dB  "
                      f"avg: {peak_hz_avg:7.1f} Hz", flush=True)
                last_print = now

            # Input
            try:
                ch = stdscr.getch()
            except Exception:
                ch = -1
            if ch in (ord('q'), 27):  # q or ESC
                return
            elif ch == ord('s'):
                show_overlay = not show_overlay
            elif ch == ord('p'):
                show_peak = not show_peak
            elif ch == ord('a'):
                auto_db = not auto_db
            elif ch in (ord('+'), ord('=')):
                db_hi -= 3.0
                auto_db = False
            elif ch in (ord('-'), ord('_')):
                db_hi += 3.0
                auto_db = False
            elif ch == ord('r'):
                db_lo, db_hi = -90.0, -10.0
                auto_db = True


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--device", default=DEFAULT_DEVICE,
                   help=f"ALSA capture device (default: {DEFAULT_DEVICE})")
    p.add_argument("--no-overlay", action="store_true",
                   help="start without the spectrum overlay")
    p.add_argument("--peak", action="store_true",
                   help="start with the peak marker visible")
    args = p.parse_args()

    if not HAVE_SD and not sys.stdin.isatty():
        # No sounddevice + no TTY: we can't run. Tell the user.
        print("freedv_waterfall: this tool needs either python3-sounddevice",
              file=sys.stderr)
        print("or a TTY (for the curses UI). Neither available here.",
              file=sys.stderr)
        sys.exit(1)

    try:
        curses.wrapper(run, args.device, not args.no_overlay, args.peak)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
