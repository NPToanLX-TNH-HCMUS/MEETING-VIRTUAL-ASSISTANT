import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
BUCKET_NAME = "DocuMeet-bucket"

_MIME_OVERRIDES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".wav": "audio/wav",
    ".json": "application/json",
}


class CloudStorageError(RuntimeError):
    """Raised when uploading meeting artifacts to cloud storage fails."""


def _guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class CloudStorage:
    """Archives local per-meeting directories to an existing Supabase Storage bucket."""

    def __init__(
        self,
        bucket_name: str = BUCKET_NAME,
        client: Client | None = None,
    ) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_API_KEY:
                raise ValueError("Missing SUPABASE_URL or SUPABASE_API_KEY in .env")
            client = create_client(SUPABASE_URL, SUPABASE_API_KEY)
        self._bucket = client.storage.from_(bucket_name)

    def upload_meeting_directory(self, meeting_id: str, meeting_dir: Path) -> list[str]:
        """Upload all files under meeting_dir preserving paths, adding .keep for empty dirs."""
        if not meeting_dir.exists():
            return []

        # Skip recordings: ~2 MB per minute is minutes of upload on a slow uplink and blocks confirm.
        files = sorted(
            p for p in meeting_dir.rglob("*") if p.is_file() and p.suffix.lower() != ".wav"
        )
        empty_dirs = sorted(
            d
            for d in (meeting_dir, *meeting_dir.rglob("*"))
            if d.is_dir() and not any(d.iterdir())
        )

        uploaded_paths: list[str] = []
        try:
            for file_path in files:
                rel_path = file_path.relative_to(meeting_dir).as_posix()
                remote_path = f"{meeting_id}/{rel_path}"
                with file_path.open("rb") as fh:
                    self._bucket.upload(
                        path=remote_path,
                        file=fh,
                        file_options={
                            "content-type": _guess_content_type(file_path),
                            "upsert": "true",
                        },
                    )
                uploaded_paths.append(remote_path)

            # Object storage has no empty folders, so upload .keep markers to preserve the tree.
            for empty_dir in empty_dirs:
                rel_dir = empty_dir.relative_to(meeting_dir).as_posix()
                remote_path = (
                    f"{meeting_id}/.keep"
                    if rel_dir == "."
                    else f"{meeting_id}/{rel_dir}/.keep"
                )
                self._bucket.upload(
                    path=remote_path,
                    file=b"",
                    file_options={"content-type": "text/plain", "upsert": "true"},
                )
                uploaded_paths.append(remote_path)
        except Exception as exc:
            raise CloudStorageError(
                f"Failed to upload '{meeting_id}' artifacts: {exc}"
            ) from exc

        return uploaded_paths
