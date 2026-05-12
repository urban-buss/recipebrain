"""Tests for the image download and storage module."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from recipebrain.images import (
    _extension_from_url,
    _image_filename,
    _url_hash,
    download_recipe_images,
    images_dir,
)


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
