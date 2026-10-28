# main.py for Raspberry Pi Pico (MicroPython) - relay driver for the Sienna: turn signals + window close.
# Save this file on the Pico as  main.py
#
# Wiring (4-ch 5V relay module, low-level trigger, JD-VCC jumper REMOVED):
#   Pico 3V3(OUT) pin 36 -> module VCC      Pico VBUS pin 40 -> module JD-VCC
#   Pico GND      pin 38 -> module GND
#   GP2 (pin 4) -> IN1 = TL  (left)          GP3 (pin 5) -> IN2 = TR (right)
#   GP4 (pin 6) -> IN3 = WIN (driver's door key switch, LOCK side)
#   Relay COM1/COM2 -> EL ;  NO1 -> TL ; NO2 -> TR   (never use NC)
#   Relay COM3 / NO3 -> the key switch's lock wire and its ground (holding it = holding the key to lock)
#
# Protocol: the comma sends ONE character, repeated at least every 0.5 s:
#   '0' all off   'l' / 'L' left signal (TL)   'r' / 'R' right signal (TR)   'W' window close (key held to lock)
# Fail-safe: no valid character for 1.0 s -> everything off. Never two of them on together.

import select
import sys
import time
from machine import Pin

RELAY_ON, RELAY_OFF = 0, 1          # low-level trigger module: pulling IN low energises the relay
TL = Pin(2, Pin.OUT, value=RELAY_OFF)
TR = Pin(3, Pin.OUT, value=RELAY_OFF)
WIN = Pin(4, Pin.OUT, value=RELAY_OFF)
LED = Pin("LED", Pin.OUT, value=0)
TIMEOUT_MS = 1000

STATES = {'0': (0, 0, 0), 'l': (1, 0, 0), 'L': (1, 0, 0), 'r': (0, 1, 0), 'R': (0, 1, 0), 'W': (0, 0, 1)}

def apply(tl, tr, win):
  if tl + tr + win > 1:              # interlock: only one thing at a time
    tl = tr = win = 0
  TL.value(RELAY_ON if tl else RELAY_OFF)
  TR.value(RELAY_ON if tr else RELAY_OFF)
  WIN.value(RELAY_ON if win else RELAY_OFF)
  LED.value(1 if (tl or tr or win) else 0)

poll = select.poll()
poll.register(sys.stdin, select.POLLIN)
state, last = '0', time.ticks_ms()
apply(0, 0, 0)

while True:
  try:
    while poll.poll(0):
      ch = sys.stdin.read(1)
      if ch in STATES:
        last = time.ticks_ms()
        if ch != state:
          state = ch
          apply(*STATES[state])
    if state != '0' and time.ticks_diff(time.ticks_ms(), last) > TIMEOUT_MS:
      state = '0'
      apply(0, 0, 0)                 # comma went quiet -> release everything
    time.sleep_ms(10)
  except Exception:
    state = '0'
    apply(0, 0, 0)
