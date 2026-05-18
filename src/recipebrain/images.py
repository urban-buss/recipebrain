"""Image downloading and local storage with optional resize/recompression.

Downloads recipe images from URLs and stores them as files in the output
directory. Uses deterministic filenames based on URL hash so re-runs
skip already-downloaded images.

When an ImagesConfig is provided, images are:
- Rewritten to request smaller CDN variants where possible (Migros).
- Resized to fit within max_width pixels (longest edge).
- Re-encoded at configurable JPEG/WebP quality.
- Rejected if smaller than min_dimension (tracking pixels).
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from recipebrain.settings import ImagesConfig

logger = logging.getLogger(__name__)

_IMAGES_SUBDIR = "images"
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})
_DEFAULT_EXTENSION = ".jpg"
_MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB safety limit

# Regex to match Migros CDN width parameter: v-w-<digits>-h-<digits>
_MIGROS_CDN_RE = re.compile(r"(v-w-)\d+(-h-)\d+")


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


def _output_extension(config: ImagesConfig | None) -> str:
    """Return the file extension for the configured output format.

    Examples:
        >>> from recipebrain.settings import ImagesConfig
        >>> _output_extension(ImagesConfig(format="webp"))
        '.webp'
        >>> _output_extension(None)
        '.jpg'
    """
    if config is None:
        return _DEFAULT_EXTENSION
    if config.format == "webp":
        return ".webp"
    return ".jpg"


def _image_filename(recipe_id: int, seq: int, url: str, config: ImagesConfig | None = None) -> str:
    """Build a deterministic filename for a recipe image.

    When *config* is provided, uses the configured output format extension.
    Otherwise falls back to the source URL's extension.

    Examples:
        >>> _image_filename(42, 1, "https://example.com/photo.png")
        '42_001_...'
    """
    h = _url_hash(url)
    if config and config.enabled:
        ext = _output_extension(config)
    else:
        ext = _extension_from_url(url)
    return f"{recipe_id}_{seq:03d}_{h}{ext}"


def _rewrite_cdn_url(url: str, max_width: int) -> str:
    """Rewrite CDN URLs to request a smaller image variant where possible.

    Currently supports Migros/Migusto CDN URLs that encode width/height in
    the path segment (e.g. ``v-w-330-h-186-a-center_center``).

    Examples:
        >>> url = "https://recipeimages.migros.ch/crop/v-w-2050-h-1367-a-center_center/abc/img.jpg"
        >>> _rewrite_cdn_url(url, 1200)
        'https://recipeimages.migros.ch/crop/v-w-1200-h-800-a-center_center/abc/img.jpg'
        >>> _rewrite_cdn_url("https://media.bettybossi.ch/img/photo.jpg", 1200)
        'https://media.bettybossi.ch/img/photo.jpg'
    """
    if "recipeimages.migros.ch" not in url:
        return url

    match = _MIGROS_CDN_RE.search(url)
    if not match:
        return url

    # Extract original dimensions to maintain aspect ratio
    orig_segment = match.group(0)  # e.g. "v-w-2050-h-1367"
    parts = orig_segment.split("-")
    # parts: ['v', 'w', '<width>', 'h', '<height>']
    try:
        orig_w = int(parts[2])
        orig_h = int(parts[4])
    except (IndexError, ValueError):
        return url

    if orig_w <= max_width:
        return url

    ratio = max_width / orig_w
    new_h = int(orig_h * ratio)
    replacement = f"{match.group(1)}{max_width}{match.group(2)}{new_h}"
    return url[: match.start()] + replacement + url[match.end() :]


def _resize_and_compress(
    data: bytes,
    config: ImagesConfig,
) -> bytes | None:
    """Resize and re-encode image bytes according to *config*.

    Returns processed image bytes, or ``None`` if the image should be
    rejected (e.g. tracking pixel below min_dimension).

    Examples:
        >>> from recipebrain.settings import ImagesConfig
        >>> cfg = ImagesConfig(max_width=100, quality=70, format="jpeg", min_dimension=10)
        >>> result = _resize_and_compress(b'...valid_jpeg...', cfg)  # doctest: +SKIP
    """
    try:
        img: Image.Image = Image.open(io.BytesIO(data))
    except Exception:
        logger.warning("Failed to open image for processing — storing raw bytes")
        return data

    # Reject tracking pixels
    if img.width <= config.min_dimension and img.height <= config.min_dimension:
        return None

    # Resize if wider than max_width
    if img.width > config.max_width:
        ratio = config.max_width / img.width
        new_size = (config.max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Determine output format
    buf = io.BytesIO()
    if config.format == "webp":
        img.save(buf, format="WEBP", quality=config.quality, method=4)
    else:
        # JPEG cannot handle alpha channel
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=config.quality, optimize=True)

    return buf.getvalue()


def images_dir(output_dir: Path) -> Path:
    """Return the canonical images subdirectory."""
    return output_dir / _IMAGES_SUBDIR


def download_recipe_images(
    image_urls: list[str],
    recipe_id: int,
    output_dir: Path,
    client: httpx.Client,
    config: ImagesConfig | None = None,
) -> list[str | None]:
    """Download images and return a list of local paths (relative to output_dir).

    For each URL, downloads the image to ``output_dir/images/{filename}``.
    Skips images that already exist on disk. Returns ``None`` for any URL
    that failed to download or was rejected (e.g. tracking pixel).

    When *config* is provided and ``config.enabled`` is True, images are
    resized/recompressed according to configuration. CDN URLs are rewritten
    to request smaller variants where possible.

    Args:
        image_urls: Ordered list of image URLs.
        recipe_id: Recipe PK, used in filenames.
        output_dir: Root output directory (images go under ``images/`` subdir).
        client: httpx Client for making requests.
        config: Optional image processing configuration.

    Returns:
        List parallel to *image_urls* with relative paths (e.g.
        ``"images/42_001_abc123.jpg"``) or ``None`` for failures/rejections.
    """
    img_dir = images_dir(output_dir)
    img_dir.mkdir(parents=True, exist_ok=True)

    processing_enabled = config is not None and config.enabled
    local_paths: list[str | None] = []

    for seq, url in enumerate(image_urls, start=1):
        filename = _image_filename(recipe_id, seq, url, config if processing_enabled else None)
        dest = img_dir / filename
        rel_path = f"{_IMAGES_SUBDIR}/{filename}"

        if dest.exists():
            local_paths.append(rel_path)
            continue

        # Rewrite CDN URL to request a smaller variant
        fetch_url = url
        if processing_enabled:
            assert config is not None
            fetch_url = _rewrite_cdn_url(url, config.max_width)

        try:
            response = client.get(fetch_url)
            response.raise_for_status()

            if len(response.content) > _MAX_IMAGE_SIZE:
                logger.warning(
                    "Image too large (%d bytes), skipping: %s",
                    len(response.content),
                    url,
                )
                local_paths.append(None)
                continue

            image_data = response.content

            # Resize and recompress if processing is enabled
            if processing_enabled:
                assert config is not None
                processed = _resize_and_compress(image_data, config)
                if processed is None:
                    logger.debug("Rejected image (tracking pixel): %s", url)
                    local_paths.append(None)
                    continue
                image_data = processed

            dest.write_bytes(image_data)
            local_paths.append(rel_path)
        except httpx.HTTPError:
            logger.warning("Failed to download image: %s", url)
            local_paths.append(None)
        except OSError:
            logger.warning("Failed to write image to disk: %s", dest)
            local_paths.append(None)

    return local_paths
