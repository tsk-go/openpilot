import pytest

from openpilot.starpilot.system.starview.techstream import link as link_mod
from openpilot.starpilot.system.starview.techstream.link import (DiagLink, EcuRejectedError, MalformedResponseError, NoResponseError,
                                                                 expect_positive, read_error_text)

from .fakes import FakeEcu, FakePanda

ELM327 = 3  # only used to check it's passed through


class OneFramePerPollPanda(FakePanda):
  """Hands out one frame per can_recv: an ECU sending consecutive frames one by one at its STmin."""

  def can_recv(self):
    return [self._rx.pop(0)] if self._rx else []


def make_link(ecus, **kwargs):
  panda = FakePanda(ecus)
  kwargs.setdefault("timeout", 0.05)
  return panda, DiagLink(panda, elm327_mode=ELM327, heartbeat_thread=False, **kwargs)


class TestOpen:
  def test_sets_elm327_without_obd_multiplexing(self):
    panda, _ = make_link({})
    # param 1 = don't switch bus 1 to the OBD port: we use bus 0 on the camera harness
    assert panda.safety_modes == [(ELM327, 1)]

  def test_close_releases_panda(self):
    panda, link = make_link({})
    link.close()
    assert panda.closed


class TestRequest:
  def test_single_frame_direct_ecu(self):
    _, link = make_link({(0x7C0, None): FakeEcu({b"\x21\xa7": b"\x61\xa7\x12\x34"})})
    assert link.request(0x7C0, None, b"\x21\xa7") == b"\x61\xa7\x12\x34"

  def test_gateway_sub_address_multi_frame_both_ways(self):
    # a 10-byte write request has to go out segmented; a 12-byte answer has to come in segmented, every frame starting
    # with sub-address 0x40
    request = bytes.fromhex("3b11") + bytes(range(8))
    response = bytes.fromhex("6111") + bytes(range(10))
    ecu = FakeEcu({request: response})
    panda, link = make_link({(0x750, 0x40): ecu})
    assert link.request(0x750, 0x40, request) == response
    assert ecu.requests == [request]
    assert all(dat[0] == 0x40 for addr, dat, _ in panda.sent if addr == 0x750)

  def test_waits_through_response_pending(self):
    ecu = FakeEcu({b"\x3b\x12\x01": [b"\x7f\x3b\x78", b"\x7b\x12"]})
    _, link = make_link({(0x750, 0x40): ecu})
    assert link.request(0x750, 0x40, b"\x3b\x12\x01") == b"\x7b\x12"

  def test_negative_response_is_returned_not_raised(self):
    # reading / clearing codes moves on to the next command depending on the NRC, so negative answers go back as-is
    _, link = make_link({(0x7E0, None): FakeEcu({b"\x13": b"\x7f\x13\x11"})})
    assert link.request(0x7E0, None, b"\x13") == b"\x7f\x13\x11"

  def test_silent_ecu_raises_no_response(self):
    _, link = make_link({})
    with pytest.raises(NoResponseError, match="no response"):
      link.request(0x7E0, None, b"\x3e")

  def test_misnumbered_consecutive_frames_raise_malformed_response(self):
    # the real car's 750/AD answers A8 03 with out-of-order frames and opendbc raises AssertionError; it has to become a
    # bad response that can be handled per ECU
    ecu = FakeEcu({b"\xa8\x03": b"\xe8\x03" + bytes(range(20))}, misnumbered_frames=True)
    _, link = make_link({(0x750, 0xAD): ecu})
    with pytest.raises(MalformedResponseError):
      link.request(0x750, 0xAD, b"\xa8\x03")

  @pytest.mark.parametrize("next_address, next_request, next_response", [
    ((0x750, 0x40), b"\x21\x12", b"\x61\x12\xa0"),   # another ECU behind the gateway: leftover frames have another sub-address
    ((0x750, 0xAD), b"\x19\x02\x8d", b"\x7f\x19\x11"),  # the same ECU: leftover frames must not be glued onto the new answer
  ])
  def test_late_frames_of_malformed_response_do_not_break_next_request(self, next_address, next_request, next_response):
    # on the real car, after the out-of-order frame the ECU keeps sending the rest at its STmin; they arrive during the
    # next request
    sunroof = FakeEcu({b"\xa8\x03": b"\xe8\x03" + bytes(range(60)), b"\x19\x02\x8d": b"\x7f\x19\x11"}, misnumbered_frames=True)
    body = FakeEcu({b"\x21\x12": b"\x61\x12\xa0"})
    panda = OneFramePerPollPanda({(0x750, 0xAD): sunroof, (0x750, 0x40): body})
    link = DiagLink(panda, elm327_mode=ELM327, heartbeat_thread=False, timeout=0.05)
    with pytest.raises(MalformedResponseError):
      link.request(0x750, 0xAD, b"\xa8\x03")
    assert link.request(*next_address, next_request) == next_response

  def test_slow_multi_frame_response_is_not_a_timeout(self, monkeypatch):
    # A8 03 mask tables run to dozens of frames; when the ECU sends them slowly, taking longer than one timeout overall
    # must not count as no response
    response = b"\xe8\x03" + bytes(range(60))
    panda = OneFramePerPollPanda({(0x7C0, None): FakeEcu({b"\xa8\x03": response})})
    link = DiagLink(panda, elm327_mode=ELM327, heartbeat_thread=False, timeout=0.05)
    clock = iter(range(100000))
    monkeypatch.setattr(link_mod.time, "monotonic", lambda: next(clock) * 0.02)
    assert link.request(0x7C0, None, b"\xa8\x03") == response

  def test_heartbeat_sent_while_waiting(self, monkeypatch):
    # with the ignition off the panda goes SILENT after 2 s without a heartbeat; long waits must keep sending them
    ecu = FakeEcu({b"\x3b\x12\x01": [b"\x7f\x3b\x78"]})
    panda = FakePanda({(0x750, 0x40): ecu})
    link = DiagLink(panda, elm327_mode=ELM327, heartbeat_thread=False, timeout=0.05, pending_timeout=0.2)
    clock = iter(range(1000))
    monkeypatch.setattr(link_mod.time, "monotonic", lambda: next(clock) * 0.01)
    with pytest.raises(NoResponseError):
      link.request(0x750, 0x40, b"\x3b\x12\x01")
    assert panda.heartbeats > 0


class TestHelpers:
  def test_read_error_text(self):
    assert read_error_text(NoResponseError("x")) == "no response"
    assert read_error_text(MalformedResponseError("x")) == "bad response"
    assert read_error_text(EcuRejectedError(b"\x22\x22\x70", b"\x7f\x22\x31")) == "NRC 31"
    assert read_error_text(EcuRejectedError(b"\x22\x22\x70", b"\x62\x22\x71\x00")) == "unexpected response"

  def test_rejected_error_message_and_nrc(self):
    exc = EcuRejectedError(b"\x2e\x22\x70\x00", b"\x7f\x2e\x22")
    assert exc.nrc == 0x22 and str(exc) == "ECU rejected 2e22: 7f2e22"

  def test_expect_positive_checks_echo(self):
    _, link = make_link({(0x7C0, None): FakeEcu({b"\x22\x10\x01": b"\x62\x10\x01\xab", b"\x22\x10\x02": b"\x62\x10\x03\xab"})})
    assert expect_positive(link, (0x7C0, None), b"\x22\x10\x01", 3) == b"\xab"
    with pytest.raises(EcuRejectedError) as exc:
      expect_positive(link, (0x7C0, None), b"\x22\x10\x02", 3)
    assert exc.value.nrc is None
