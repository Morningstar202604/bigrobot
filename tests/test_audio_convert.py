"""语音转码：wav 直通、缺解码器如实返回 None。"""
from core import audio_convert


def test_wav_passthrough():
    assert audio_convert.to_wav_bytes(b"RIFFxx", "wav") == b"RIFFxx"


def test_silk_without_decoder(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert audio_convert.to_wav_bytes(b"silkdata", "silk") is None


def test_unknown_format(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert audio_convert.to_wav_bytes(b"xx", "xyz") is None
