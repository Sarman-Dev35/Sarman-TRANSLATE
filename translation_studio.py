from __future__ import annotations

import json
import hashlib
from pathlib import Path

import keyring
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, QProgressBar
)

from translation_core import TextEntry, scan_game_texts, load_workspace, save_workspace, build_translated_files, create_translation_patch, validate_translation
from gemini_translator import translate_batch, GeminiTranslationError

SERVICE = "Sarman.TRANSLATE.Gemini"


class TranslateWorker(QThread):
    progress = Signal(int, int, str)
    row_done = Signal(int, str)
    paused = Signal(str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, entries, api_key, model, indices):
        super().__init__()
        self.entries = entries
        self.api_key = api_key
        self.model = model
        self.indices = indices

    def run(self):
        total = len(self.indices)
        completed = 0
        batch_size = 5
        for offset in range(0, total, batch_size):
            chunk = self.indices[offset:offset + batch_size]
            payload = [(str(index), self.entries[index].source) for index in chunk]
            try:
                translated = translate_batch(self.api_key, self.model, payload)
                for index in chunk:
                    self.row_done.emit(index, translated[str(index)])
                completed += len(chunk)
                self.progress.emit(completed, total, self.entries[chunk[-1]].source[:80])
            except GeminiTranslationError as exc:
                if exc.quota:
                    self.paused.emit(str(exc))
                else:
                    first = self.entries[chunk[0]]
                    self.failed.emit(f"{first.file} · {first.locator}: {exc}")
                return
        self.completed.emit()


class TranslationStudio(QDialog):
    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.entries: list[TextEntry] = []
        game_identity = hashlib.sha256(str(Path(game.path).resolve()).casefold().encode("utf-8")).hexdigest()[:10]
        self.workspace_path = Path.home() / "AppData" / "Local" / "Sarman" / "TRANSLATE" / "workspaces" / (self._safe_name(game.name) + "-" + game_identity + ".json")
        self.worker = None
        self._rendering = False
        self.setWindowTitle(f"Çeviri Atölyesi · {game.name}")
        self.resize(1050, 700)
        self._build()
        self._load_existing()

    @staticmethod
    def _safe_name(value):
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:80] or "game"

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel(f"{self.game.name}  /  ÇEVİRİ ATÖLYESİ")
        title.setStyleSheet("font-size:20px;font-weight:800;color:#e58a43")
        root.addWidget(title)
        root.addWidget(QLabel("Desteklenen metin dosyaları salt okunur biçimde taranır. Orijinal oyun dosyaları çeviri sırasında değiştirilmez."))
        actions = QHBoxLayout()
        self.scan_btn = QPushButton("Metinleri tara")
        self.scan_btn.clicked.connect(self.scan)
        self.translate_btn = QPushButton("Bekleyenleri çevir")
        self.translate_btn.clicked.connect(self.translate_pending)
        self.export_btn = QPushButton("Yama ZIP'i oluştur")
        self.export_btn.clicked.connect(self.export_patch)
        self.save_btn = QPushButton("Çalışmayı kaydet")
        self.save_btn.clicked.connect(self.save)
        for button in (self.scan_btn, self.translate_btn, self.save_btn, self.export_btn):
            actions.addWidget(button)
        root.addLayout(actions)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["DURUM", "DOSYA / KONUM", "KAYNAK METİN", "TÜRKÇE ÇEVİRİ"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemChanged.connect(self._cell_edited)
        root.addWidget(self.table, 1)
        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.status = QLabel("Hazır.")
        root.addWidget(self.status)
        self.setStyleSheet("""
            QDialog,QWidget{background:#0c0d10;color:#eeeae5;font-family:'Segoe UI';}
            QTableWidget{background:#111216;border:1px solid #292a30;selection-background-color:#35271d;}
            QHeaderView::section{background:#17181d;color:#e58a43;padding:8px;border:0;}
            QTableWidget::item{padding:7px;}
            QPushButton{background:#1a1b20;border:1px solid #34353c;border-radius:7px;padding:9px;}
            QPushButton:hover{border-color:#e58a43;}
        """)

    def _load_existing(self):
        if self.workspace_path.is_file():
            try:
                data = load_workspace(self.workspace_path)
                if Path(data["game_dir"]).resolve() == Path(self.game.path).resolve():
                    self.entries = [TextEntry(**item) for item in data["entries"]]
                    self.render()
                    self.status.setText(f"Kaydedilmiş çalışma yüklendi · {len(self.entries)} metin")
            except Exception:
                self.status.setText("Önceki çalışma okunamadı; yeni tarama yapabilirsin.")

    def scan(self):
        try:
            found = scan_game_texts(self.game.path)
            existing = {e.entry_id: e for e in self.entries}
            self.entries = [existing.get(e.entry_id, e) for e in found]
            self.render()
            self.save()
            self.status.setText(f"Tarama tamamlandı · {len(self.entries)} metin bulundu.")
        except Exception as exc:
            QMessageBox.warning(self, "Metin tarama", str(exc))

    def render(self):
        self._rendering = True
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            values = (entry.status, f"{entry.file}\n{entry.locator}", entry.source, entry.translated)
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col in (0, 1, 2):
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, cell)
        self._rendering = False

    def _cell_edited(self, cell):
        if self._rendering or cell.column() != 3 or cell.row() >= len(self.entries):
            return
        entry = self.entries[cell.row()]
        entry.translated = cell.text()
        entry.status = "translated" if not validate_translation(entry.source, entry.translated) else "review"
        self.table.item(cell.row(), 0).setText(entry.status)
        self.save()

    def save(self):
        try:
            self.workspace_path.parent.mkdir(parents=True, exist_ok=True)
            save_workspace(self.workspace_path, self.game.path, self.entries)
            self.status.setText(f"Çalışma kaydedildi · {self.workspace_path}")
        except Exception as exc:
            QMessageBox.warning(self, "Kaydetme", str(exc))

    def translate_pending(self):
        try:
            api_key = keyring.get_password(SERVICE, "user-api-key")
            model = keyring.get_password(SERVICE, "model") or "gemini-2.5-flash"
        except Exception as exc:
            QMessageBox.warning(self, "Gemini API", f"Windows kimlik bilgisi kasası açılamadı: {exc}")
            return
        if not api_key:
            QMessageBox.information(self, "Gemini API", "Önce Ayarlar > Gemini API bölümünden kendi API anahtarını kaydet.")
            return
        indices = [i for i, entry in enumerate(self.entries) if entry.status != "translated" or not entry.translated]
        if not indices:
            QMessageBox.information(self, "Çeviri", "Çevrilecek bekleyen metin yok.")
            return
        self._set_busy(True)
        self.progress.setRange(0, len(indices))
        self.worker = TranslateWorker(self.entries, api_key, model, indices)
        self.worker.progress.connect(lambda n, total, text: (self.progress.setValue(n), self.status.setText(f"{n}/{total} çevrildi · {text}")))
        self.worker.row_done.connect(self._translation_done)
        self.worker.paused.connect(self._quota_paused)
        self.worker.failed.connect(self._translation_failed)
        self.worker.completed.connect(self._translation_completed)
        self.worker.start()

    def _translation_done(self, index, result):
        self.entries[index].translated = result
        self.entries[index].status = "translated"
        self.render()
        self.save()

    def _quota_paused(self, message):
        self._set_busy(False)
        self.save()
        self.status.setText("Kota nedeniyle duraklatıldı. Tamamlanan çeviriler kaydedildi.")
        QMessageBox.warning(self, "Gemini kotası", "API kotası doldu. İlerleme kaydedildi; aynı Google Cloud projesinin kotası yenilendiğinde veya farklı bir projeye ait uygun anahtar eklediğinde bekleyenleri sürdürebilirsin.\n\n" + message)

    def _translation_failed(self, message):
        self._set_busy(False)
        self.save()
        QMessageBox.warning(self, "Çeviri hatası", message)

    def _translation_completed(self):
        self._set_busy(False)
        self.save()
        self.status.setText("Çeviri kuyruğu tamamlandı. Çevirileri gözden geçir.")

    def _set_busy(self, busy):
        for button in (self.scan_btn, self.translate_btn, self.export_btn):
            button.setEnabled(not busy)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers if busy else (QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Çeviri sürüyor", "Çeviri kuyruğu tamamlanana kadar bu pencereyi kapatamazsın. Tamamlanan satırlar otomatik kaydedilir.")
            event.ignore()
            return
        event.accept()

    def export_patch(self):
        if not any(e.translated.strip() for e in self.entries):
            QMessageBox.information(self, "Yama", "Önce en az bir metni çevir.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Yama paketini kaydet", f"{self._safe_name(self.game.name)}-tr.zip", "ZIP (*.zip)")
        if not filename:
            return
        try:
            create_translation_patch(self.game.path, self.entries, filename, self.game.name)
            QMessageBox.information(self, "Yama oluşturuldu", f"Yama paketi oluşturuldu:\n{filename}\n\nNot: Paket yalnızca desteklenen metin dosyalarını içerir. Oyunun bu dosyaları yüklemesi/etkinleştirmesi oyun motoruna bağlıdır.")
        except Exception as exc:
            QMessageBox.critical(self, "Yama oluşturma", str(exc))
