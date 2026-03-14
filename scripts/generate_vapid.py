#!/usr/bin/env python
"""scripts/generate_vapid.py — Generate VAPID key pair for Web Push.

Run once and add the output to your .env file:

    python scripts/generate_vapid.py
"""
import base64

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()

raw_pub = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
raw_priv = vapid.private_key.private_bytes(
    Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
)

public_key = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
# Store private key as PEM (base64-encoded for easy .env storage)
private_key = base64.urlsafe_b64encode(raw_priv).rstrip(b"=").decode()

print("Add these to your .env file:")
print()
print(f"VAPID_PUBLIC_KEY={public_key}")
print(f"VAPID_PRIVATE_KEY={private_key}")
print(f"VAPID_SUBJECT=mailto:admin@example.com")
print()
print("The public key is also needed in the browser (already served at /notifications/vapid-public-key).")
