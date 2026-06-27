from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import export_service  # noqa: E402


def test_pdf_image_url_rejects_non_http_urls() -> None:
    assert export_service._is_safe_remote_image_url("file:///etc/passwd") is False
    assert export_service._is_safe_remote_image_url("ftp://example.com/image.jpg") is False


def test_pdf_image_url_rejects_private_hosts(monkeypatch) -> None:
    monkeypatch.setattr(
        export_service.socket,
        "getaddrinfo",
        lambda hostname, port: [(None, None, None, None, ("127.0.0.1", 0))],
    )

    assert export_service._is_safe_remote_image_url("http://localhost/image.jpg") is False


def test_pdf_image_url_allows_public_https_hosts(monkeypatch) -> None:
    monkeypatch.setattr(
        export_service.socket,
        "getaddrinfo",
        lambda hostname, port: [(None, None, None, None, ("93.184.216.34", 0))],
    )

    assert export_service._is_safe_remote_image_url("https://example.com/image.jpg") is True
