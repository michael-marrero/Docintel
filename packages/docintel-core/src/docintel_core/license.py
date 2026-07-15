"""Offline-verifiable licensing (Epic 4, Story 4.4, AD-18).

A license is a signed token ``<payload_b64>.<sig_b64>`` — ``payload`` is a JSON
``License`` (licensee, expiry, tier/seat scope); ``sig`` is a signature over the
payload bytes. Verification is **entirely offline** against a bundled public key
and there is **NO vendor network call** at issue, startup, or query time
(FR-E2 / NFR-SEC2/SEC4). Enforcement (expiry + scope) happens once at startup.

The verifier is an **adapter seam** (AD-3), mirroring the LLM provider seam:

* ``Ed25519LicenseVerifier`` — the real, unforgeable path: an asymmetric
  signature verified against the vendor's public key (the vendor holds the
  private key; a deployment can verify but cannot forge). Uses ``cryptography``,
  imported lazily so the offline suite needs no native build.
* ``StubLicenseVerifier`` — the deterministic, offline-first default (AD-2/AD-8),
  like ``LLM_PROVIDER=stub``. It uses a symmetric HMAC over a public dev key, so
  it is **NOT forge-resistant** — it exists so ``docker compose up`` runs
  out-of-the-box without key material, NOT as the production trust boundary.

A license/secret key is **never logged and never embedded in an image**
(NFR-SEC3): only the licensee/tier/expiry (non-secret) are logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from docintel_core.config import Settings

__all__ = [
    "Ed25519LicenseVerifier",
    "License",
    "LicenseError",
    "LicenseVerifier",
    "StubLicenseVerifier",
    "encode_token",
    "enforce_license",
    "make_license_verifier",
]

# Public dev key for the STUB verifier only. Symmetric → forgeable; dev/demo only.
_STUB_DEV_KEY: bytes = b"docintel-dev-license-v1"


class LicenseError(RuntimeError):
    """A license is missing-when-required, malformed, forged, expired, or out of scope."""


class License(BaseModel):
    """The signed license payload. Frozen (the verified token is immutable)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    licensee: str
    expiry: date
    """Inclusive last valid day (ISO ``YYYY-MM-DD``)."""
    tier: str = "any"
    """``open`` | ``sealed`` | ``any`` — the tier this license authorizes."""
    seats: int = 1


def _payload_bytes(lic: License) -> bytes:
    """Canonical payload bytes (sort_keys → a stable signing surface)."""
    return json.dumps(lic.model_dump(mode="json"), sort_keys=True).encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


def encode_token(payload: bytes, sig: bytes) -> str:
    """Frame a license token from payload + signature bytes."""
    return f"{_b64(payload)}.{_b64(sig)}"


def _split_token(token: str) -> tuple[bytes, bytes]:
    try:
        p_b64, s_b64 = token.strip().split(".", 1)
        return _unb64(p_b64), _unb64(s_b64)
    except Exception as exc:  # missing dot / malformed base64
        raise LicenseError("malformed license token") from exc


@runtime_checkable
class LicenseVerifier(Protocol):
    """Port: verify a token's signature offline and return its ``License``.

    Raises ``LicenseError`` on a malformed or forged token. Does NOT check
    expiry/scope — that is ``enforce_license``'s job (separation of signature
    trust from policy)."""

    name: str

    def verify(self, token: str) -> License: ...


class StubLicenseVerifier:
    """Deterministic, offline-first default (dev/demo). HMAC over a public dev key
    — offline but symmetric, so NOT forge-resistant. See module docstring."""

    name = "stub-hmac"

    def verify(self, token: str) -> License:
        payload, sig = _split_token(token)
        expected = hmac.new(_STUB_DEV_KEY, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise LicenseError("license signature invalid (stub verifier)")
        return License.model_validate(json.loads(payload))

    def issue(self, lic: License) -> str:
        """Dev-only issuance (stub). Real issuance uses the vendor Ed25519 private key."""
        payload = _payload_bytes(lic)
        sig = hmac.new(_STUB_DEV_KEY, payload, hashlib.sha256).digest()
        return encode_token(payload, sig)


class Ed25519LicenseVerifier:
    """Real, unforgeable path: Ed25519 signature verified against the vendor's
    public key. ``cryptography`` is imported lazily (no native build for the stub
    path / offline suite)."""

    name = "ed25519"

    def __init__(self, public_key_hex: str) -> None:
        self._public_key_hex = public_key_hex

    def verify(self, token: str) -> License:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as exc:  # pragma: no cover - real-adapter dep
            raise LicenseError(
                "Ed25519 license verification requires the 'cryptography' package"
            ) from exc
        payload, sig = _split_token(token)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(self._public_key_hex))
        try:
            pub.verify(sig, payload)
        except InvalidSignature as exc:
            raise LicenseError("license signature invalid (Ed25519)") from exc
        return License.model_validate(json.loads(payload))


def make_license_verifier(cfg: Settings) -> LicenseVerifier:
    """AD-3 seam: the real Ed25519 verifier when a public key is bundled, else the
    deterministic stub (offline-first default, like ``LLM_PROVIDER=stub``)."""
    if cfg.license_public_key_hex:
        return Ed25519LicenseVerifier(cfg.license_public_key_hex)
    return StubLicenseVerifier()


def enforce_license(cfg: Settings, *, today: date | None = None) -> License | None:
    """Verify + enforce the license entirely offline (AD-18). Returns the verified
    ``License`` (or ``None`` when no license is configured — the offline-first
    default grants the demo, like stub mode). Raises ``LicenseError`` when a
    CONFIGURED license is forged, expired, or out of tier scope — the documented
    enforcement, done WITHOUT transmitting anything to the vendor.

    ``today`` is injectable for deterministic tests.
    """
    token = cfg.license_key.get_secret_value() if cfg.license_key is not None else None
    if not token:
        return None  # no license configured → demo grant (offline-first default)

    lic = make_license_verifier(cfg).verify(token)  # signature trust (offline)

    now = today or date.today()
    if lic.expiry < now:
        raise LicenseError(f"license expired {lic.expiry.isoformat()} (today {now.isoformat()})")
    if lic.tier not in ("any", cfg.tier):
        raise LicenseError(f"license tier {lic.tier!r} does not authorize the {cfg.tier!r} tier")
    return lic


def license_status(cfg: Settings, *, today: date | None = None) -> dict[str, Any]:
    """Non-secret license summary for operability surfaces (/ready). Never includes
    the token/signature. On an enforcement failure, reports ``licensed: false`` +
    the reason rather than raising — a status probe should not 500."""
    try:
        lic = enforce_license(cfg, today=today)
    except LicenseError as exc:
        return {"licensed": False, "reason": str(exc)}
    if lic is None:
        return {"licensed": True, "source": "unlicensed-demo", "licensee": None}
    return {
        "licensed": True,
        "source": "verified",
        "licensee": lic.licensee,
        "tier": lic.tier,
        "expiry": lic.expiry.isoformat(),
    }
