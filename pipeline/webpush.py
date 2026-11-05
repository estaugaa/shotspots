"""Minimal Web Push sender (RFC 8291 aes128gcm payload encryption + RFC 8292 VAPID), using only `cryptography`.

The VAPID private key lives in the VAPID_PRIVATE_KEY secret (base64url of the raw 32-byte P-256 scalar).
The matching public key is not secret and is embedded in the app (app/alerts.js) so browsers can subscribe.
"""
import base64, json, os, struct, time
from urllib.parse import urlparse
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SUBJECT = "https://shotspots-eric.netlify.app"


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _hkdf(salt, ikm, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def _raw_pub(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def load_key(b64priv):
    return ec.derive_private_key(int.from_bytes(b64d(b64priv), "big"), ec.SECP256R1())


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    ua_pub = b64d(p256dh)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    eph = ec.generate_private_key(ec.SECP256R1())
    as_pub = _raw_pub(eph)
    ecdh = eph.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(b64d(auth), ecdh, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ct = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + ct


def vapid_header(endpoint, key):
    u = urlparse(endpoint)
    hdr = b64e(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64e(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SUBJECT}).encode())
    signing = f"{hdr}.{claims}".encode()
    r, s = decode_dss_signature(key.sign(signing, ec.ECDSA(hashes.SHA256())))
    jwt = f"{hdr}.{claims}.{b64e(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={b64e(_raw_pub(key))}"


def send(sub: dict, data: dict, key, ttl=6 * 3600, urgency="normal"):
    """Returns the push service's HTTP status (201 ok; 404/410 = subscription gone)."""
    body = encrypt(json.dumps(data).encode(), sub["keys"]["p256dh"], sub["keys"]["auth"])
    r = requests.post(sub["endpoint"], data=body, timeout=30, headers={
        "Authorization": vapid_header(sub["endpoint"], key), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": str(ttl), "Urgency": urgency})
    return r.status_code
