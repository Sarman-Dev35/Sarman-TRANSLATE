from __future__ import annotations

import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QTabWidget, QComboBox
)

from patch_manager import (PatchError, inspect_patch, install_patch, uninstall_latest, uninstall_all, installed_patch_languages, incomplete_patch_installs, rollback_incomplete_patches)
from translation_studio import TranslationStudio
from translation_core import remove_incomplete_patch

APP_NAME = "Sarman TRANSLATE"
ACCENT = "#e58a43"
LANGUAGE_LABELS = {
    "EN": "İngilizce", "TR": "Türkçe", "DE": "Almanca", "FR": "Fransızca",
    "ES": "İspanyolca", "IT": "İtalyanca", "PT": "Portekizce", "RU": "Rusça",
    "JA": "Japonca", "KO": "Korece", "ZH": "Çince", "PL": "Lehçe",
    "NL": "Felemenkçe", "AR": "Arapça", "HI": "Hintçe", "ID": "Endonezce",
    "UK": "Ukraynaca", "SV": "İsveççe", "NO": "Norveççe", "DA": "Danca",
    "FI": "Fince", "CS": "Çekçe", "HU": "Macarca", "EL": "Yunanca",
    "HE": "İbranice", "RO": "Romence", "BG": "Bulgarca", "HR": "Hırvatça",
    "SK": "Slovakça", "SL": "Slovence", "SR": "Sırpça",
}


from game_discovery import Game, discover_games


def asset_path(name: str) -> Path:
    """Resolve bundled assets in both source runs and PyInstaller builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


def install_exception_logging():
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE" / "logs"
    logger = logging.getLogger("sarman_translate")
    logger.setLevel(logging.ERROR)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "application.log", maxBytes=2 * 1024 * 1024,
            backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logging.basicConfig(level=logging.ERROR)

    def handle_exception(exc_type, exc_value, traceback):
        logger.critical("Beklenmeyen uygulama hatası", exc_info=(exc_type, exc_value, traceback))
        if QApplication.instance():
            QMessageBox.critical(
                None, APP_NAME,
                "Beklenmeyen bir hata oluştu. Ayrıntılar yerel uygulama günlüğüne kaydedildi.\n\n"
                + str(log_dir / "application.log")
            )
        else:
            sys.__excepthook__(exc_type, exc_value, traceback)

    sys.excepthook = handle_exception


class ScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, extra_roots=None, parent=None):
        super().__init__(parent)
        self.extra_roots = extra_roots or []

    def run(self):
        try:
            self.completed.emit(discover_games(self.extra_roots))
        except Exception as exc:
            self.failed.emit(str(exc))


class StatCard(QFrame):
    def __init__(self, caption: str, value: str):
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 13, 17, 13)
        label = QLabel(caption.upper())
        label.setObjectName("eyebrow")
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon_file = asset_path("sarman-translate.ico")
        if not icon_file.is_file():
            icon_file = asset_path("sarman-translate.svg")
        if icon_file.is_file():
            self.setWindowIcon(QIcon(str(icon_file)))
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self.games: list[Game] = []
        self.worker = None
        self.language_settings = QSettings("Sarman Studios", "Sarman TRANSLATE")
        self.patch_path: str | None = None
        self.patch_manifest: dict | None = None
        self.build_ui()
        self.apply_style()
        # Start discovery after the event loop begins so the window remains responsive.
        QTimer.singleShot(150, self.start_scan)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 25, 20, 20)
        side.setSpacing(12)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(11)
        brand_icon = QLabel()
        brand_icon.setFixedSize(42, 42)
        brand_file = asset_path("sarman-translate.ico")
        if not brand_file.is_file():
            brand_file = asset_path("sarman-translate.svg")
        if brand_file.is_file():
            brand_icon.setPixmap(QIcon(str(brand_file)).pixmap(42, 42))
        brand_row.addWidget(brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        brand = QLabel("SARMAN")
        brand.setObjectName("brand")
        brand2 = QLabel("TRANSLATE")
        brand2.setObjectName("brandSub")
        brand_text.addWidget(brand)
        brand_text.addWidget(brand2)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        side.addLayout(brand_row)
        side.addSpacing(24)
        nav_title = QLabel("ÇALIŞMA ALANI")
        nav_title.setObjectName("eyebrow")
        side.addWidget(nav_title)
        self.nav_library = QPushButton("▦   Oyun kütüphanesi")
        self.nav_patch = QPushButton("⇧   Yama merkezi")
        self.nav_library.setObjectName("navActive")
        self.nav_patch.setObjectName("navButton")
        self.nav_library.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.nav_patch.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        side.addWidget(self.nav_library)
        side.addWidget(self.nav_patch)
        side.addStretch()
        version = QLabel("DESKTOP  ·  ÖN SÜRÜM\nYerelleştirme araçları")
        version.setObjectName("sideFoot")
        side.addWidget(version)
        shell.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 25, 30, 22)
        layout.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.page_title = QLabel("Oyun kütüphanesi")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Oyununu seç, metinleri tara ve Türkçe yamayı oluştur.")
        self.page_subtitle.setObjectName("muted")
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_subtitle)
        header.addLayout(heading)
        header.addStretch()
        self.scan_btn = QPushButton("⟳   Oyunları tara")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.start_scan)
        header.addWidget(self.scan_btn)
        layout.addLayout(header)

        self.pages = QTabWidget()
        self.pages.setDocumentMode(True)
        self.pages.tabBar().hide()
        self.pages.currentChanged.connect(self.page_changed)
        layout.addWidget(self.pages, 1)

        library = QWidget()
        lib = QVBoxLayout(library)
        lib.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        label = QLabel("Oyun listen")
        label.setObjectName("sectionTitle")
        row.addWidget(label)
        row.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Oyun veya klasör ara…")
        self.search.setMaximumWidth(300)
        self.search.textChanged.connect(self.render_games)
        row.addWidget(self.search)
        self.studio_btn = QPushButton("Çeviri Atölyesi")
        self.studio_btn.setObjectName("primary")
        self.studio_btn.setEnabled(False)
        self.studio_btn.clicked.connect(self.open_translation_studio)
        row.addWidget(self.studio_btn)
        self.remove_game_patches_btn = QPushButton("Yamaları kaldır")
        self.remove_game_patches_btn.setEnabled(False)
        self.remove_game_patches_btn.clicked.connect(self.remove_all_patches)
        self.recover_incomplete_btn = QPushButton("Yarım kalan yüklemeyi geri al")
        self.recover_incomplete_btn.setEnabled(False)
        self.recover_incomplete_btn.clicked.connect(self.recover_incomplete_install)
        lib.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["OYUN", "PLATFORM", "DİL / YAMA DURUMU"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        lib.addWidget(self.table, 1)
        language_row = QHBoxLayout()
        language_title = QLabel("OYUNUN METİN DİLİ")
        language_title.setObjectName("eyebrow")
        language_row.addWidget(language_title)
        self.source_language_combo = QComboBox()
        self.source_language_combo.setMinimumWidth(210)
        self.source_language_combo.setEnabled(False)
        self.source_language_combo.currentIndexChanged.connect(self.source_language_changed)
        language_row.addWidget(self.source_language_combo)
        self.source_language_hint = QLabel("Bir oyun seçtiğinde bulunan dil dosyaları burada listelenir.")
        self.source_language_hint.setObjectName("muted")
        language_row.addWidget(self.source_language_hint, 1)
        lib.addLayout(language_row)
        patch_manage_row = QHBoxLayout()
        patch_manage_row.addStretch()
        patch_manage_row.addWidget(self.remove_game_patches_btn)
        patch_manage_row.addWidget(self.recover_incomplete_btn)
        lib.addLayout(patch_manage_row)
        self.library_status = QLabel("Hazır · Henüz tarama yapılmadı")
        self.library_status.setObjectName("muted")
        lib.addWidget(self.library_status)
        self.pages.addTab(library, "Kütüphane")

        patch_page = QWidget()
        patch_layout = QVBoxLayout(patch_page)
        patch_layout.setContentsMargins(0, 0, 0, 0)
        package = QFrame()
        package.setObjectName("panel")
        pl = QVBoxLayout(package)
        pl.setContentsMargins(20, 18, 20, 18)
        pl.addWidget(QLabel("1  /  YAMA PAKETİ"))
        self.patch_file_label = QLabel("Henüz bir yama paketi seçilmedi.")
        self.patch_file_label.setObjectName("muted")
        self.patch_file_label.setWordWrap(True)
        pl.addWidget(self.patch_file_label)
        patch_actions = QHBoxLayout()
        self.choose_patch_btn = QPushButton("Yama dosyası seç (.zip)")
        self.choose_patch_btn.clicked.connect(self.choose_patch)
        patch_actions.addWidget(self.choose_patch_btn)
        self.remove_partial_patch_btn = QPushButton("Yarım kalan yamayı sil")
        self.remove_partial_patch_btn.clicked.connect(self.remove_partial_patch_file)
        patch_actions.addWidget(self.remove_partial_patch_btn)
        patch_actions.addStretch()
        pl.addLayout(patch_actions)
        self.patch_info = QLabel("Paket seçildiğinde adı, sürümü ve dosya sayısı burada görünür.")
        self.patch_info.setObjectName("muted")
        pl.addWidget(self.patch_info)
        patch_layout.addWidget(package)
        target = QFrame()
        target.setObjectName("panel")
        tl = QVBoxLayout(target)
        tl.setContentsMargins(20, 18, 20, 18)
        tl.addWidget(QLabel("2  /  HEDEF OYUN"))
        self.target_label = QLabel("Önce Oyun kütüphanesi bölümünden bir oyun seç.")
        self.target_label.setObjectName("muted")
        self.target_label.setWordWrap(True)
        tl.addWidget(self.target_label)
        actions = QHBoxLayout()
        self.install_btn = QPushButton("Yamayı yükle")
        self.install_btn.setObjectName("primary")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self.apply_patch)
        self.uninstall_btn = QPushButton("Son yamayı geri al")
        self.uninstall_btn.clicked.connect(self.rollback_patch)
        self.uninstall_all_btn = QPushButton("Tüm yamaları kaldır")
        self.uninstall_all_btn.clicked.connect(self.remove_all_patches)
        actions.addWidget(self.install_btn)
        actions.addWidget(self.uninstall_btn)
        actions.addWidget(self.uninstall_all_btn)
        actions.addStretch()
        tl.addLayout(actions)
        patch_layout.addWidget(target)
        warning = QLabel("Güvenlik: Yalnızca bu uygulamanın manifestli yama paketleri kabul edilir. Yüklemeden önce hedefleri doğrula; oyun çevrimiçi/anti-cheat korumalıysa dosya yaması uygulama.")
        warning.setObjectName("warning")
        warning.setWordWrap(True)
        patch_layout.addWidget(warning)
        patch_layout.addStretch()
        self.pages.addTab(patch_page, "Yama merkezi")
        shell.addWidget(content, 1)

    def apply_style(self):
        self.setStyleSheet("""
            QWidget { background:#0c0d10; color:#eeeae5; font-family:'Segoe UI'; font-size:13px; }
            QFrame#sidebar { background:#101115; border-right:1px solid #24252a; }
            QLabel#brand { font-size:24px; font-weight:900; letter-spacing:2px; color:#f4f0eb; }
            QLabel#brandSub { color:#e58a43; font-size:11px; font-weight:800; letter-spacing:3px; }
            QLabel#sideFoot { color:#777a82; font-size:10px; line-height:1.5; }
            QLabel#eyebrow { color:#e58a43; font-size:10px; font-weight:800; letter-spacing:1.7px; }
            QLabel#pageTitle { font-size:23px; font-weight:750; }
            QLabel#muted { color:#92949c; }
            QLabel#heroTitle { font-size:27px; font-weight:750; padding:3px 0; }
            QLabel#sectionTitle { font-size:17px; font-weight:700; }
            QFrame#hero { background:#17181d; border:1px solid #303137; border-radius:13px; }
            QFrame#statCard, QFrame#panel { background:#141519; border:1px solid #292a30; border-radius:11px; }
            QLabel#statValue { font-size:17px; font-weight:700; padding-top:4px; }
            QPushButton { background:#1a1b20; border:1px solid #34353c; border-radius:8px; padding:10px 14px; font-weight:650; }
            QPushButton:hover { border-color:#e58a43; background:#24201c; }
            QPushButton:disabled { color:#666870; background:#17181c; border-color:#292a30; }
            QPushButton#primary { background:#e58a43; color:#1a120c; border:0; padding:11px 17px; font-weight:800; }
            QPushButton#primary:hover { background:#f09a55; }
            QPushButton#navButton, QPushButton#navActive { text-align:left; padding:12px 11px; border:0; }
            QPushButton#navButton { background:transparent; color:#a2a3aa; }
            QPushButton#navActive { background:#292019; color:#f0a36a; border-left:3px solid #e58a43; }
            QLineEdit { background:#141519; border:1px solid #303138; border-radius:8px; padding:10px 12px; color:#fff; }
            QLineEdit:focus { border-color:#e58a43; }
            QTableWidget { background:#111216; border:1px solid #292a30; border-radius:10px; padding:5px; selection-background-color:#35271d; }
            QHeaderView::section { background:#17181d; color:#92949c; border:0; padding:12px 9px; font-size:10px; font-weight:800; }
            QTableWidget::item { padding:9px 8px; border-bottom:1px solid #24252a; }
            QLabel#warning { color:#dca879; background:#211b16; border:1px solid #493323; border-radius:8px; padding:12px; }
            QComboBox { background:#141519; border:1px solid #34353c; border-radius:8px; padding:8px 10px; min-width:150px; }
            QComboBox::drop-down { border:0; width:25px; }
            QComboBox QAbstractItemView { background:#17181d; selection-background-color:#35271d; }
        """)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, APP_NAME, "Oyun taraması tamamlanana kadar uygulama kapatılamaz.")
            event.ignore()
            return
        event.accept()

    def page_changed(self, index):
        is_patch = index == 1
        self.page_title.setText("Yama merkezi" if is_patch else "Oyun kütüphanesi")
        self.page_subtitle.setText("Harici Türkçe yamalarını güvenli biçimde yönet." if is_patch else "Kurulu oyunlarını otomatik bul; dil dosyalarını ve Sarman yama durumunu görüntüle.")
        self.nav_library.setObjectName("navButton" if is_patch else "navActive")
        self.nav_patch.setObjectName("navActive" if is_patch else "navButton")
        self.nav_library.style().unpolish(self.nav_library)
        self.nav_library.style().polish(self.nav_library)
        self.nav_patch.style().unpolish(self.nav_patch)
        self.nav_patch.style().polish(self.nav_patch)

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Taranıyor…")
        self.library_status.setText("Oyun kütüphaneleri taranıyor…")
        worker = ScanWorker(parent=self)
        self.worker = worker
        worker.completed.connect(self.scan_finished)
        worker.failed.connect(self.scan_failed)
        worker.finished.connect(self._scan_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _scan_thread_finished(self):
        worker = self.sender()
        if worker is self.worker:
            self.worker = None

    def scan_finished(self, games):
        worker = self.sender()
        if worker is not None and worker is not self.worker:
            return
        self.studio_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.remove_game_patches_btn.setEnabled(False)
        self.recover_incomplete_btn.setEnabled(False)
        self.source_language_combo.clear()
        self.source_language_combo.setEnabled(False)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.target_label.setText("Önce Oyun kütüphanesi bölümünden bir oyun seç.")
        self.games = games
        self.render_games()
        self.library_status.setText(f"Tarama tamamlandı · {len(games)} oyun bulundu")
        self.selection_changed()
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⟳   Yeniden tara")

    def scan_failed(self, message):
        worker = self.sender()
        if worker is not None and worker is not self.worker:
            return
        self.library_status.setText("Tarama sırasında hata oluştu")
        QMessageBox.warning(self, APP_NAME, message)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⟳   Yeniden tara")

    def render_games(self):
        selected = self.selected_game()
        selected_path = selected.path if selected else None
        query = self.search.text().casefold()
        items = [g for g in self.games if query in g.name.casefold() or query in g.platform.casefold() or query in g.path.casefold()]
        self.table.blockSignals(True)
        self.table.setRowCount(len(items))
        for row, game in enumerate(items):
            patched = installed_patch_languages(game.path)
            detected = " · ".join(game.detected_languages) if game.detected_languages else "Belirlenemedi"
            patch_status = " · ".join(code.upper() for code in sorted(patched)) + " yüklü" if patched else "Yüklü değil"
            status = f"{detected}  ·  {patch_status}"
            values = (game.name, game.platform, status)
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if col == 0:
                    cell.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
                self.table.setItem(row, col, cell)
            self.table.item(row, 0).setData(Qt.UserRole, game.path)
        if selected_path:
            for row, game in enumerate(items):
                if game.path == selected_path:
                    self.table.selectRow(row)
                    break
        self.table.blockSignals(False)
        self.selection_changed()

    def _language_setting_key(self, game):
        import hashlib
        identity = hashlib.sha256(os.path.normcase(os.path.abspath(game.path)).encode("utf-8")).hexdigest()
        return f"source-language/{identity}"

    def source_language_changed(self):
        game = self.selected_game()
        if not game:
            return
        code = self.source_language_combo.currentData()
        if not code:
            return
        self.language_settings.setValue(self._language_setting_key(game), code)
        if code == "EN":
            self.source_language_hint.setText("İngilizce → Türkçe · Hy-MT2 otomatik çevirisi destekleniyor.")
        else:
            self.source_language_hint.setText(
                f"{LANGUAGE_LABELS.get(code, code)} kaynak seçildi. Otomatik model şu anda yalnızca İngilizce → Türkçe destekliyor; elle çeviri ve yama oluşturma kullanılabilir."
            )

    def selected_game(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        name_item = self.table.item(row, 0)
        if not name_item:
            return None
        path = name_item.data(Qt.UserRole)
        return next((g for g in self.games if g.path == path), None)

    def selection_changed(self):
        game = self.selected_game()
        if game:
            self.studio_btn.setEnabled(True)
            self.target_label.setText(f"{game.name}  ·  {game.path}")
            self.install_btn.setEnabled(bool(self.patch_path))
            self.remove_game_patches_btn.setEnabled(bool(installed_patch_languages(game.path)))
            self.recover_incomplete_btn.setEnabled(bool(incomplete_patch_installs(game.path)))
            codes = sorted(set(game.detected_languages) | {"EN"}, key=lambda code: (code != "EN", code))
            saved = str(self.language_settings.value(self._language_setting_key(game), "EN")).upper()
            if saved not in codes:
                saved = "EN"
            self.source_language_combo.blockSignals(True)
            self.source_language_combo.clear()
            for code in codes:
                self.source_language_combo.addItem(f"{code}  ·  {LANGUAGE_LABELS.get(code, code)}", code)
            self.source_language_combo.setCurrentIndex(max(0, self.source_language_combo.findData(saved)))
            self.source_language_combo.setEnabled(True)
            self.source_language_combo.blockSignals(False)
            self.source_language_changed()
        else:
            self.studio_btn.setEnabled(False)
            self.target_label.setText("Önce Oyun kütüphanesi bölümünden bir oyun seç.")
            self.install_btn.setEnabled(False)
            self.remove_game_patches_btn.setEnabled(False)
            self.recover_incomplete_btn.setEnabled(False)
            self.source_language_combo.blockSignals(True)
            self.source_language_combo.clear()
            self.source_language_combo.setEnabled(False)
            self.source_language_combo.blockSignals(False)
            self.source_language_hint.setText("Bir oyun seçtiğinde bulunan dil dosyaları burada listelenir.")

    def open_translation_studio(self):
        game = self.selected_game()
        if not game:
            QMessageBox.information(self, APP_NAME, "Önce oyun listesinden bir oyun seç.")
            return
        source_language = self.source_language_combo.currentData() or "EN"
        if not Path(game.path).is_dir():
            QMessageBox.warning(self, APP_NAME, "Oyun klasörü artık bulunamıyor. Oyunları yeniden tara ve kurulum konumunu kontrol et.")
            return
        try:
            dialog = TranslationStudio(game, self, source_language=source_language)
            dialog.exec()
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Çeviri Atölyesi açılamadı:\n{exc}")

    def remove_partial_patch_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Yarım kalan Sarman yama dosyasını seç", "",
            "Yarım kalan yama dosyaları (*.zip.tmp *.sarman-tmp)"
        )
        if not filename:
            return
        answer = QMessageBox.question(
            self, "Yarım kalan yama silinsin mi?",
            f"Bu geçici yama dosyası tamamen silinecek:\n{filename}\n\nDevam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            removed = remove_incomplete_patch(filename)
            QMessageBox.information(self, APP_NAME, "Yarım kalan yama dosyası silindi." if removed else "Dosya artık bulunmuyor.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Yama dosyası silinemedi:\n{exc}")

    def recover_incomplete_install(self):
        game = self.selected_game()
        if not game:
            return
        pending = incomplete_patch_installs(game.path)
        if not pending:
            self.selection_changed()
            return
        names = "\n".join(f"• {item['name']} ({item['files']} dosya kaydı)" for item in pending)
        answer = QMessageBox.question(
            self, "Yarım kalan yükleme geri alınsın mı?",
            f"{game.name} için tamamlanmamış yama işlemleri bulundu:\n{names}\n\n"
            "Orijinal dosyalar yedeklerden geri yüklenecek. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            recovered = rollback_incomplete_patches(game.path)
            self.render_games()
            QMessageBox.information(self, APP_NAME, f"{len(recovered)} yarım kalan yama yüklemesi geri alındı.")
        except (PatchError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Geri alma tamamlanamadı. Yedek kayıtları korundu.\n\n{exc}")

    def choose_patch(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Sarman yama paketi seç", "", "Yama paketleri (*.zip)")
        if not filename:
            return
        try:
            manifest = inspect_patch(filename)
            self.patch_path = filename
            self.patch_manifest = manifest
            self.patch_file_label.setText(filename)
            self.patch_info.setText(f"{manifest['name']}  ·  Sürüm {manifest['version']}  ·  {len(manifest['files'])} dosya")
            self.install_btn.setEnabled(self.selected_game() is not None)
        except PatchError as exc:
            self.patch_path = None
            self.patch_manifest = None
            self.patch_file_label.setText("Geçerli bir yama paketi seçilmedi.")
            self.patch_info.setText("Paket okunamadı. Başka bir ZIP seçebilirsin.")
            self.install_btn.setEnabled(False)
            QMessageBox.warning(self, APP_NAME, str(exc))

    def apply_patch(self):
        game = self.selected_game()
        if not game or not self.patch_path:
            return
        target_game = (self.patch_manifest or {}).get("target_game")
        if target_game and target_game.casefold() != game.name.casefold():
            QMessageBox.warning(self, APP_NAME, f"Bu yama '{target_game}' için hazırlanmış; seçili oyun '{game.name}'. Yanlış oyuna yükleme engellendi.")
            return
        answer = QMessageBox.question(self, "Yama yüklensin mi?",
            f"'{game.name}' klasörüne dosya yazılacak. Mevcut dosyalar yedeklenecek. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            result = install_patch(self.patch_path, game.path)
            self.render_games()
            self.selection_changed()
            QMessageBox.information(self, APP_NAME, f"{result['name']} yüklendi.\nYedek: {result['backup']}")
        except (PatchError, OSError) as exc:
            QMessageBox.critical(self, APP_NAME, f"Yama yüklenemedi:\n{exc}")

    def remove_all_patches(self):
        game = self.selected_game()
        if not game:
            QMessageBox.information(self, APP_NAME, "Önce oyun listesinden bir oyun seç.")
            return
        answer = QMessageBox.question(
            self, "Tüm Sarman yamaları kaldırılsın mı?",
            f"'{game.name}' için Sarman TRANSLATE tarafından yüklenen tüm yamalar geri alınacak. "
            "Orijinal dosyalar yedeklerden geri yüklenir. Bu işlem başka modları kaldırmaz. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            names = uninstall_all(game.path)
            self.render_games()
            self.selection_changed()
            QMessageBox.information(self, APP_NAME,
                f"{len(names)} yama kaldırıldı." if names else "Bu oyun için kayıtlı Sarman yaması bulunamadı.")
        except (PatchError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Yama kaldırma durdu. Dosyalar ve yedek kayıtları korundu.\n\n{exc}")

    def rollback_patch(self):
        game = self.selected_game()
        if not game:
            QMessageBox.information(self, APP_NAME, "Önce oyun listesinden bir oyun seç.")
            return
        answer = QMessageBox.question(self, "Yama geri alınsın mı?",
            "Bu oyun için kaydedilmiş en son Sarman yaması geri alınacak. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            name = uninstall_latest(game.path)
            self.render_games()
            self.selection_changed()
            QMessageBox.information(self, APP_NAME, f"{name} geri alındı.")
        except (PatchError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))


def main():
    install_exception_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion("0.1.0")
    icon_file = asset_path("sarman-translate.ico")
    if not icon_file.is_file():
        icon_file = asset_path("sarman-translate.svg")
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
