"""Tests for the image download and storage module."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image

from recipebrain.images import (
    _extension_from_url,
    _image_filename,
    _output_extension,
    _resize_and_compress,
    _rewrite_cdn_url,
    _url_hash,
    download_recipe_images,
    images_dir,
)
from recipebrain.settings import ImagesConfig


class TestUrlHash:
    def test_returns_12_char_hex(self):
        h = _url_hash("https://example.com/img.jpg")
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert _url_hash("https://example.com/a.jpg") == _url_hash("https://example.com/a.jpg")

    def test_different_urls_different_hashes(self):
        assert _url_hash("https://example.com/a.jpg") != _url_hash("https://example.com/b.jpg")


class TestExtensionFromUrl:
    def test_png(self):
        assert _extension_from_url("https://example.com/photo.png") == ".png"

    def test_jpg(self):
        assert _extension_from_url("https://example.com/photo.jpg") == ".jpg"

    def test_jpeg(self):
        assert _extension_from_url("https://example.com/photo.jpeg") == ".jpeg"

    def test_webp(self):
        assert _extension_from_url("https://example.com/photo.webp") == ".webp"

    def test_uppercase(self):
        assert _extension_from_url("https://example.com/photo.WEBP") == ".webp"

    def test_no_extension_defaults_to_jpg(self):
        assert _extension_from_url("https://example.com/photo") == ".jpg"

    def test_unknown_extension_defaults_to_jpg(self):
        assert _extension_from_url("https://example.com/photo.bmp") == ".jpg"

    def test_cdn_url_with_transform_params(self):
        url = "https://media.bettybossi.ch/image/123/img/-FWEBP-Ro:5,w:1125"
        assert _extension_from_url(url) == ".jpg"


class TestImageFilename:
    def test_format(self):
        name = _image_filename(42, 1, "https://example.com/photo.png")
        assert name.startswith("42_001_")
        assert name.endswith(".png")

    def test_deterministic(self):
        a = _image_filename(1, 1, "https://example.com/a.jpg")
        b = _image_filename(1, 1, "https://example.com/a.jpg")
        assert a == b

    def test_different_seq(self):
        a = _image_filename(1, 1, "https://example.com/a.jpg")
        b = _image_filename(1, 2, "https://example.com/a.jpg")
        assert a != b

    def test_with_config_jpeg(self):
        cfg = ImagesConfig(format="jpeg", enabled=True)
        name = _image_filename(1, 1, "https://example.com/photo.png", config=cfg)
        assert name.endswith(".jpg")

    def test_with_config_webp(self):
        cfg = ImagesConfig(format="webp", enabled=True)
        name = _image_filename(1, 1, "https://example.com/photo.png", config=cfg)
        assert name.endswith(".webp")

    def test_with_disabled_config_uses_source_ext(self):
        cfg = ImagesConfig(format="webp", enabled=False)
        name = _image_filename(1, 1, "https://example.com/photo.png", config=cfg)
        assert name.endswith(".png")


class TestImagesDir:
    def test_returns_images_subdir(self, tmp_path):
        assert images_dir(tmp_path) == tmp_path / "images"


class TestDownloadRecipeImages:
    def test_downloads_single_image(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.png"]
        paths = download_recipe_images(urls, recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 1
        assert paths[0] is not None
        assert paths[0].startswith("images/")
        assert (tmp_path / paths[0]).exists()
        assert (tmp_path / paths[0]).read_bytes() == mock_response.content

    def test_downloads_multiple_images(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = b"fake-image-data"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = [
            "https://media.bettybossi.ch/img/a.jpg",
            "https://media.bettybossi.ch/img/b.jpg",
            "https://media.bettybossi.ch/img/c.jpg",
        ]
        paths = download_recipe_images(urls, recipe_id=5, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 3
        assert all(p is not None for p in paths)
        assert mock_client.get.call_count == 3

    def test_skips_existing_file(self, tmp_path):
        # Pre-create the image file
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        url = "https://media.bettybossi.ch/img/photo.jpg"
        filename = _image_filename(1, 1, url)
        (img_dir / filename).write_bytes(b"existing-data")

        mock_client = MagicMock(spec=httpx.Client)
        paths = download_recipe_images([url], recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 1
        assert paths[0] is not None
        mock_client.get.assert_not_called()

    def test_returns_none_on_http_error(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock()
        )

        urls = ["https://media.bettybossi.ch/img/missing.jpg"]
        paths = download_recipe_images(urls, recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 1
        assert paths[0] is None

    def test_returns_none_on_oversized_image(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = b"\x00" * (21 * 1024 * 1024)  # 21 MB
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/huge.jpg"]
        paths = download_recipe_images(urls, recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 1
        assert paths[0] is None

    def test_empty_urls_returns_empty(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        paths = download_recipe_images([], recipe_id=1, output_dir=tmp_path, client=mock_client)
        assert paths == []

    def test_creates_images_directory(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = b"fake-image"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.jpg"]
        download_recipe_images(urls, recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert (tmp_path / "images").is_dir()

    def test_partial_failure(self, tmp_path):
        """One image fails, others succeed."""
        mock_client = MagicMock(spec=httpx.Client)
        good_response = MagicMock()
        good_response.content = b"good-image"
        good_response.raise_for_status = MagicMock()

        def side_effect(url):
            if "fail" in url:
                raise httpx.ConnectError("Connection refused")
            return good_response

        mock_client.get.side_effect = side_effect

        urls = [
            "https://media.bettybossi.ch/img/ok.jpg",
            "https://media.bettybossi.ch/img/fail.jpg",
            "https://media.bettybossi.ch/img/ok2.jpg",
        ]
        paths = download_recipe_images(urls, recipe_id=1, output_dir=tmp_path, client=mock_client)

        assert len(paths) == 3
        assert paths[0] is not None
        assert paths[1] is None
        assert paths[2] is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_image(width: int = 200, height: int = 150, fmt: str = "JPEG") -> bytes:
    """Create a minimal valid image in memory."""
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_tiny_image(width: int = 1, height: int = 1) -> bytes:
    """Create a 1x1 tracking pixel."""
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# New test classes for compression/CDN features
# ---------------------------------------------------------------------------


class TestOutputExtension:
    def test_none_config_defaults_to_jpg(self):
        assert _output_extension(None) == ".jpg"

    def test_jpeg_format(self):
        assert _output_extension(ImagesConfig(format="jpeg")) == ".jpg"

    def test_webp_format(self):
        assert _output_extension(ImagesConfig(format="webp")) == ".webp"


class TestRewriteCdnUrl:
    def test_migros_url_downsized(self):
        url = "https://recipeimages.migros.ch/crop/v-w-2050-h-1367-a-center_center/abc/img.jpg"
        result = _rewrite_cdn_url(url, 1200)
        assert "v-w-1200-h-800" in result
        assert result.endswith("/abc/img.jpg")

    def test_migros_url_already_small(self):
        url = "https://recipeimages.migros.ch/crop/v-w-330-h-186-a-center_center/abc/img.jpg"
        result = _rewrite_cdn_url(url, 1200)
        # Already smaller than max_width, unchanged
        assert result == url

    def test_non_migros_url_passthrough(self):
        url = "https://media.bettybossi.ch/img/photo.jpg"
        assert _rewrite_cdn_url(url, 1200) == url

    def test_no_match_passthrough(self):
        url = "https://recipeimages.migros.ch/other/path/img.jpg"
        assert _rewrite_cdn_url(url, 1200) == url


class TestResizeAndCompress:
    def test_resizes_large_image(self):
        data = _make_test_image(2050, 1367)
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.width == 800
        assert img.height == pytest.approx(533, abs=1)

    def test_small_image_not_upscaled(self):
        data = _make_test_image(400, 300)
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.width == 400
        assert img.height == 300

    def test_rejects_tracking_pixel(self):
        data = _make_tiny_image(1, 1)
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is None

    def test_rejects_small_pixel_at_threshold(self):
        data = _make_tiny_image(10, 10)
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is None

    def test_accepts_image_above_threshold(self):
        data = _make_test_image(11, 11)
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None

    def test_webp_output(self):
        data = _make_test_image(200, 150)
        cfg = ImagesConfig(max_width=800, quality=75, format="webp", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.format == "WEBP"

    def test_jpeg_output_from_png(self):
        data = _make_test_image(200, 150, fmt="PNG")
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_rgba_converted_for_jpeg(self):
        img = Image.new("RGBA", (200, 150), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        out = Image.open(io.BytesIO(result))
        assert out.mode == "RGB"

    def test_invalid_data_returns_raw(self):
        cfg = ImagesConfig(max_width=800, quality=80, format="jpeg", min_dimension=10)
        result = _resize_and_compress(b"not-an-image", cfg)
        assert result == b"not-an-image"

    def test_compression_reduces_size(self):
        # Large uncompressed image should compress significantly
        data = _make_test_image(2000, 1500)
        cfg = ImagesConfig(max_width=800, quality=70, format="jpeg", min_dimension=10)
        result = _resize_and_compress(data, cfg)
        assert result is not None
        assert len(result) < len(data)


class TestDownloadWithConfig:
    """Tests for download_recipe_images with image processing config."""

    def _cfg(self, **kwargs) -> ImagesConfig:
        defaults = {"max_width": 800, "quality": 80, "format": "jpeg", "min_dimension": 10}
        defaults.update(kwargs)
        return ImagesConfig(**defaults)

    def test_resizes_on_download(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = _make_test_image(2050, 1367)
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.jpg"]
        cfg = self._cfg()
        paths = download_recipe_images(
            urls, recipe_id=1, output_dir=tmp_path, client=mock_client, config=cfg
        )

        assert len(paths) == 1
        assert paths[0] is not None
        # Verify the stored image is resized
        stored = Image.open(tmp_path / paths[0])
        assert stored.width == 800

    def test_rejects_tracking_pixel_on_download(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = _make_tiny_image(1, 1)
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/pixel.jpg"]
        cfg = self._cfg()
        paths = download_recipe_images(
            urls, recipe_id=1, output_dir=tmp_path, client=mock_client, config=cfg
        )

        assert paths[0] is None

    def test_rewrites_migros_cdn_url(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = _make_test_image(800, 533)
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://recipeimages.migros.ch/crop/v-w-2050-h-1367-a-center_center/abc/img.jpg"
        cfg = self._cfg(max_width=800)
        download_recipe_images(
            [url], recipe_id=1, output_dir=tmp_path, client=mock_client, config=cfg
        )

        # Verify the CDN was called with rewritten URL
        called_url = mock_client.get.call_args[0][0]
        assert "v-w-800-h-533" in called_url

    def test_disabled_config_stores_raw(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        raw_data = _make_test_image(2050, 1367)
        mock_response.content = raw_data
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.jpg"]
        cfg = ImagesConfig(enabled=False)
        paths = download_recipe_images(
            urls, recipe_id=1, output_dir=tmp_path, client=mock_client, config=cfg
        )

        assert paths[0] is not None
        stored_bytes = (tmp_path / paths[0]).read_bytes()
        assert stored_bytes == raw_data

    def test_webp_output_extension(self, tmp_path):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.content = _make_test_image(200, 150)
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.png"]
        cfg = self._cfg(format="webp")
        paths = download_recipe_images(
            urls, recipe_id=1, output_dir=tmp_path, client=mock_client, config=cfg
        )

        assert paths[0] is not None
        assert paths[0].endswith(".webp")

    def test_none_config_stores_raw(self, tmp_path):
        """Backward compat: no config = raw bytes, same as before."""
        mock_client = MagicMock(spec=httpx.Client)
        raw_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_response = MagicMock()
        mock_response.content = raw_data
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = ["https://media.bettybossi.ch/img/photo.png"]
        paths = download_recipe_images(
            urls, recipe_id=1, output_dir=tmp_path, client=mock_client, config=None
        )

        assert paths[0] is not None
        assert (tmp_path / paths[0]).read_bytes() == raw_data
