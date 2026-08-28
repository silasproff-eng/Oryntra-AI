import os
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend import database
from backend.main import app
from backend.provider_credentials import credential_status, decrypted_credentials, delete_credential, save_credential


class ProviderCredentialTests(unittest.TestCase):
    def test_keys_are_encrypted_per_user_and_never_in_status_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "oryntra.db")
            with patch.object(database, "DB_PATH", db_path), patch.dict(os.environ, {"ORYNTRA_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode()}, clear=False):
                database.init_db()
                conn = database.get_connection()
                try:
                    for user_id in (10, 20):
                        conn.execute("INSERT INTO users (id, email, password_salt, password_hash) VALUES (?, ?, 'salt', 'hash')", (user_id, f"user{user_id}@example.com"))
                    conn.commit()
                finally:
                    conn.close()
                save_credential(10, "polygon", "polygon-secret-key-123")
                save_credential(20, "polygon", "other-user-secret-key")
                self.assertEqual(decrypted_credentials(10), {"polygon": "polygon-secret-key-123"})
                self.assertEqual(decrypted_credentials(20), {"polygon": "other-user-secret-key"})
                status = credential_status(10)
                self.assertTrue(status["encryption_configured"])
                self.assertTrue(next(row for row in status["providers"] if row["provider"] == "polygon")["saved"])
                self.assertNotIn("polygon-secret-key-123", str(status))
                conn = database.get_connection()
                try:
                    stored = conn.execute("SELECT encrypted_api_key FROM user_provider_credentials WHERE user_id=10").fetchone()[0]
                finally:
                    conn.close()
                self.assertNotEqual(stored, "polygon-secret-key-123")
                delete_credential(10, "polygon")
                self.assertEqual(decrypted_credentials(10), {})

    def test_http_key_storage_is_retired_in_browser_direct_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "oryntra.db")
            environment = {"ORYNTRA_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode()}
            with patch.object(database, "DB_PATH", db_path), patch.dict(os.environ, environment, clear=False), TestClient(app) as client:
                unauthenticated = client.get("/api/auth/provider-credentials")
                self.assertEqual(unauthenticated.status_code, 401)
                signup = client.post(
                    "/api/auth/signup",
                    json={
                        "email": "key-owner@example.com",
                        "password": "long-test-password",
                        "accept_legal": True,
                    },
                )
                self.assertEqual(signup.status_code, 200)
                token = signup.json()["token"]
                headers = {"Authorization": f"Bearer {token}"}
                rejected = client.put(
                    "/api/auth/provider-credentials",
                    headers=headers,
                    json={"provider": "twelvedata", "api_key": "private-user-key-456"},
                )
                self.assertEqual(rejected.status_code, 410)
                self.assertNotIn("private-user-key-456", rejected.text)
                status = client.get("/api/auth/provider-credentials", headers=headers)
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["mode"], "browser_direct")


if __name__ == "__main__":
    unittest.main()
