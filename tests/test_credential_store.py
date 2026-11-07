import unittest
from unittest.mock import patch

import credential_store


class WinVaultKeyring:
    priority = 5


class UnsafeKeyring:
    priority = 1


class CredentialStoreTests(unittest.TestCase):
    def test_windows_requires_windows_credential_manager(self):
        with patch.object(credential_store.sys, "platform", "win32"), patch.object(
            credential_store.keyring, "get_keyring", return_value=WinVaultKeyring()
        ):
            self.assertIsInstance(credential_store.ensure_secure_backend(), WinVaultKeyring)

    def test_windows_rejects_unverified_backend(self):
        with patch.object(credential_store.sys, "platform", "win32"), patch.object(
            credential_store.keyring, "get_keyring", return_value=UnsafeKeyring()
        ):
            with self.assertRaises(RuntimeError):
                credential_store.ensure_secure_backend()


if __name__ == "__main__":
    unittest.main()
