from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QFont
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest


WARM_PALETTE = ("#f06a3d", "#a92f45")
MAX_ART_BYTES = 25 * 1024 * 1024
MIN_ART_WIDTH = 300
MIN_ART_HEIGHT = 150
MAX_ART_PIXELS = 50_000_000


def theme_stylesheet(accent="#f06a3d", secondary="#a92f45", compact=False):
    radius = "10px" if compact else "12px"
    soft_accent = f"#{0x22:02x}{accent.lstrip('#')}"
    selected_accent = f"#{0x44:02x}{accent.lstrip('#')}"
    hover_accent = f"#{0x55:02x}{accent.lstrip('#')}"
    return f"""
 QWidget{{color:#f2f0ed;font-family:'Segoe UI';font-size:13px;}}
 QMainWindow,QDialog{{background:#0b0d12;}}
 QFrame#sidebar{{background:#10131a;border-right:1px solid #252a34;}}
 QLabel#brand{{font-size:24px;font-weight:900;letter-spacing:2px;color:#fffaf5;}}
 QLabel#brandSub,QLabel#eyebrow{{color:{accent};font-size:10px;font-weight:850;letter-spacing:1.8px;}}
 QLabel#sideFoot,QLabel#muted{{color:#8e95a3;}}
 QLabel#pageTitle{{font-size:25px;font-weight:800;}}
 QLabel#sectionTitle{{font-size:17px;font-weight:750;}}
 QLabel#heroTitle{{font-size:25px;font-weight:850;}}
 QFrame#hero{{background:#171b24;border:1px solid #343b49;border-radius:16px;}}
 QFrame#panel,QFrame#statCard{{background:#141923;border:1px solid #2b303c;border-radius:{radius};}}
 QPushButton{{background:#191e28;border:1px solid #343b49;border-radius:{radius};padding:10px 14px;font-weight:700;}}
 QPushButton:hover{{border-color:{accent};background:#25202a;}}
 QPushButton:disabled{{color:#626b79;background:#171b23;border-color:#292f3a;}}
 QPushButton#primary{{background:{accent};color:#fff;border:0;padding:11px 17px;font-weight:900;}}
 QPushButton#navButton,QPushButton#navActive{{text-align:left;padding:13px 12px;border:0;}}
 QPushButton#navButton{{background:transparent;color:#a5adba;}}
 QPushButton#navActive{{background:{soft_accent};color:#fff;border-left:3px solid {accent};}}
 QLineEdit{{background:#141923;border:1px solid #343b49;border-radius:{radius};padding:10px 12px;color:#fff;}}
 QLineEdit:focus{{border-color:{accent};}}
 QTableWidget{{background:#10151e;alternate-background-color:#141a24;border:1px solid #2b303c;border-radius:14px;padding:5px;selection-background-color:{selected_accent};gridline-color:transparent;}}
 QHeaderView::section{{background:#171d28;color:{accent};border:0;padding:12px 9px;font-size:10px;font-weight:900;letter-spacing:1px;}}
 QTableWidget::item{{padding:9px 8px;border-bottom:1px solid #242b37;}}
 QTableWidget::item:selected{{background:{selected_accent};color:#fff;}}
 QLabel#warning{{color:#f0bd91;background:#251a1b;border:1px solid {secondary};border-radius:10px;padding:12px;}}
 QComboBox{{background:#141923;border:1px solid #343b49;border-radius:{radius};padding:8px 10px;min-width:150px;}}
 QComboBox::drop-down{{border:0;width:25px;}}
 QComboBox QAbstractItemView{{background:#171d28;selection-background-color:{hover_accent};}}
 QProgressBar{{background:#171d28;color:#f5f1ed;border:1px solid #303746;border-radius:7px;text-align:center;min-height:12px;}}
 QProgressBar::chunk{{border-radius:6px;background:{accent};}}
 QScrollBar:vertical{{background:#10151e;width:10px;margin:2px;}}
 QScrollBar::handle:vertical{{background:#394252;border-radius:5px;min-height:28px;}}
 """


def make_placeholder_cover(name, platform, accent, secondary, size=(420, 236)):
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#10141d"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size[0], size[1])
    gradient.setColorAt(0, QColor(accent))
    gradient.setColorAt(1, QColor(secondary))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size[0], size[1], 18, 18)
    painter.setPen(QColor(255, 255, 255, 36))
    for offset in range(-size[1], size[0], 34):
        painter.drawLine(offset, 0, offset + size[1], size[1])
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", max(15, size[0] // 28))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(24, 24, size[0] - 48, size[1] // 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(name)[:36])
    font = QFont("Segoe UI", max(9, size[0] // 55))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 190))
    painter.drawText(24, size[1] - 42, size[0] - 48, 20, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(platform).upper()[:48])
    painter.end()
    return image


class GameArtService(QObject):
    """Fetch high-resolution Steam artwork once and keep it in a local persistent cache."""

    cover_ready = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.cache_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE" / "covers"
        self.pending = {}
        self.requested = set()
        self.game_names = {}
        self.game_keys = {}

    @staticmethod
    def cache_key(game):
        # Use stable game metadata, not its install path: moving/reinstalling a game
        # should not discard its already downloaded cover.
        identity = "|".join((
            str(getattr(game, "name", "")).strip().casefold(),
            str(getattr(game, "platform", "")).strip().casefold(),
            str(getattr(game, "app_id", "")).strip().casefold(),
        ))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    def cache_path(self, game):
        return self.cache_dir / (self.cache_key(game) + ".jpg")

    def cached_cover(self, game):
        path = self.cache_path(game)
        if not path.is_file():
            return None
        image = QImage(str(path))
        if image.isNull() or image.width() < MIN_ART_WIDTH or image.height() < MIN_ART_HEIGHT:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return image

    def request(self, game):
        path = str(game.path)
        if path in self.requested:
            return
        self.requested.add(path)
        self.game_names[path] = str(game.name)
        self.game_keys[path] = self.cache_key(game)
        cached = self.cached_cover(game)
        if cached is not None:
            QTimer.singleShot(0, lambda p=path, image=cached: self.cover_ready.emit(p, image))
            return

        app_id = str(getattr(game, "app_id", "") or "").strip()
        if app_id.isdigit():
            self._request_details(path, app_id)
        else:
            self._request_search(path)

    def _request_search(self, path):
        url = QUrl("https://store.steampowered.com/api/storesearch/")
        query = QUrlQuery()
        query.addQueryItem("term", self.game_names.get(path, "")[:100])
        query.addQueryItem("l", "english")
        query.addQueryItem("cc", "us")
        url.setQuery(query)
        self._send(path, "search", url.toString())

    def _request_details(self, path, app_id):
        url = QUrl("https://store.steampowered.com/api/appdetails")
        query = QUrlQuery()
        query.addQueryItem("appids", app_id)
        query.addQueryItem("l", "english")
        url.setQuery(query)
        self._send(path, "details", url.toString())

    def _send(self, path, phase, url):
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"Sarman-TRANSLATE/1.1")
        request.setTransferTimeout(15000)
        reply = self.manager.get(request)
        self.pending[reply] = (path, phase)
        reply.finished.connect(lambda current=reply: self._finished(current))

    def _finished(self, reply):
        path, phase = self.pending.pop(reply, ("", ""))
        try:
            if reply.error():
                return
            length = reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader)
            if length is not None and int(length) > MAX_ART_BYTES:
                return
            data = bytes(reply.readAll())
            if len(data) > MAX_ART_BYTES:
                return

            if phase == "search":
                payload = json.loads(data.decode("utf-8"))
                items = payload.get("items") or []
                wanted = " ".join(self.game_names.get(path, "").casefold().split())
                best = None
                best_score = 0.0
                for item in items:
                    candidate_name = " ".join(str(item.get("name", "")).casefold().split())
                    score = difflib.SequenceMatcher(None, wanted, candidate_name).ratio()
                    if score > best_score:
                        best, best_score = item, score
                if best and (best_score >= 0.86 or " ".join(str(best.get("name", "")).casefold().split()) == wanted):
                    app_id = str(best.get("id", "")).strip()
                    if app_id.isdigit():
                        self._request_details(path, app_id)
                return

            if phase == "details":
                payload = json.loads(data.decode("utf-8"))
                app_id = next(iter(payload), "")
                details = payload.get(app_id, {}).get("data") or {}
                screenshots = details.get("screenshots") or []
                image_url = ""
                # Full screenshots are generally 1920x1080 and look much sharper
                # than the small 460x215 Steam header artwork.
                if screenshots:
                    image_url = str(screenshots[0].get("path_full") or "")
                if not image_url:
                    image_url = str(details.get("header_image") or "")
                if image_url.startswith("https://"):
                    self._send(path, "image", image_url)
                return

            image = QImage.fromData(data)
            if image.isNull() or image.width() < MIN_ART_WIDTH or image.height() < MIN_ART_HEIGHT:
                return
            if image.width() * image.height() > MAX_ART_PIXELS:
                return
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self.cache_dir / (self.game_keys[path] + ".jpg")
            if not image.save(str(cache_path), "JPG", 94):
                return
            self.cover_ready.emit(path, image)
        except (ValueError, OSError, TypeError, KeyError, StopIteration):
            # Missing/invalid artwork is non-fatal: the designed placeholder remains.
            return
        finally:
            reply.deleteLater()
