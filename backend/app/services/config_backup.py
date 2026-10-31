"""Configuration Backup, Normalization, Encryption, and Diff Service (Target Architecture §3, Plan 06 Step 4.3).

Provides:
- Normalization of Huawei VRP CLI output (strips volatile timestamps, pagination, banners).
- Deterministic SHA-256 checksumming (skips duplicate DB rows if configuration is unchanged).
- AES-128-CBC / HMAC-SHA256 Encryption at rest via Fernet vault key.
- Unified and structured JSON diff generation for side-by-side or hunk inspection.
- Snapshot retention enforcement (keeps latest 30 snapshots + 1/month up to 12 months).
"""
import re
import difflib
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from backend.app.models.config_change import ConfigSnapshot, ChangeRequest
from backend.app.models.job import Job
from backend.app.models.device import Device
from backend.app.security.vault import get_vault_key

# Volatile headers and comments that vary without functional configuration changes
VOLATILE_HEADER_PATTERNS = [
    re.compile(r"^#\s*last\s+physical\s+(?:up|down)\s+time:?.*$", re.IGNORECASE),
    re.compile(r"^#\s*(?:current\s+configuration(?:\s+generated\s+on)?|configuration\s+generated\s+on):?.*$", re.IGNORECASE),
    re.compile(r"^#\s*info:\s*current\s+terminal\s+time:?.*$", re.IGNORECASE),
    re.compile(r"^#\s*time:\s*\d{4}-\d{2}-\d{2}.*$", re.IGNORECASE),
    re.compile(r"^#\s*uptime\s+is\s+.*$", re.IGNORECASE),
]

PAGINATION_PATTERNS = [
    re.compile(r"^\s*----\s*More\s*----\s*$", re.IGNORECASE),
    re.compile(r"^\s*--\s*More\s*\(Key\s*'Q'\s*to\s*quit\)\s*--\s*$", re.IGNORECASE),
    re.compile(r"^\s*<[^>]+>\s*$"),  # Prompt at end of output
    re.compile(r"^\s*\[[^\]]+\]\s*$"),
]


def normalize_vrp_config(raw_config: str) -> str:
    """
    Normalize Huawei VRP configuration text:
    - Removes terminal pagination and control artifacts.
    - Strips volatile timestamps and generated-on comments.
    - Trims trailing whitespace from each line.
    - Preserves exact syntax, indentation, and structure.
    """
    if not raw_config:
        return ""

    normalized_lines: List[str] = []
    lines = raw_config.splitlines()

    for line in lines:
        cleaned = line.rstrip()
        stripped = cleaned.strip()

        # 1. Skip empty lines at top/bottom or standalone carriage returns
        if not stripped:
            continue

        # 2. Skip pagination markers
        if any(pat.match(stripped) for pat in PAGINATION_PATTERNS):
            continue

        # 3. Skip volatile timestamp comments
        if any(pat.match(stripped) for pat in VOLATILE_HEADER_PATTERNS):
            continue

        normalized_lines.append(cleaned)

    return "\n".join(normalized_lines).strip()


def compute_config_hash(content: str) -> str:
    """Compute SHA-256 hex digest of normalized configuration content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def encrypt_config_content(plain_text: str) -> str:
    """Encrypt configuration content with vault Fernet key."""
    key = get_vault_key(require_prod=False)
    f = Fernet(key)
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_config_content(cipher_or_plain: str) -> str:
    """Decrypt encrypted configuration or return as-is if already plain text."""
    if not cipher_or_plain:
        return ""
    try:
        key = get_vault_key(require_prod=False)
        f = Fernet(key)
        return f.decrypt(cipher_or_plain.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback for plain-text or unencrypted mock data
        return cipher_or_plain


def generate_config_diff(
    before_text: str,
    after_text: str,
    before_label: str = "before",
    after_label: str = "after",
) -> Dict[str, Any]:
    """
    Generate unified text diff and structured hunks for UI rendering.
    Returns:
        unified_diff: str
        hunks: List[Dict] with type (add, delete, context), line numbers, and content.
        additions: int
        deletions: int
        changed: bool
    """
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=before_label,
            tofile=after_label,
            lineterm="\n",
        )
    )
    unified_diff_str = "".join(diff_lines)

    hunks: List[Dict[str, Any]] = []
    additions = 0
    deletions = 0
    old_lineno = 0
    new_lineno = 0

    for line in diff_lines:
        content = line.rstrip("\n")
        if line.startswith("@@"):
            # Header hunk e.g. @@ -1,5 +1,6 @@
            m = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                old_lineno = int(m.group(1))
                new_lineno = int(m.group(2))
            hunks.append({
                "type": "header",
                "content": content,
                "old_lineno": None,
                "new_lineno": None,
            })
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
            hunks.append({
                "type": "add",
                "content": content[1:],
                "old_lineno": None,
                "new_lineno": new_lineno,
            })
            new_lineno += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            hunks.append({
                "type": "delete",
                "content": content[1:],
                "old_lineno": old_lineno,
                "new_lineno": None,
            })
            old_lineno += 1
        elif not line.startswith("---") and not line.startswith("+++"):
            hunks.append({
                "type": "context",
                "content": content[1:] if line.startswith(" ") else content,
                "old_lineno": old_lineno,
                "new_lineno": new_lineno,
            })
            old_lineno += 1
            new_lineno += 1

    return {
        "unified_diff": unified_diff_str,
        "hunks": hunks,
        "additions": additions,
        "deletions": deletions,
        "changed": additions > 0 or deletions > 0,
    }


class ConfigBackupService:
    """Service orchestrating device configuration backup, deduplication, retention, and diffs."""

    @classmethod
    def create_snapshot(
        cls,
        db_session: Session,
        device_id: int,
        config_text: str,
        kind: str = "running",
        job_id: Optional[str] = None,
    ) -> Tuple[ConfigSnapshot, bool]:
        """
        Normalize config, check hash against latest snapshot for device:
        - If hash matches: updates last_checked_at and returns (latest, created=False).
        - If hash differs: encrypts and stores new snapshot, applies retention, and returns (new_snap, created=True).
        """
        normalized = normalize_vrp_config(config_text)
        new_hash = compute_config_hash(normalized)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check latest snapshot for this device & kind
        latest = (
            db_session.query(ConfigSnapshot)
            .filter(ConfigSnapshot.device_id == device_id, ConfigSnapshot.kind == kind)
            .order_by(ConfigSnapshot.taken_at.desc())
            .first()
        )

        if latest and latest.sha256 == new_hash:
            latest.last_checked_at = now
            db_session.commit()
            return latest, False

        # Configuration changed or first backup
        encrypted = encrypt_config_content(normalized)
        new_snap = ConfigSnapshot(
            device_id=device_id,
            kind=kind,
            sha256=new_hash,
            content_encrypted_or_text=encrypted,
            size_bytes=len(normalized.encode("utf-8")),
            job_id=job_id,
            taken_at=now,
            last_checked_at=now,
        )
        db_session.add(new_snap)
        db_session.flush()

        # Enforce retention policy
        cls.prune_snapshots(db_session, device_id=device_id, kind=kind)

        db_session.commit()
        return new_snap, True

    @classmethod
    def prune_snapshots(
        cls,
        db_session: Session,
        device_id: int,
        kind: str = "running",
        keep_recent_count: int = 30,
        max_monthly_history: int = 12,
    ) -> int:
        """
        Enforce retention policy:
        1. Always keep the most recent `keep_recent_count` (default: 30) snapshots.
        2. For snapshots older than the recent count, keep at most 1 snapshot per calendar month,
           up to `max_monthly_history` months (12 months).
        3. Delete any other redundant or overly old snapshots.
        """
        all_snapshots = (
            db_session.query(ConfigSnapshot)
            .filter(ConfigSnapshot.device_id == device_id, ConfigSnapshot.kind == kind)
            .order_by(ConfigSnapshot.taken_at.desc())
            .all()
        )

        if len(all_snapshots) <= keep_recent_count:
            return 0

        # Preserve the most recent snapshots
        keep_ids = {s.id for s in all_snapshots[:keep_recent_count]}
        older_snapshots = all_snapshots[keep_recent_count:]

        # Monthly tracking: (year, month) -> snapshot_id to keep
        monthly_kept: Dict[Tuple[int, int], str] = {}
        for s in older_snapshots:
            if not s.taken_at:
                continue
            key = (s.taken_at.year, s.taken_at.month)
            if key not in monthly_kept and len(monthly_kept) < max_monthly_history:
                monthly_kept[key] = s.id
                keep_ids.add(s.id)

        # Delete any snapshot not in keep_ids
        deleted_count = 0
        for s in older_snapshots:
            if s.id not in keep_ids:
                db_session.delete(s)
                deleted_count += 1

        return deleted_count

    @classmethod
    def get_snapshot_decrypted(cls, db_session: Session, snapshot_id: str) -> Optional[str]:
        """Fetch snapshot and decrypt content to plaintext."""
        snap = db_session.query(ConfigSnapshot).filter(ConfigSnapshot.id == snapshot_id).first()
        if not snap:
            return None
        return decrypt_config_content(snap.content_encrypted_or_text)

    @classmethod
    def diff_snapshots(
        cls,
        db_session: Session,
        from_snapshot_id: str,
        to_snapshot_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Compute unified and structured diff between two snapshots."""
        snap_from = db_session.query(ConfigSnapshot).filter(ConfigSnapshot.id == from_snapshot_id).first()
        snap_to = db_session.query(ConfigSnapshot).filter(ConfigSnapshot.id == to_snapshot_id).first()

        if not snap_from or not snap_to:
            return None

        from_text = decrypt_config_content(snap_from.content_encrypted_or_text)
        to_text = decrypt_config_content(snap_to.content_encrypted_or_text)

        label_from = f"snapshot_{snap_from.id[:8]}_{snap_from.taken_at.strftime('%Y%m%d_%H%M%S')}"
        label_to = f"snapshot_{snap_to.id[:8]}_{snap_to.taken_at.strftime('%Y%m%d_%H%M%S')}"

        diff_res = generate_config_diff(from_text, to_text, before_label=label_from, after_label=label_to)
        diff_res["from_snapshot"] = snap_from.to_dict()
        diff_res["to_snapshot"] = snap_to.to_dict()
        return diff_res

    @classmethod
    def get_device_timeline(
        cls,
        db_session: Session,
        device_id: int,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Build an enriched timeline of configuration snapshots for a device.
        Correlates each snapshot with Job and ChangeRequest records to answer 'who/what changed'.
        """
        dev = db_session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return []

        query = db_session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == device_id)
        if kind:
            query = query.filter(ConfigSnapshot.kind == kind)

        snapshots = (
            query.order_by(ConfigSnapshot.taken_at.desc())
            .limit(limit)
            .all()
        )

        if not snapshots:
            return []

        timeline: List[Dict[str, Any]] = []

        for i, s in enumerate(snapshots):
            older_snap = snapshots[i + 1] if i + 1 < len(snapshots) else None

            # 1. Job and ChangeRequest correlation
            job = None
            if s.job_id:
                job = db_session.query(Job).filter(Job.id == s.job_id).first()

            cr = (
                db_session.query(ChangeRequest)
                .filter(
                    or_(
                        ChangeRequest.snapshot_id == s.id,
                        (ChangeRequest.job_id == s.job_id) if s.job_id else False,
                    )
                )
                .first()
            )

            # Determine who changed
            if cr and cr.approver_id:
                who_changed = f"{cr.creator_id or 'unknown'} (approved by {cr.approver_id})"
            elif cr and cr.creator_id:
                who_changed = cr.creator_id
            elif job and job.created_by:
                who_changed = job.created_by
            else:
                who_changed = "system/scheduled"

            # Determine what changed
            if older_snap is None:
                what_changed = "Initial configuration baseline"
                diff_summary = {"additions": 0, "deletions": 0, "changed": False}
            elif older_snap.sha256 == s.sha256:
                what_changed = "Unchanged configuration checkpoint"
                diff_summary = {"additions": 0, "deletions": 0, "changed": False}
            else:
                s_text = cls.get_snapshot_decrypted(db_session, s.id) or ""
                older_text = cls.get_snapshot_decrypted(db_session, older_snap.id) or ""
                diff_res = generate_config_diff(older_text, s_text)
                adds = diff_res["additions"]
                dels = diff_res["deletions"]
                what_changed = f"+{adds} / -{dels} lines changed"
                diff_summary = {"additions": adds, "deletions": dels, "changed": True}

            timeline.append({
                "snapshot_id": s.id,
                "device_id": s.device_id,
                "device_name": dev.name,
                "taken_at": s.taken_at.isoformat() if s.taken_at else None,
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                "kind": s.kind,
                "sha256": s.sha256,
                "size_bytes": s.size_bytes,
                "job_id": s.job_id,
                "job": {
                    "id": job.id,
                    "type": job.type,
                    "created_by": job.created_by,
                    "status": job.status,
                    "mode": job.mode,
                } if job else None,
                "change_request": {
                    "id": cr.id,
                    "risk_level": cr.risk_level,
                    "creator_id": cr.creator_id,
                    "approver_id": cr.approver_id,
                    "status": cr.status,
                } if cr else None,
                "who_changed": who_changed,
                "what_changed": what_changed,
                "diff_summary": diff_summary,
            })

        return timeline

    @classmethod
    def get_download_data(
        cls,
        db_session: Session,
        device_id: int,
        snapshot_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve decrypted snapshot content and metadata formatted for file download."""
        dev = db_session.query(Device).filter(Device.id == device_id).first()
        snap = (
            db_session.query(ConfigSnapshot)
            .filter(
                ConfigSnapshot.id == snapshot_id,
                ConfigSnapshot.device_id == device_id,
            )
            .first()
        )
        if not dev or not snap:
            return None

        content = cls.get_snapshot_decrypted(db_session, snapshot_id) or ""
        ts_str = snap.taken_at.strftime("%Y%m%d_%H%M%S") if snap.taken_at else "snapshot"
        filename = f"{dev.name}_{snap.kind}_{ts_str}.cfg"
        return {
            "filename": filename,
            "content": content,
            "mimetype": "text/plain; charset=utf-8",
            "device_name": dev.name,
            "kind": snap.kind,
            "sha256": snap.sha256,
            "size_bytes": len(content.encode("utf-8")),
        }
