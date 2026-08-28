from __future__ import annotations

import backend.main as main


def test_web_ads_are_blank_by_default(monkeypatch):
    monkeypatch.delenv("WEB_ADS_ENABLED", raising=False)
    monkeypatch.delenv("ADSENSE_VERIFY_ENABLED", raising=False)
    monkeypatch.delenv("ADS_PREVIEW_MODE", raising=False)

    assert main.adsense_head_markup() == ""
    diagnostics = main.ads_diagnostics()
    assert diagnostics["web_ads_enabled"] is False
    assert diagnostics["preview_mode"] is False
    assert diagnostics["verification_ready"] is False


def test_web_ads_require_explicit_enablement(monkeypatch):
    monkeypatch.setenv("WEB_ADS_ENABLED", "true")
    monkeypatch.setenv("ADSENSE_VERIFY_ENABLED", "true")

    markup = main.adsense_head_markup()
    assert "google-adsense-account" in markup
    assert "adsbygoogle.js" in markup
    assert main.ads_diagnostics()["verification_ready"] is True
