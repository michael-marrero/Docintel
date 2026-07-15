"""Story 4.4 (AD-18) — offline-verifiable licensing: stub roundtrip, forgery
rejection, offline expiry/scope enforcement, and the Ed25519 real path.

Everything here runs OFFLINE — no network, no vendor call. The Ed25519 round-trip
skips when ``cryptography`` is absent (mirrors the real-key LLM tests skipping
without keys); the stub + enforcement logic run on stdlib alone.
"""

from __future__ import annotations

from datetime import date

import pytest
from docintel_core.config import Settings
from docintel_core.license import (
    License,
    LicenseError,
    StubLicenseVerifier,
    encode_token,
    enforce_license,
    license_status,
    make_license_verifier,
)


def _lic(**over) -> License:
    base = {"licensee": "Acme Capital", "expiry": date(2030, 1, 1), "tier": "any", "seats": 5}
    base.update(over)
    return License(**base)


def test_stub_issue_verify_roundtrip() -> None:
    v = StubLicenseVerifier()
    token = v.issue(_lic())
    got = v.verify(token)
    assert got.licensee == "Acme Capital" and got.seats == 5


def test_forged_or_malformed_token_rejected() -> None:
    v = StubLicenseVerifier()
    with pytest.raises(LicenseError):
        v.verify("not-a-token")
    # Tamper the signature → rejected.
    token = v.issue(_lic())
    payload_b64, _sig = token.split(".", 1)
    with pytest.raises(LicenseError, match="signature invalid"):
        v.verify(f"{payload_b64}.{'A' * 43}=")


def test_no_license_is_a_demo_grant() -> None:
    # Offline-first default: no license configured → enforce returns None (granted).
    assert enforce_license(Settings(license_key=None)) is None
    st = license_status(Settings(license_key=None))
    assert st["licensed"] is True and st["source"] == "unlicensed-demo"


def test_expired_license_is_enforced_offline() -> None:
    token = StubLicenseVerifier().issue(_lic(expiry=date(2020, 1, 1)))
    cfg = Settings(license_key=token)
    with pytest.raises(LicenseError, match="expired"):
        enforce_license(cfg, today=date(2026, 7, 15))
    assert license_status(cfg, today=date(2026, 7, 15))["licensed"] is False


def test_tier_scope_is_enforced() -> None:
    # A license scoped to 'open' does not authorize a 'sealed' deployment.
    token = StubLicenseVerifier().issue(_lic(tier="open"))
    cfg = Settings(license_key=token, tier="sealed")
    with pytest.raises(LicenseError, match="does not authorize"):
        enforce_license(cfg, today=date(2026, 7, 15))
    # 'any'-tier license authorizes either tier.
    any_token = StubLicenseVerifier().issue(_lic(tier="any"))
    assert enforce_license(Settings(license_key=any_token, tier="sealed"), today=date(2026, 7, 15))


def test_valid_license_verifies_and_reports_status() -> None:
    token = StubLicenseVerifier().issue(
        _lic(licensee="Northwind", tier="sealed", expiry=date(2031, 1, 1))
    )
    cfg = Settings(license_key=token, tier="sealed")
    lic = enforce_license(cfg, today=date(2026, 7, 15))
    assert lic is not None and lic.licensee == "Northwind"
    st = license_status(cfg, today=date(2026, 7, 15))
    assert st == {
        "licensed": True,
        "source": "verified",
        "licensee": "Northwind",
        "tier": "sealed",
        "expiry": "2031-01-01",
    }


def test_seam_selects_stub_without_public_key() -> None:
    assert make_license_verifier(Settings()).name == "stub-hmac"
    assert make_license_verifier(Settings(license_public_key_hex="00" * 32)).name == "ed25519"


def test_ed25519_real_path_roundtrip() -> None:
    pytest.importorskip("cryptography")  # skip if the real-adapter dep is absent
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from docintel_core.license import Ed25519LicenseVerifier, _payload_bytes

    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes_raw().hex()
    lic = _lic(licensee="Sealed Buyer", tier="sealed")
    payload = _payload_bytes(lic)
    token = encode_token(payload, priv.sign(payload))

    verifier = Ed25519LicenseVerifier(pub_hex)
    assert verifier.verify(token).licensee == "Sealed Buyer"
    # A different key cannot forge a valid token.
    other_hex = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    with pytest.raises(LicenseError, match="Ed25519"):
        Ed25519LicenseVerifier(other_hex).verify(token)
