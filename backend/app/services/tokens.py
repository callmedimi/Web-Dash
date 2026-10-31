"""API Token Management Service (Target Architecture §3 & Step 5.14).

Handles programmatic authentication tokens:
- High-entropy tokens prefixed with 'wbd_'
- Hashed in DB via SHA-256 (plaintext only shown once upon creation)
- Scoped permissions (e.g. 'devices:read', 'jobs:run', '*')
- Configurable expiration (default 30 days) and explicit revocation
- Activity tracking ('last_used_at')
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.models.api_token import ApiToken


def hash_token(raw_token: str) -> str:
    """Return SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


class ApiTokenService:
    """Service for issuing, verifying, revoking, and listing API tokens."""

    @staticmethod
    def create_token(
        user_id: int,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = 30,
        db_session: Optional[Session] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Issue a new API token for the specified user.
        Returns a tuple of (token_dict, raw_token_secret).
        """
        if not name or not name.strip():
            raise ValueError("Token name is required")

        # Generate high-entropy secret
        token_secret = f"wbd_{secrets.token_urlsafe(32)}"
        token_digest = hash_token(token_secret)
        prefix = f"{token_secret[:12]}..."

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = (now + timedelta(days=expires_in_days)) if expires_in_days else None
        effective_scopes = scopes if scopes is not None else ["*"]

        def _do_create(session: Session) -> Dict[str, Any]:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError(f"User #{user_id} not found")

            token_obj = ApiToken(
                name=name.strip(),
                token_hash=token_digest,
                token_prefix=prefix,
                user_id=user_id,
                scopes=effective_scopes,
                revoked=False,
                created_at=now,
                expires_at=expires_at,
            )
            session.add(token_obj)
            session.commit()
            return token_obj.to_dict()

        if db_session:
            token_dict = _do_create(db_session)
        else:
            with get_db_session() as s:
                token_dict = _do_create(s)

        return token_dict, token_secret

    @staticmethod
    def verify_token(
        raw_token: str,
        required_scope: Optional[str] = None,
        db_session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate incoming raw API token, check expiration, revocation, and scope.
        Updates 'last_used_at' timestamp on success.
        Returns dict with user/token context or None if invalid.
        """
        if not raw_token or not isinstance(raw_token, str):
            return None
        cleaned = raw_token.strip()
        if not cleaned.startswith("wbd_"):
            return None

        token_digest = hash_token(cleaned)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        def _do_verify(session: Session) -> Optional[Dict[str, Any]]:
            token = session.query(ApiToken).filter(ApiToken.token_hash == token_digest).first()
            if not token:
                return None

            if not token.is_active():
                return None

            # Verify user account is active
            user = token.user
            if not user or not user.is_active:
                return None

            # Verify required scope if specified
            if required_scope:
                scopes = token.scopes if isinstance(token.scopes, list) else []
                if not ("*" in scopes or "admin" in scopes or required_scope in scopes):
                    return None

            # Update last used timestamp
            token.last_used_at = now
            session.commit()

            return {
                "token_id": token.id,
                "token_name": token.name,
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "scopes": token.scopes if isinstance(token.scopes, list) else [],
            }

        if db_session:
            return _do_verify(db_session)
        with get_db_session() as s:
            return _do_verify(s)

    @staticmethod
    def revoke_token(
        token_id: int,
        user_id: Optional[int] = None,
        db_session: Optional[Session] = None,
    ) -> bool:
        """Revoke an active API token."""
        def _do_revoke(session: Session) -> bool:
            query = session.query(ApiToken).filter(ApiToken.id == token_id)
            if user_id is not None:
                query = query.filter(ApiToken.user_id == user_id)
            token = query.first()
            if not token:
                return False
            token.revoked = True
            session.commit()
            return True

        if db_session:
            return _do_revoke(db_session)
        with get_db_session() as s:
            return _do_revoke(s)

    @staticmethod
    def list_tokens(
        user_id: Optional[int] = None,
        db_session: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """List API tokens (filtered by user_id if provided)."""
        def _do_list(session: Session) -> List[Dict[str, Any]]:
            query = session.query(ApiToken)
            if user_id is not None:
                query = query.filter(ApiToken.user_id == user_id)
            tokens = query.order_by(ApiToken.id.desc()).all()
            return [t.to_dict() for t in tokens]

        if db_session:
            return _do_list(db_session)
        with get_db_session() as s:
            return _do_list(s)
