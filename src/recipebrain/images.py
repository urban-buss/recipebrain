"""Image downloading and local storage.

Downloads recipe images from URLs and stores them as files in the output
directory. Uses deterministic filenames based on URL hash so re-runs
skip already-downloaded images.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_IMAGES_SUBDIR = "images"
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})
_DEFAULT_EXTENSION = ".jpg"
_MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB safety limit


def _url_hash(url: str) -> str:
    """Compute a short deterministic hash from a URL.

    Examples:
        >>> len(_url_hash("https://example.com/img.jpg"))
        12
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _extension_from_url(url: str) -> str:
    """Extract a file extension from an image URL.

    Falls back to .jpg if the extension is not recognised.

    Examples:
        >>> _extension_from_url("https://example.com/photo.png")
        '.png'
        >>> _extension_from_url("https://example.com/photo")
        '.jpg'
        >>> _extension_from_url("https://example.com/photo.WEBP")
        '.webp'
    """
    path = urlparse(url).path
    # Strip query-like suffixes that may appear in CDN URLs (e.g. /-FWEBP-...)
    path = path.split("/-")[0]
    dot_pos = path.rfind(".")
    if dot_pos >= 0:
        ext = path[dot_pos:].lower()
        if ext in _ALLOWED_EXTENSIONS:
            return ext
    return _DEFAULT_EXTENSION


def _image_filename(recipe_id: int, seq: int, url: str) -> str:
    """Build a deterministic filename for a recipe image.

    Examples:
        >>> _image_filename(42, 1, "https://example.com/photo.png")
        '42_001_..._photo.png'
    """
    h = _url_hash(url)
    ext = _extension_from_url(url)
    return f"{recipe_id}_{seq:03d}_{h}{ext}"


def images_dir(output_dir: Path) -> Path:
    """Return the canonical images subdirectory."""
    return output_dir / _IMAGES_SUBDIR


def download_recipe_images(
    image_urls: list[str],
    recipe_id: int,
    output_dir: Path,
    client: httpx.Client,
) -> list[str | None]:
    """Download images and return a list of local paths (relative to output_dir).

    For each URL, downloads the image to ``output_dir/images/{filename}``.
    Skips images that already exist on disk. Returns ``None`` for any URL
    that failed to download.

    Args:
        image_urls: Ordered list of image URLs.
        recipe_id: Recipe PK, used in filenames.
        output_dir: Root output directory (images go under ``images/`` subdir).
        client: httpx Client for making requests.

    Returns:
        List parallel to *image_urls* with relative paths (e.g.
        ``"images/42_001_abc123.jpg"``) or ``None`` for failures.
    """
    img_dir = images_dir(output_dir)
    img_dir.mkdir(parents=True, exist_ok=True)

    local_paths: list[str | None] = []

    for seq, url in enumerate(image_urls, start=1):
        filename = _image_filename(recipe_id, seq, url)
        dest = img_dir / filename
        rel_path = f"{_IMAGES_SUBDIR}/{filename}"

        if dest.exists():
            local_paths.append(rel_path)
            continue

        try:
            response = client.get(url)
            response.raise_for_status()

            if len(response.content) > _MAX_IMAGE_SIZE:
                logger.warning(
                    "Image too large (%d bytes), skipping: %s",
                    len(response.content),
                    url,
                )
                local_paths.append(None)
                continue

            dest.write_bytes(response.content)
            local_paths.append(rel_path)
        except httpx.HTTPError:
            logger.warning("Failed to download image: %s", url)
            local_paths.append(None)
        except OSError:
            logger.warning("Failed to write image to disk: %s", dest)
            local_paths.append(None)

    return local_paths
