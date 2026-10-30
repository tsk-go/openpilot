"""Key fob radio: hears the owner's Toyota fob through an RTL-SDR dongle and prints one JSON line per event.

  rtl_sdr -f 313.22M -s 2560000 -g 40 - | python -m openpilot.starpilot.system.starview.fob_radio [FOB_ID ...]
(fob.py runs both at nice 10)

Run by fob.py (starviewd) only while it's useful; it never acts on anything itself.

The fob (2021 Sienna): 2-FSK, +-14.3 kHz, 2860 chips/s Manchester, 256-bit frames sent 4 times per press (0.72 s),
alternating between two channels press by press - 312.099 and 314.349 MHz. Tuned between them at 2.56 MS/s, one
dongle hears both. Bits 200-235 of every frame are the fob's fixed ID (sent normal or inverted); the rest changes
every press (encrypted: Lock and Unlock look the same). A held button keeps sending (~4-6 s).

Cost: every 10 ms one 1024-point FFT of the first 1024 samples of that block (enough to see a 0.72 s burst): each
channel's power (+-25 kHz) against the bands right beside it. The fob is narrow, so it stands far above its sides
(~18 dB); the wideband hash a car is full of (seen in the van: 312.3-312.6 MHz) lifts both alike and never does - no
noise floor to estimate, so a floor that moves can't fool it. Only when a burst is heard are its samples kept, and a worker
thread decodes the first 0.6 s of it (the reader never waits for it, so the dongle never drops samples):
  shift that channel to zero, average down to 128 kS/s, energy in each tone over one chip (two-tone detector), chip
  clock from where the tone flips (phase on a circle of one chip, followed through the burst), Manchester pairs ->
  soft bits, frame start from the preamble and the known IDs, and the 3-4 repeats added together bit by bit.

Events (stdout, one JSON object per line):
  {"e": "ready"}                                           first samples arrived
  {"e": "burst", "b", "ch", "rep", "raw_id", "id", "m", "frame", "t0", "dec_ms", "lag_ms", "db"}   decoded (id: the known
      ID it matches, or None; t0: when the burst began, time.monotonic(); dec_ms: the decode; lag_ms: how far behind
      the radio the reader was; db: the strongest the channel stood above its sides so far - the range left)
  {"e": "hold", "b"}                                       burst b still on after HOLD_BLOCKS (a held button)
  {"e": "on", "b", "ms"}                                   every PULSE_BLOCKS while that hold lasts (ms: held so far)
  {"e": "end", "b", "ms"}                                  burst b is over
Bursts shorter than MIN_BLOCKS are dropped without a word: other transmitters near 312 MHz (seen in the van) blip
all the time, and decoding them would put a real press in a queue behind them.
"""
import json
import queue
import sys
import threading
import time
from collections import deque

import numpy as np

FS = 2_560_000
FC = 313.22e6
CHANS = (312.0988e6, 314.349e6)
BLK = FS // 100                      # 10 ms
NFFT = 1024
DEC = 20
FS2 = FS // DEC                      # 128 kS/s after the channel is cut out
CHIP = FS2 / 2860
FRAME = 256
PRE_BITS = "1000000000"
ID_AT, ID_BITS = 200, 36
PRE_BLOCKS = 3                       # kept from before the burst was noticed
EARLY_AT = (25, 40)                  # first tries after 0.25 s (1.5 frames: the ID template finds it) and 0.4 s
                                     # (2+ frames): a clear press is acted on long before it ends
DECODE_BLOCKS = 60                   # the full try after 0.6 s (3+ of a press's 4 frames), if the first didn't match
LAG_WINDOW = 10                      # the reader's lag counts from the best second of the last 10 (samples dropped
                                     # when the car turns off would otherwise read as lag forever)
HOLD_BLOCKS = 100                    # still sending after 1 s: the button is held
PULSE_BLOCKS = 25                    # "on" every 250 ms during a hold
MAX_BURST_BLOCKS = 1200              # 12 s: a held fob sends ~4-6 s; longer is something else
SETTLE_BLOCKS = 100                  # the tuner's first second is ignored (it settles: power jumps around)
MIN_BLOCKS = 50                      # a fob burst lasts 0.72 s or more: anything under 0.5 s is something else
STALE_S = 3.0                        # a decode job that waited this long is dropped (the newest press counts)
ON_DB, OFF_DB, OFF_BLOCKS = 6.0, 3.0, 3   # channel over its sides: the van's hash peaks at ~5 dB, a press sits at ~18

_LUT = np.arange(256, dtype=np.float32) - 127.5
_WIN = np.hanning(NFFT).astype(np.float32)


def iq(raw: bytes) -> np.ndarray:
  """rtl_sdr's unsigned 8-bit I/Q -> complex64, one table lookup."""
  return _LUT[np.frombuffer(raw, dtype=np.uint8)].view(np.complex64)


def _bins(f: float) -> tuple[slice, slice, slice]:
  k = int(round((f - FC) / FS * NFFT)) % NFFT
  return slice(k - 10, k + 11), slice(k - 36, k - 15), slice(k + 16, k + 37)


_SL = [_bins(f) for f in CHANS]


def chan_power(raw: bytes) -> list[float]:
  """dB each channel (+-25 kHz) stands above the bands beside it, over the first 1024 samples of a block."""
  s = np.abs(np.fft.fft(iq(raw[:2 * NFFT]) * _WIN)) ** 2
  return [10 * np.log10((float(s[c].sum()) + 1e-9) / ((float(s[a].sum()) + float(s[b].sum())) / 2 + 1e-9))
          for c, a, b in _SL]


_MIX = {}


def _mixer(ch: int):
  if ch not in _MIX:
    fo = CHANS[ch] - FC
    n = np.arange(BLK)
    _MIX[ch] = (np.exp(-2j * np.pi * fo * n / FS).astype(np.complex64), complex(np.exp(-2j * np.pi * fo * BLK / FS)))
  return _MIX[ch]


def baseband(blocks: list[bytes], ch: int) -> np.ndarray:
  """Contiguous 10 ms blocks -> that channel at 0 Hz, 128 kS/s."""
  table, step = _mixer(ch)
  x = iq(b"".join(blocks)).reshape(len(blocks), BLK)
  steps = (step ** np.arange(len(blocks))).astype(np.complex64)
  return (x * table[None, :] * steps[:, None]).reshape(-1, DEC).mean(1)


def _movavg(v: np.ndarray, n: int) -> np.ndarray:
  c = np.cumsum(np.concatenate([[0.0], v]))
  out = np.zeros(len(v))
  h = n // 2
  out[h:len(v) - n + h + 1] = (c[n:] - c[:-n]) / n
  return out


def _tones(y: np.ndarray) -> tuple[float, float]:
  n = 1 << int(np.floor(np.log2(len(y))))
  X = np.abs(np.fft.fftshift(np.fft.fft(y[:n] * np.hanning(n)))) ** 2
  f = np.fft.fftshift(np.fft.fftfreq(n, 1 / FS2))
  X = np.where(np.abs(f) < 45e3, np.convolve(X, np.ones(9) / 9, "same"), 0)
  i1 = int(np.argmax(X))
  i2 = int(np.argmax(np.where(np.abs(f - f[i1]) > 12e3, X, 0)))
  lo, hi = sorted((f[i1], f[i2]))
  return float(lo), float(hi)


def soft(y: np.ndarray) -> np.ndarray:
  """Per sample: +1 = upper tone, -1 = lower tone (each tone's energy over one chip)."""
  lo, hi = _tones(y)
  t = np.arange(len(y)) / FS2
  n = int(round(CHIP))
  e = []
  for f in (lo, hi):
    z = y * np.exp(-2j * np.pi * f * t)
    e.append(_movavg(z.real, n) ** 2 + _movavg(z.imag, n) ** 2)
  return (e[1] - e[0]) / (e[1] + e[0] + 1e-9)


def _timing(d: np.ndarray):
  """Chip period and phase: zero crossings sit on chip edges, so on a circle of one chip they bunch at one angle,
  while noise crossings spread out and cancel."""
  s = d > 0
  z = np.flatnonzero(s[1:] != s[:-1]).astype(float) + 0.5
  if len(z) < 50:
    return None
  lo, hi = CHIP * 0.97, CHIP * 1.03
  best = None
  for _ in range(3):                     # coarse, then finer around the best
    best = None
    for T in np.linspace(lo, hi, 41):
      m = np.mean(np.exp(2j * np.pi * z / T))
      if best is None or abs(m) > best[0]:
        best = (abs(m), T, m)
    step = (hi - lo) / 40
    lo, hi = best[1] - step, best[1] + step
  _, T, m = best
  return (np.angle(m) / (2 * np.pi)) * T % T, T, z


def soft_bits(d: np.ndarray) -> np.ndarray:
  """Manchester soft bits (> 0 = '1', sent as high-low), with the chip clock followed through the burst."""
  tm = _timing(d)
  if tm is None:
    return np.zeros(0)
  phi, T, z = tm
  W = 64 * T
  cents, phs, prev = [], [], phi
  for a in np.arange(0, len(d), W / 2):
    zz = z[(z >= a) & (z < a + W)]
    if len(zz) < 12:
      continue
    ph = (np.angle(np.mean(np.exp(2j * np.pi * zz / T))) / (2 * np.pi)) * T
    ph = prev + ((ph - prev + T / 2) % T - T / 2)     # the nearest to the window before
    cents.append(a + W / 2)
    phs.append(ph)
    prev = ph
  if not cents:
    cents, phs = [0.0], [phi]
  base = np.arange(int(len(d) / T) + 2) * T + T / 2
  pos = base + np.interp(base, cents, phs)
  c = d[pos[(pos >= 0) & (pos < len(d) - 1)].astype(int)]
  best = None
  for off in (0, 1):                     # which chips pair up into bits
    a, b = c[off:-1:2], c[off + 1::2]
    m = min(len(a), len(b))
    sc = float(np.sum(np.abs(a[:m] - b[:m])))
    if best is None or sc > best[0]:
      best = (sc, a[:m] - b[:m])
  return best[1]


def _tmpl(bits: str) -> np.ndarray:
  return np.array([1.0 if b == "1" else -1.0 for b in bits])


def _fold(corr: np.ndarray, reps: int) -> np.ndarray:
  """sum of corr[s + k*FRAME] for k < reps, for every s < FRAME (one reshape, no Python loop)."""
  n = reps * FRAME
  c = np.zeros(n)
  c[:min(n, len(corr))] = corr[:n]
  return c.reshape(reps, FRAME).sum(0)


def id_bits(fob_id: str) -> str:
  return format(int(fob_id, 16), f"0{ID_BITS}b")


def norm_id(bits: str) -> str:
  """The ID block as 9 hex digits, always in its 1-first form (the fob sends it either way round)."""
  if bits[0] == "0":
    bits = "".join("1" if c == "0" else "0" for c in bits)
  return f"{int(bits, 2):09x}"


def frame_of(y: np.ndarray, ids: list[str]) -> dict | None:
  """-> {"rep", "raw_id", "id", "m", "frame"} or None. The frame's start comes from the preamble folded over the
  repeats, plus each known ID at its place (far stronger than the 10-bit preamble alone); then the repeats are
  added up bit by bit - noise cancels, the frame doesn't."""
  v = soft_bits(soft(y))
  if len(v) < FRAME + 44:
    return None
  v = v / (np.median(np.abs(v)) + 1e-9)
  reps = max(1, len(v) // FRAME)
  base = _fold(np.correlate(v, _tmpl(PRE_BITS), "valid"), reps)
  best = (float(np.max(base)), int(np.argmax(base)))
  for fid in ids:
    ci = np.correlate(v, _tmpl(id_bits(fid)), "valid")
    if len(ci) <= ID_AT:
      continue
    sc = base + _fold(np.abs(ci[ID_AT:]), reps)
    if float(np.max(sc)) > best[0]:
      best = (float(np.max(sc)), int(np.argmax(sc)))
  s0 = best[1]
  segs = [v[s:s + FRAME] for s in range(s0, len(v) - FRAME + 1, FRAME)]
  if not segs:
    return None
  bits = "".join("1" if x > 0 else "0" for x in np.sum(segs, 0))
  got = bits[ID_AT:ID_AT + ID_BITS]
  match, m = None, 0.0
  for fid in ids:
    same = sum(a == b for a, b in zip(got, id_bits(fid), strict=False)) / ID_BITS
    same = max(same, 1 - same)
    if same > m:
      match, m = fid, same
  return {"rep": len(segs), "raw_id": norm_id(got), "id": match if m >= 0.9 else None, "m": round(m, 3),
          "frame": f"{int(bits, 2):064x}"}


def decode(blocks: list[bytes], ch: int, ids: list[str]) -> dict | None:
  return frame_of(baseband(blocks, ch), ids)


class Listener:
  """Block by block, each channel on its own (a blip on one never hides a press on the other): burst start / hold /
  end, decode jobs handed to a worker."""
  def __init__(self, ids, emit, decode_fn=decode):
    self.ids = list(ids)
    self.emit = emit
    self.decode_fn = decode_fn
    self.blocks_in = 0
    self.pre = deque(maxlen=PRE_BLOCKS)
    self.cur = [None, None]
    self.bid = 0
    self.jobs = queue.Queue()
    self.ready = False
    self.anchor = None              # time.monotonic() of block 0 as the radio made it (the least lag lately)
    self.anchors = deque(maxlen=LAG_WINDOW)
    self.sec_min = None
    self.found = set()              # bursts whose early try already matched a fob: no full try

  def lag(self) -> float:
    return time.monotonic() - (self.anchor + self.blocks_in * BLK / FS) if self.anchor is not None else 0.0

  def _submit(self, c, early=False):
    if early:
      if self.ids:
        self.jobs.put((c["b"], c["ch"], list(c["blocks"]), time.monotonic(), c["t0"], self.lag(), True, c["pk"]))
      return
    if not c["sent"]:
      c["sent"] = True
      self.jobs.put((c["b"], c["ch"], list(c["blocks"]), time.monotonic(), c["t0"], self.lag(), False, c["pk"]))

  def feed(self, raw: bytes) -> None:
    if not self.ready:
      self.ready = True
      self.emit({"e": "ready"})
    self.blocks_in += 1
    a = time.monotonic() - self.blocks_in * BLK / FS
    self.sec_min = a if self.sec_min is None else min(self.sec_min, a)
    if self.blocks_in % 100 == 0:
      self.anchors.append(self.sec_min)
      self.sec_min = None
    self.anchor = min([*self.anchors, a] + ([self.sec_min] if self.sec_min is not None else []))
    if self.blocks_in <= SETTLE_BLOCKS:
      return
    p = chan_power(raw)
    for ch in (0, 1):
      c = self.cur[ch]
      if c is None:
        if p[ch] > ON_DB:
          self.bid += 1
          self.cur[ch] = {"b": self.bid, "ch": ch, "blocks": list(self.pre) + [raw], "n": 1, "quiet": 0, "sent": False,
                          "t0": round(self.anchor + (self.blocks_in - 1) * BLK / FS, 3), "pk": p[ch]}
        continue
      c["n"] += 1
      c["pk"] = max(c["pk"], p[ch])
      if len(c["blocks"]) < PRE_BLOCKS + DECODE_BLOCKS:
        c["blocks"].append(raw)
        if c["n"] in EARLY_AT:
          self._submit(c, early=True)
      elif not c["sent"]:
        self._submit(c)
      if c["n"] == HOLD_BLOCKS:
        self.emit({"e": "hold", "b": c["b"]})
      elif c["n"] > HOLD_BLOCKS and (c["n"] - HOLD_BLOCKS) % PULSE_BLOCKS == 0:
        self.emit({"e": "on", "b": c["b"], "ms": c["n"] * 10})
      c["quiet"] = c["quiet"] + 1 if p[ch] < OFF_DB else 0
      if c["quiet"] >= OFF_BLOCKS or c["n"] >= MAX_BURST_BLOCKS:
        self.cur[ch] = None
        if c["n"] - c["quiet"] < MIN_BLOCKS:
          continue                                # too short for a fob: not a word, not a decode
        self._submit(c)
        self.emit({"e": "end", "b": c["b"], "ms": (c["n"] - c["quiet"]) * 10})
    self.pre.append(raw)

  def work(self) -> None:
    while True:
      job = self.jobs.get()
      if job is None:
        return
      b, ch, blocks, t, t0, lag, early, pk = job
      if b in self.found:
        continue                                  # the early try matched: done
      if time.monotonic() - t > STALE_S:          # behind: skip it, the newer ones matter
        self.emit({"e": "burst", "b": b, "ch": ch, "rep": 0, "raw_id": None, "id": None, "m": 0.0, "frame": None, "stale": True})
        continue
      d0 = time.monotonic()
      try:
        r = self.decode_fn(blocks, ch, self.ids)
      except Exception as e:      # a bad burst never stops the listener
        r = None
        self.emit({"e": "error", "b": b, "error": str(e)[:120]})
      if early:
        if not r or not r.get("id"):
          continue                                # no match yet: the full try decides
        self.found.add(b)
        if len(self.found) > 64:
          self.found = set(sorted(self.found)[-32:])
      self.emit({"e": "burst", "b": b, "ch": ch, **(r or {"rep": 0, "raw_id": None, "id": None, "m": 0.0, "frame": None}),
                 "t0": t0, "dec_ms": round((time.monotonic() - d0) * 1000), "lag_ms": round(lag * 1000), "early": early,
                 "db": round(float(pk), 1)})


def main(argv: list[str]) -> None:
  ids = [a.lower() for a in argv if len(a) == 9 and all(c in "0123456789abcdefABCDEF" for c in a)]
  lock = threading.Lock()
  out = sys.stdout

  def emit(d):
    with lock:
      out.write(json.dumps(d, separators=(",", ":")) + "\n")
      out.flush()

  lis = Listener(ids, emit)
  th = threading.Thread(target=lis.work, daemon=True)
  th.start()
  inp = sys.stdin.buffer
  while True:
    raw = inp.read(2 * BLK)
    if raw is None or len(raw) < 2 * BLK:
      break
    lis.feed(raw)
  lis.jobs.put(None)
  th.join(timeout=5)


if __name__ == "__main__":
  main(sys.argv[1:])
