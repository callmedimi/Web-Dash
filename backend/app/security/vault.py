"""Credential Vault and Encryption using Fernet (Target Architecture §3, §5 & Step 2.8 - F-06)."""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.device import Credential, Device

logger = logging.getLogger(__name__)


def get_vault_key(require_prod: bool = True) -> bytes:
    """
    Retrieve or initialize the 32-byte Fernet key.
    - If WEBDASH_VAULT_KEY (or VAULT_KEY) is set as an env var or points to a file, use it.
    - If in production mode (and not in testing mode), missing key raises RuntimeError.
    - Otherwise (development/testing), generate/persist key to .vault_key in data_dir.
    """
    key_str = settings.get_vault_key()
    if key_str:
        try:
            raw_key = key_str.encode("utf-8")
            Fernet(raw_key)
            return raw_key
        except Exception as exc:
            raise ValueError(f"Invalid Fernet key provided in WEBDASH_VAULT_KEY: {exc}")

    is_prod = (settings.env == "production") and not os.environ.get("TESTING")
    if is_prod and require_prod:
        raise RuntimeError(
            "WEBDASH_VAULT_KEY is required in production mode. Set it via env var or file path."
        )

    # In dev/testing: load or generate local .vault_key
    data_dir = settings.get_data_dir()
    key_file = os.path.join(data_dir, ".vault_key")
    if os.path.isfile(key_file):
        try:
            with open(key_file, "rb") as f:
                stored = f.read().strip()
                Fernet(stored)
                return stored
        except Exception:
            pass

    # Generate new key
    new_key = Fernet.generate_key()
    try:
        with open(key_file, "wb") as f:
            f.write(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    except Exception as exc:
        logger.warning("Could not persist .vault_key file: %s", exc)

    return new_key


def encrypt_secret(plaintext: str, key: Optional[bytes] = None) -> str:
    """Encrypt a plaintext secret using Fernet."""
    if not plaintext:
        return ""
    fernet_key = key or get_vault_key(require_prod=False)
    f = Fernet(fernet_key)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, key: Optional[bytes] = None) -> str:
    """Decrypt a ciphertext secret using Fernet."""
    if not ciphertext:
        return ""
    fernet_key = key or get_vault_key(require_prod=False)
    f = Fernet(fernet_key)
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


class VaultService:
    """Vault database management operations."""

    @staticmethod
    def create_credential(
        session: Session,
        name: str,
        kind: str,
        secret: str,
        username: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Credential:
        """Create a new encrypted credential in DB."""
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Credential name cannot be empty")
        if not secret:
            raise ValueError("Credential secret cannot be empty")
        if not kind:
            kind = "ssh_password"

        meta_info = dict(meta or {})
        if username:
            meta_info["username"] = username.strip()

        encrypted = encrypt_secret(secret)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        cred = Credential(
            name=clean_name,
            kind=kind,
            secret_encrypted=encrypted,
            meta_info=meta_info,
            created_at=now,
        )
        session.add(cred)
        session.flush()
        return cred

    @staticmethod
    def list_credentials(session: Session) -> List[Dict[str, Any]]:
        """List all credentials (safe, no secret)."""
        creds = session.query(Credential).order_by(Credential.id.asc()).all()
        return [c.to_dict() for c in creds]

    @staticmethod
    def get_credential(session: Session, cred_id: int) -> Optional[Dict[str, Any]]:
        """Get safe metadata for a single credential."""
        cred = session.query(Credential).filter(Credential.id == cred_id).first()
        return cred.to_dict() if cred else None

    @staticmethod
    def get_decrypted_secret(session: Session, cred_id: int) -> Tuple[str, str]:
        """
        Internal worker only: Decrypt and return (username, plaintext_secret).
        Raises ValueError if credential not found.
        """
        cred = session.query(Credential).filter(Credential.id == cred_id).first()
        if not cred:
            raise ValueError(f"Credential {cred_id} not found")
        username = cred.meta_info.get("username", "") if cred.meta_info else ""
        secret = decrypt_secret(cred.secret_encrypted)
        return username, secret

    @staticmethod
    def update_credential(
        session: Session,
        cred_id: int,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        username: Optional[str] = None,
        secret: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update or rotate a credential."""
        cred = session.query(Credential).filter(Credential.id == cred_id).first()
        if not cred:
            return None

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Credential name cannot be empty")
            cred.name = clean_name

        if kind is not None:
            cred.kind = kind.strip()

        meta_info = dict(cred.meta_info or {})
        if meta is not None:
            meta_info.update(meta)
        if username is not None:
            meta_info["username"] = username.strip()
        cred.meta_info = meta_info

        if secret is not None and secret != "":
            cred.secret_encrypted = encrypt_secret(secret)

        session.flush()
        return cred.to_dict()

    @staticmethod
    def delete_credential(session: Session, cred_id: int) -> bool:
        """Delete a credential and unbind it from any devices."""
        cred = session.query(Credential).filter(Credential.id == cred_id).first()
        if not cred:
            return False
        session.query(Device).filter(Device.credential_id == cred_id).update(
            {"credential_id": None}
        )
        session.delete(cred)
        session.flush()
        return True

    @staticmethod
    def rotate_all(session: Session, old_key: bytes, new_key: bytes) -> int:
        """Re-encrypt all stored credentials matching old_key to new_key."""
        creds = session.query(Credential).all()
        count = 0
        for c in creds:
            try:
                plaintext = decrypt_secret(c.secret_encrypted, key=old_key)
                c.secret_encrypted = encrypt_secret(plaintext, key=new_key)
                count += 1
            except Exception:
                continue
        session.flush()
        return count

    @staticmethod
    def attach_to_device(session: Session, cred_id: int, device_name: str) -> bool:
        """Attach a credential to a device by name."""
        device = session.query(Device).filter(Device.name == device_name).first()
        if not device:
            return False
        device.credential_id = cred_id
        session.flush()
        return True

    @staticmethod
    def resolve_credentials(
        session: Session,
        credential_id: Optional[int] = None,
        device_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve credentials either from direct credential_id or from the device's attached credential_id.
        Returns dict with {"id": ..., "name": ..., "kind": ..., "username": ..., "password": ...} or None.
        """
        target_cred_id = credential_id
        if not target_cred_id and device_name:
            device = session.query(Device).filter(Device.name == device_name).first()
            if device and device.credential_id:
                target_cred_id = device.credential_id

        if not target_cred_id:
            return None

        cred = session.query(Credential).filter(Credential.id == target_cred_id).first()
        if not cred:
            return None

        username = cred.meta_info.get("username", "") if cred.meta_info else ""
        secret = decrypt_secret(cred.secret_encrypted)
        return {
            "id": cred.id,
            "name": cred.name,
            "kind": cred.kind,
            "username": username,
            "password": secret,
        }
