"""Story 4.2 (NFR-SEC3) — secrets (provider keys, license token) are never logged,
serialized, or exposed. SecretStr masks in repr/str/model_dump; /health and
license status carry no secret material.
"""

from __future__ import annotations

from datetime import date

from docintel_api.main import app
from docintel_core.config import Settings
from docintel_core.license import License, StubLicenseVerifier, license_status
from fastapi.testclient import TestClient

_SECRET_KEY = "sk-super-secret-provider-key-DO-NOT-LEAK"

client = TestClient(app)


def test_secretstr_masks_provider_and_license_keys() -> None:
    lic = StubLicenseVerifier().issue(License(licensee="A", expiry=date(2030, 1, 1)))
    cfg = Settings(anthropic_api_key=_SECRET_KEY, openai_api_key=_SECRET_KEY, license_key=lic)
    # repr/str never reveal the secret (pydantic SecretStr).
    assert _SECRET_KEY not in repr(cfg)
    assert _SECRET_KEY not in str(cfg)
    # model_dump keeps SecretStr wrapped, not the raw value.
    dumped = str(cfg.model_dump())
    assert _SECRET_KEY not in dumped and lic not in dumped
    # The value is still retrievable at the trust boundary (adapter construction).
    assert cfg.anthropic_api_key is not None
    assert cfg.anthropic_api_key.get_secret_value() == _SECRET_KEY


def test_health_and_license_status_expose_no_secret() -> None:
    lic = StubLicenseVerifier().issue(License(licensee="Acme", expiry=date(2030, 1, 1)))
    body = client.get("/health").text
    assert _SECRET_KEY not in body and "api_key" not in body.lower()
    # license_status is non-secret only — never the token.
    st = license_status(Settings(license_key=lic))
    assert lic not in str(st) and "sig" not in str(st).lower()
