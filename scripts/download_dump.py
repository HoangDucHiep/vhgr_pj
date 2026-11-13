#!/usr/bin/env python
"""Tải dump Wikipedia tiếng Việt từ `dumps.wikimedia.org`.

Cách dùng:
    python scripts/download_dump.py --dump-version 20261101
    python scripts/download_dump.py --dump-version 20261101 --resume

Ghi `data/raw/manifest.json` với tên file, kích thước, sha1 và ngày tải.

Lưu ý (đã kiểm chứng 11/2026): **viwiki không có file `redirects.xml.bz2` riêng**
— redirect nằm trong `pages-articles.xml.bz2` dưới thẻ `<redirect>`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_default_config  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger("scripts.download_dump")

# User-Agent định danh theo yêu cầu của Wikimedia.
# Header HTTP chỉ mã hoá được latin-1 → User-Agent **phải là ASCII thuần**.
USER_AGENT = (
    "vhgr-npl-project/1.0 (Knowledge Graph lich su Viet Nam; "
    "contact: hoangduchiep) Python-urllib"
)

CHUNK_SIZE = 1024 * 1024


def _sha1(path: Path) -> str:
    """Tính sha1 của file theo luồng.

    Args:
        path: Đường dẫn file.

    Returns:
        Chuỗi hex sha1 40 ký tự.
    """
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, *, resume: bool) -> None:
    """Tải một file URL về đường dẫn đích, hỗ trợ tiếp tục file dở dang.

    Args:
        url: URL nguồn.
        dest: Đường dẫn đích.
        resume: Tiếp tục tải file dở dang nếu có (dùng header ``Range``).

    Raises:
        urllib.error.URLError: Lỗi mạng.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0

    headers = {"User-Agent": USER_AGENT}
    mode = "wb"
    if resume and existing > 0:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        if resume and existing > 0 and response.status != 206:
            # Server không hỗ trợ Range → tải lại từ đầu.
            logger.warning("Server không hỗ trợ Range, tải lại từ đầu: %s", dest.name)
            existing = 0
            mode = "wb"

        total = response.headers.get("Content-Length")
        total_size = (int(total) + existing) if total else None
        downloaded = existing

        logger.info("Đang tải %s -> %s", url, dest.name)
        with dest.open(mode) as out:
            while chunk := response.read(CHUNK_SIZE):
                out.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    pct = 100.0 * downloaded / total_size
                    logger.info(
                        "  %s: %.1f%% (%d MB)",
                        dest.name,
                        pct,
                        downloaded // (1024 * 1024),
                    )
                else:
                    logger.info("  %s: %d MB", dest.name, downloaded // (1024 * 1024))


def main() -> int:
    """Điểm vào của CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Tải dump Wikipedia tiếng Việt")
    parser.add_argument(
        "--dump-version",
        default=None,
        help="Phiên bản dump, ví dụ 20261101. Mặc định lấy từ configs/default.yaml",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Tiếp tục tải file dở dang thay vì tải lại từ đầu",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Chỉ tải các file được chỉ định: pages_articles, pages_meta_current",
    )
    args = parser.parse_args()

    config = load_default_config()
    dump_version = args.dump_version or str(config["dump"]["dump_version"])
    raw_dir = REPO_ROOT / str(config["paths"]["raw_dir"])
    base_url = str(config["dump"]["dump_base_url"]).rstrip("/")

    files: dict[str, str] = {
        "pages_articles": f"viwiki-{dump_version}-pages-articles.xml.bz2",
        "pages_meta_current": f"viwiki-{dump_version}-pages-meta-current.xml.bz2",
    }
    if args.only:
        unknown = set(args.only) - set(files)
        if unknown:
            logger.error("Tên file không hợp lệ: %s", ", ".join(sorted(unknown)))
            return 2
        files = {key: value for key, value in files.items() if key in args.only}

    manifest_path = raw_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest["dump_version"] = dump_version
    manifest["downloaded_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["files"] = manifest.get("files", {})

    for key, filename in files.items():
        url = f"{base_url}/{dump_version}/{filename}"
        dest = raw_dir / filename
        try:
            _download(url, dest, resume=args.resume)
        except urllib.error.URLError as exc:
            logger.error("Lỗi tải %s: %s", filename, exc)
            return 1

        size = dest.stat().st_size
        logger.info("Tính sha1 cho %s (%d MB)...", filename, size // (1024 * 1024))
        manifest["files"][filename] = {
            "key": key,
            "url": url,
            "size_bytes": size,
            "sha1": _sha1(dest),
            "downloaded_at": manifest["downloaded_at"],
        }
        logger.info("Xong %s (%d MB)", filename, size // (1024 * 1024))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Đã ghi manifest: %s", manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
