from __future__ import annotations

import sys

import keyring


def ensure_secure_backend():
    backend = keyring.get_keyring()
    backend_name = backend.__class__.__name__
    if sys.platform == "win32":
        if backend_name != "WinVaultKeyring":
            raise RuntimeError(
                "Windows Credential Manager kullanılamıyor. API anahtarı güvensiz bir yedek depoya yazılmadı. "
                f"Algılanan keyring backend: {backend_name}"
            )
    elif backend_name in {"FailKeyring", "ChainerBackend"} or getattr(backend, "priority", 0) <= 0:
        raise RuntimeError(f"Güvenli sistem kimlik bilgisi deposu kullanılamıyor: {backend_name}")
    return backend


def get_password(service: str, username: str):
    ensure_secure_backend()
    return keyring.get_password(service, username)


def set_password(service: str, username: str, password: str) -> None:
    ensure_secure_backend()
    keyring.set_password(service, username, password)


def delete_password(service: str, username: str) -> None:
    ensure_secure_backend()
    keyring.delete_password(service, username)
