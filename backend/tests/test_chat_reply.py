"""Tests for the AI reply cleanup (chat.py._clean_reply).

The AI sometimes echoes recommended actions into its summary text as
label + "read" lines, duplicating the action cards the frontend renders.
These tests lock in that the noise is stripped from the final reply.
"""
from __future__ import annotations

from app.ai.chat import _clean_reply


def test_strips_permission_token_lines_and_action_labels():
    text = (
        "Channel Anda memiliki 67 subscriber.\n"
        "Ambil komentar video DbEMzs_p7sY\n"
        "read\n"
        "Ambil komentar video 07PuEFHjOSE\n"
        "read\n"
        "Analisis video teratas untuk CTR & retensi\n"
        "write\n"
    )
    labels = ["Ambil komentar video DbEMzs_p7sY", "Ambil komentar video 07PuEFHjOSE"]
    cleaned = _clean_reply(text, labels)
    assert "read" not in cleaned
    assert "write" not in cleaned
    assert "Ambil komentar video" not in cleaned
    assert "Channel Anda memiliki 67 subscriber." in cleaned


def test_strips_tindakan_yang_disarankan_block():
    text = (
        "Kesimpulan analisis.\n"
        "- Temuan pertama.\n"
        "TINDAKAN YANG DISARANKAN\n"
        "Ambil analitik channel untuk verifikasi data\n"
        "read\n"
        "Analisis video teratas DbEMzs_p7sY untuk CTR & retensi\n"
        "read\n"
    )
    cleaned = _clean_reply(text)
    assert "TINDAKAN YANG DISARANKAN" not in cleaned
    assert "read" not in cleaned
    assert "Ambil analitik channel" not in cleaned
    assert "Kesimpulan analisis." in cleaned
    assert "- Temuan pertama." in cleaned


def test_strips_recommended_actions_variants():
    text = (
        "Ringkasan.\n"
        "RECOMMENDED ACTIONS:\n"
        "Check top video\n"
        "read\n"
        "Berikutnya, lihat laporan lengkap di halaman Dashboard.\n"
    )
    cleaned = _clean_reply(text)
    assert "RECOMMENDED ACTIONS" not in cleaned
    assert "read" not in cleaned
    assert "Ringkasan." in cleaned


def test_keeps_normal_prose_untouched():
    text = "Video terbaik mencapai 2.215 views.\n\nRekomendasi: perbaiki metadata.\n"
    assert _clean_reply(text) == text.strip()


def test_no_actions_passed_is_safe():
    text = "Kesimpulan.\nread\nwrite\n"
    assert _clean_reply(text) == "Kesimpulan."
