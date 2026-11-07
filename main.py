from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QTabWidget
)

from patch_manager import PatchError, inspect_patch, install_patch, uninstall_latest
from gemini_settings import GeminiSettingsDialog

APP_NAME = "Sarman TRANSLATE"
ACCENT = "#e58a43"


from game_discovery import Game, discover_games

class ScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            self.completed.emit(discover_games())
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
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self.games: list[Game] = []
        self.worker = None
        self.patch_path: str | None = None
        self.build_ui()
        self.apply_style()

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
        brand = QLabel("SARMAN")
        brand.setObjectName("brand")
        brand2 = QLabel("TRANSLATE")
        brand2.setObjectName("brandSub")
        side.addWidget(brand)
        side.addWidget(brand2)
        side.addSpacing(24)
        nav_title = QLabel("ÇALIŞMA ALANI")
        nav_title.setObjectName("eyebrow")
        side.addWidget(nav_title)
        self.nav_library = QPushButton("▦   Oyun kütüphanesi")
        self.nav_patch = QPushButton("⇧   Yama merkezi")
        self.nav_settings = QPushButton("⚙   Gemini API")
        self.nav_library.setObjectName("navActive")
        self.nav_patch.setObjectName("navButton")
        self.nav_settings.setObjectName("navButton")
        self.nav_library.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.nav_patch.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        self.nav_settings.clicked.connect(self.open_gemini_settings)
        side.addWidget(self.nav_library)
        side.addWidget(self.nav_patch)
        side.addWidget(self.nav_settings)
        side.addStretch()
        version = QLabel("DESKTOP  ·  ÖN SÜRÜM\nYerelleştirme araçları")
        version.setObjectName("sideFoot")
        side.addWidget(version)
        shell.addWidget(side)

        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 25, 30, 22)
        layout.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.page_title = QLabel("Oyun kütüphanesi")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Kurulu oyunlarını bul ve yerelleştirme çalışmalarını yönet.")
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
        hero = QFrame()
        hero.setObjectName("hero")
        h = QVBoxLayout(hero)
        h.setContentsMargins(23, 20, 23, 20)
        eyebrow = QLabel("SARMAN  /  GAME LIBRARY")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Oyunlarını keşfet.")
        title.setObjectName("heroTitle")
        desc = QLabel("Kütüphaneni tara, oyununu seç ve kullanmak istediğin Türkçe yamayı güvenli biçimde yönet. Tarama sırasında oyun dosyalarına dokunulmaz.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        h.addWidget(eyebrow)
        h.addWidget(title)
        h.addWidget(desc)
        lib.addWidget(hero)
        stats = QHBoxLayout()
        self.game_count = StatCard("Bulunan oyun", "0")
        self.source_count = StatCard("Tarama kaynakları", "Steam  ·  Epic  ·  Klasörler")
        stats.addWidget(self.game_count)
        stats.addWidget(self.source_count, 2)
        lib.addLayout(stats)
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
        lib.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["OYUN", "KAYNAK", "KURULUM KONUMU"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        lib.addWidget(self.table, 1)
        self.library_status = QLabel("Hazır · Henüz tarama yapılmadı")
        self.library_status.setObjectName("muted")
        lib.addWidget(self.library_status)
        self.pages.addTab(library, "Kütüphane")

        patch_page = QWidget()
        patch_layout = QVBoxLayout(patch_page)
        patch_layout.setContentsMargins(0, 0, 0, 0)
        patch_hero = QFrame()
        patch_hero.setObjectName("hero")
        ph = QVBoxLayout(patch_hero)
        ph.setContentsMargins(23, 20, 23, 20)
        eyebrow2 = QLabel("SARMAN  /  PATCH CENTER")
        eyebrow2.setObjectName("eyebrow")
        patch_title = QLabel("Hazır yamayı yükle.")
        patch_title.setObjectName("heroTitle")
        patch_desc = QLabel("Başka bir yerden indirdiğin uyumlu Sarman yama paketini seç, hedef oyunu belirle ve yükle. Uygulama mevcut dosyaların yedeğini alır; desteklenen yamalar geri alınabilir.")
        patch_desc.setObjectName("muted")
        patch_desc.setWordWrap(True)
        ph.addWidget(eyebrow2)
        ph.addWidget(patch_title)
        ph.addWidget(patch_desc)
        patch_layout.addWidget(patch_hero)
        package = QFrame()
        package.setObjectName("panel")
        pl = QVBoxLayout(package)
        pl.setContentsMargins(20, 18, 20, 18)
        pl.addWidget(QLabel("1  /  YAMA PAKETİ"))
        self.patch_file_label = QLabel("Henüz bir yama paketi seçilmedi.")
        self.patch_file_label.setObjectName("muted")
        self.patch_file_label.setWordWrap(True)
        pl.addWidget(self.patch_file_label)
        self.choose_patch_btn = QPushButton("Yama dosyası seç (.zip)")
        self.choose_patch_btn.clicked.connect(self.choose_patch)
        pl.addWidget(self.choose_patch_btn, 0, Qt.AlignLeft)
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
        actions.addWidget(self.install_btn)
        actions.addWidget(self.uninstall_btn)
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
        """)

    def open_gemini_settings(self):
        dialog = GeminiSettingsDialog(self)
        dialog.exec()

    def page_changed(self, index):
        is_patch = index == 1
        self.page_title.setText("Yama merkezi" if is_patch else "Oyun kütüphanesi")
        self.page_subtitle.setText("Harici Türkçe yamalarını güvenli biçimde yönet." if is_patch else "Kurulu oyunlarını bul ve yerelleştirme çalışmalarını yönet.")
        self.nav_library.setObjectName("navButton" if is_patch else "navActive")
        self.nav_patch.setObjectName("navActive" if is_patch else "navButton")
        self.nav_library.style().unpolish(self.nav_library)
        self.nav_library.style().polish(self.nav_library)
        self.nav_patch.style().unpolish(self.nav_patch)
        self.nav_patch.style().polish(self.nav_patch)

    def start_scan(self):
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Taranıyor…")
        self.library_status.setText("Oyun kütüphaneleri taranıyor…")
        self.worker = ScanWorker()
        self.worker.completed.connect(self.scan_finished)
        self.worker.failed.connect(self.scan_failed)
        self.worker.start()

    def scan_finished(self, games):
        self.games = games
        self.game_count.value.setText(str(len(games)))
        self.render_games()
        self.library_status.setText(f"Tarama tamamlandı · {len(games)} oyun bulundu")
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⟳   Yeniden tara")

    def scan_failed(self, message):
        self.library_status.setText("Tarama sırasında hata oluştu")
        QMessageBox.warning(self, APP_NAME, message)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⟳   Yeniden tara")

    def render_games(self):
        query = self.search.text().casefold()
        items = [g for g in self.games if query in g.name.casefold() or query in g.platform.casefold() or query in g.path.casefold()]
        self.table.setRowCount(len(items))
        for row, game in enumerate(items):
            for col, value in enumerate((game.name, game.platform, game.path)):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if col == 0:
                    cell.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
                self.table.setItem(row, col, cell)

    def selected_game(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        name_item = self.table.item(row, 0)
        path_item = self.table.item(row, 2)
        if not name_item or not path_item:
            return None
        path = path_item.text()
        return next((g for g in self.games if g.path == path), None)

    def selection_changed(self):
        game = self.selected_game()
        if game:
            self.target_label.setText(f"{game.name}  ·  {game.path}")
            self.install_btn.setEnabled(bool(self.patch_path))
        else:
            self.target_label.setText("Önce Oyun kütüphanesi bölümünden bir oyun seç.")
            self.install_btn.setEnabled(False)

    def choose_patch(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Sarman yama paketi seç", "", "Yama paketleri (*.zip)")
        if not filename:
            return
        try:
            manifest = inspect_patch(filename)
            self.patch_path = filename
            self.patch_file_label.setText(filename)
            self.patch_info.setText(f"{manifest['name']}  ·  Sürüm {manifest['version']}  ·  {len(manifest['files'])} dosya")
            self.install_btn.setEnabled(self.selected_game() is not None)
        except PatchError as exc:
            self.patch_path = None
            self.install_btn.setEnabled(False)
            QMessageBox.warning(self, APP_NAME, str(exc))

    def apply_patch(self):
        game = self.selected_game()
        if not game or not self.patch_path:
            return
        answer = QMessageBox.question(self, "Yama yüklensin mi?",
            f"'{game.name}' klasörüne dosya yazılacak. Mevcut dosyalar yedeklenecek. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            result = install_patch(self.patch_path, game.path)
            QMessageBox.information(self, APP_NAME, f"{result['name']} yüklendi.\nYedek: {result['backup']}")
        except (PatchError, OSError) as exc:
            QMessageBox.critical(self, APP_NAME, f"Yama yüklenemedi:\n{exc}")

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
            QMessageBox.information(self, APP_NAME, f"{name} geri alındı.")
        except (PatchError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
