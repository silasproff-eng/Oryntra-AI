#!/usr/bin/env python3
"""Generate the Fernet key used to encrypt Alpaca OAuth tokens at rest."""
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode("ascii"))
