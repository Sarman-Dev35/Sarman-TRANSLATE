from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView
)

APP_NAME = "Sarman TRANSLATE"
ACCENT = "#a78bfa"


@dataclass
class Game:
    name: str
    platform: str
    path: str
    app_id: str = ""


def steam_roots() -> set[Path]:
    roots: set[Path] = set()
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
        Path.home() / "Steam",
    ]
    for steam in candidates:
        if (steam / "steamapps").is_dir():
            roots.add(steam)
            config = steam / "steamapps" / "libraryfolders.vdf"
            if config.exists():
                try:
                    text = config.read_text(encoding="utf-8", errors="ignore")
                    for value in re.findall(r'"path"\s*"([^"]+)"', text):
                        roots.add(Path(value.replace("\\\\", "\\")))
                except OSError:
                    pass
    return roots


def scan_steam() -> list[Game]:
    found = []
    for root in steam_roots():
        apps = root / "steamapps"
        if not apps.is_dir():
            continue
        for manifest in apps.glob("appmanifest_*.acf"):
            try:
                text = manifest.read_text(encoding="utf-8", errors="ignore")
                name = re.search(r'"name"\s*"([^"]+)"', text)
                appid = re.search(r'"appid"\s*"?(\d+)"?', text)
                install = re.search(r'"installdir"\s*"([^"]+)"', text)
                if name and install:
                    game_path = apps / "common" / install.group(1)
                    if game_path.is_dir():
                        found.append(Game(name.group(1), "Steam", str(game_path), appid.group(1) if appid else ""))
            except OSError:
                continue
    return found


def scan_epic() -> list[Game]:
    found = []
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    manifests = program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifests.is_dir():
        return found
    for item in manifests.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            location = Path(data.get("InstallLocation", ""))
            name = data.get("DisplayName") or data.get("AppName") or location.name
            if location.is_dir():
                found.append(Game(name, "Epic Games", str(location), data.get("AppName", "")))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return found


def scan_common_folders() -> list[Game]:
    found = []
    bases = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        Path("D:/Games"), Path("D:/ oyunlar"), Path.home() / "Games",
    ]
    skip = {"common files", "windowsapps", "windows defender", "internet explorer"}
    seen = set()
    for base in bases:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if child.is_dir() and child.name.casefold() not in skip:
                    key = str(child.resolve()).casefold()
                    if key not in seen:
                        seen.add(key)
                        found.append(Game(child.name, "Klasör taraması", str(child)))
        except (OSError, PermissionError):
            continue
    return found


def discover_games() -> list[Game]:
    all_games = scan_steam() + scan_epic() + scan_common_folders()
    unique = {}
    for game in all_games:
        key = os.path.normcase(os.path.abspath(game.path))
        if key not in unique:
            unique[key] = game
    return sorted(unique.values(), key=lambda g: g.name.casefold())


class ScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            self.completed.emit(discover_games())
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 720)
        self.setMinimumSize(850, 560)
        self.games: list[Game] = []
        self.worker = None
        self.build_ui()
        self.apply_style()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(18)

        top = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("SARMAN <span style='color:#a78bfa'>TRANSLATE</span>")
        title.setTextFormat(Qt.RichText)
        title.setObjectName("brand")
        subtitle = QLabel("AI destekli oyun yerelleştirme aracı")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        top.addLayout(brand)
        top.addStretch()
        self.scan_btn = QPushButton("⌕   Oyunları Tara")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.start_scan)
        top.addWidget(self.scan_btn)
        root.addLayout(top)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        eyebrow = QLabel("İLK ADIM  /  OYUN KÜTÜPHANESİ")
        eyebrow.setObjectName("eyebrow")
        hero_layout.addWidget(eyebrow)
        hero_title = QLabel("Oyunlarını keşfet.")
        hero_title.setObjectName("heroTitle")
        hero_layout.addWidget(hero_title)
        hero_text = QLabel("Steam ve Epic Games kurulumlarını, ayrıca yaygın oyun klasörlerini bul. Bu sürüm yalnızca okuma ve keşif yapar; oyun dosyalarını değiştirmez.")
        hero_text.setObjectName("muted")
        hero_text.setWordWrap(True)
        hero_layout.addWidget(hero_text)
        root.addWidget(hero)

        stats = QHBoxLayout()
        self.count_card = self.make_stat("BULUNAN OYUN", "0")
        self.source_card = self.make_stat("TARAMA KAYNAĞI", "Steam · Epic · Klasörler")
        stats.addWidget(self.count_card)
        stats.addWidget(self.source_card, 2)
        root.addLayout(stats)

        row = QHBoxLayout()
        section = QLabel("Bulunan oyunlar")
        section.setObjectName("section")
        row.addWidget(section)
        row.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Oyun ara…")
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self.render_games)
        row.addWidget(self.search)
        root.addLayout(row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["OYUN", "KAYNAK", "KURULUM KONUMU"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("Hazır · Tarama başlatılmadı")
        self.status.setObjectName("muted")
        bottom.addWidget(self.status)
        bottom.addStretch()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedWidth(150)
        self.progress.hide()
        bottom.addWidget(self.progress)
        root.addLayout(bottom)

    def make_stat(self, label, value):
        card = QFrame()
        card.setObjectName("stat")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        a = QLabel(label)
        a.setObjectName("eyebrow")
        b = QLabel(value)
        b.setObjectName("statValue")
        layout.addWidget(a)
        layout.addWidget(b)
        card.value_label = b
        return card

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0b0b10; color:#f2f0f8; font-family:'Segoe UI'; font-size:13px; }
            QLabel#brand { font-size:23px; font-weight:800; letter-spacing:1px; }
            QLabel#muted { color:#92909f; }
            QLabel#eyebrow { color:#a78bfa; font-size:10px; font-weight:700; letter-spacing:1.5px; }
            QFrame#hero { background:#15141e; border:1px solid #292638; border-radius:14px; }
            QLabel#heroTitle { font-size:25px; font-weight:700; padding:3px 0; }
            QFrame#stat { background:#12121a; border:1px solid #252431; border-radius:12px; }
            QLabel#statValue { font-size:17px; font-weight:700; padding-top:3px; }
            QLabel#section { font-size:17px; font-weight:700; }
            QPushButton { background:#1a1923; border:1px solid #302d3d; border-radius:9px; padding:11px 16px; font-weight:600; }
            QPushButton:hover { border-color:#a78bfa; background:#211e2e; }
            QPushButton#primary { background:#a78bfa; color:#171321; border:0; padding:12px 20px; }
            QPushButton#primary:hover { background:#b9a5ff; }
            QLineEdit { background:#12121a; border:1px solid #302d3d; border-radius:8px; padding:10px 12px; color:#fff; }
            QLineEdit:focus { border-color:#a78bfa; }
            QTableWidget { background:#101017; border:1px solid #252431; border-radius:10px; padding:6px; selection-background-color:#29233c; }
            QHeaderView::section { background:#15141e; color:#8f8b9d; border:0; padding:12px 8px; font-size:10px; font-weight:700; }
            QTableWidget::item { padding:9px 8px; border-bottom:1px solid #22212b; }
            QProgressBar { border:0; background:#242230; border-radius:4px; height:7px; text-align:center; }
            QProgressBar::chunk { background:#a78bfa; border-radius:4px; }
        """)

    def start_scan(self):
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Taranıyor…")
        self.status.setText("Oyun kütüphaneleri aranıyor…")
        self.progress.show()
        self.progress.setRange(0, 0)
        self.worker = ScanWorker()
        self.worker.completed.connect(self.scan_finished)
        self.worker.failed.connect(self.scan_failed)
        self.worker.start()

    def scan_finished(self, games):
        self.games = games
        self.count_card.value_label.setText(str(len(games)))
        self.render_games()
        self.status.setText(f"Tarama tamamlandı · {len(games)} kayıt bulundu")
        self.finish_scan()

    def scan_failed(self, message):
        self.status.setText("Tarama sırasında hata oluştu")
        QMessageBox.warning(self, APP_NAME, f"Oyun taraması tamamlanamadı:\n{message}")
        self.finish_scan()

    def finish_scan(self):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("⌕   Yeniden Tara")
        self.progress.hide()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
