from __future__ import annotations

import json
import hashlib
from pathlib import Path

import credential_store
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, QProgressBar
)

from translation_core import TextEntry, scan_game_texts, load_workspace, save_workspace, build_translated_files, create_translation_patch, validate_translation
from gemini_translator import translate_batch, GeminiTranslationError
from quota_testing import quota_test_remaining

SERVICE = "Sarman.TRANSLATE.Gemini"


class TextScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.game_dir = game_dir

    def run(self):
        try:
            self.completed.emit(scan_game_texts(self.game_dir))
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateWorker(QThread):
    progress = Signal(int, int, str)
    row_done = Signal(int, str)
    paused = Signal(str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, entries, api_key, model, indices, simulate_quota=False):
        super().__init__()
        self.entries = entries
        self.api_key = api_key
        self.model = model
        self.indices = indices
        self.simulate_quota = simulate_quota

    def run(self):
        if self.simulate_quota:
            self.paused.emit("TEST_QUOTA_SIMULATION")
            return
        total = len(self.indices)
        completed = 0
        groups: dict[str, list[int]] = {}
        memory: dict[str, str] = {}
        for entry in self.entries:
            if entry.translated.strip() and not validate_translation(entry.source, entry.translated):
                memory.setdefault(entry.source, entry.translated)
        for index in self.indices:
            groups.setdefault(self.entries[index].source, []).append(index)
        pending = []
        for source, indices in groups.items():
            if source in memory:
                for index in indices:
                    self.row_done.emit(index, memory[source])
                completed += len(indices)
                self.progress.emit(completed, total, source[:80])
            else:
                pending.append((source, indices))
        batch_size = 5
        for offset in range(0, len(pending), batch_size):
            chunk = pending[offset:offset + batch_size]
            payload = [(str(indices[0]), source) for source, indices in chunk]
            try:
                translated = translate_batch(self.api_key, self.model, payload)
                for source, indices in chunk:
                    result = translated[str(indices[0])]
                    memory[source] = result
                    for index in indices:
                        self.row_done.emit(index, result)
                    completed += len(indices)
                    self.progress.emit(completed, total, source[:80])
            except GeminiTranslationError as exc:
                if exc.quota:
                    self.paused.emit(str(exc))
                else:
                    source, indices = chunk[0]
                    first = self.entries[indices[0]]
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
        self.scan_worker = None
        self._rendering = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(750)
        self.autosave_timer.timeout.connect(lambda: self.save(silent=True))
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
        if self.scan_worker and self.scan_worker.isRunning():
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Çeviri sürüyor", "Önce mevcut çeviri kuyruğunun tamamlanmasını bekle.")
            return
        self._set_scan_busy(True)
        self.status.setText("Oyun metinleri arka planda taranıyor…")
        self.scan_worker = TextScanWorker(self.game.path, self)
        self.scan_worker.completed.connect(self.scan_completed)
        self.scan_worker.failed.connect(self.scan_failed)
        self.scan_worker.start()

    def scan_completed(self, found):
        existing = {entry.entry_id: entry for entry in self.entries}
        merged = []
        for entry in found:
            previous = existing.get(entry.entry_id)
            if previous and previous.source == entry.source:
                entry.translated = previous.translated
                entry.status = previous.status
            merged.append(entry)
        self.entries = merged
        self.render()
        self.save()
        self.status.setText(f"Tarama tamamlandı · {len(self.entries)} metin bulundu.")
        self._set_scan_busy(False)

    def scan_failed(self, message):
        self._set_scan_busy(False)
        self.status.setText("Metin taraması başarısız.")
        QMessageBox.warning(self, "Metin tarama", message)

    def _set_scan_busy(self, busy):
        self.scan_btn.setEnabled(not busy)
        self.translate_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers if busy else (QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed))


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

    def save(self, silent=False):
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
        try:
            self.workspace_path.parent.mkdir(parents=True, exist_ok=True)
            save_workspace(self.workspace_path, self.game.path, self.entries)
            if not silent:
                self.status.setText(f"Çalışma kaydedildi · {self.workspace_path}")
        except Exception as exc:
            if silent:
                self.status.setText(f"Otomatik kaydetme başarısız: {exc}")
            else:
                QMessageBox.warning(self, "Kaydetme", str(exc))

    def translate_pending(self):
        try:
            api_key = credential_store.get_password(SERVICE, "user-api-key")
            model = credential_store.get_password(SERVICE, "model")
        except Exception as exc:
            QMessageBox.warning(self, "Gemini API", f"Windows kimlik bilgisi kasası açılamadı: {exc}")
            return
        if not api_key:
            QMessageBox.information(self, "Gemini API", "Önce Ayarlar > Gemini API bölümünden kendi API anahtarını kaydet.")
            return
        if not model:
            QMessageBox.information(self, "Gemini API", "Önce Gemini API ayarlarında bağlantıyı test et ve kullanılabilir bir model seç.")
            return
        indices = [i for i, entry in enumerate(self.entries) if entry.status != "translated" or not entry.translated]
        if not indices:
            QMessageBox.information(self, "Çeviri", "Çevrilecek bekleyen metin yok.")
            return
        self._set_busy(True)
        self.progress.setRange(0, len(indices))
        self.worker = TranslateWorker(self.entries, api_key, model, indices, simulate_quota=quota_test_remaining() > 0)
        self.worker.progress.connect(self._translation_progress)
        self.worker.row_done.connect(self._translation_done)
        self.worker.paused.connect(self._quota_paused)
        self.worker.failed.connect(self._translation_failed)
        self.worker.completed.connect(self._translation_completed)
        self.worker.start()

    def _translation_done(self, index, result):
        self.entries[index].translated = result
        self.entries[index].status = "translated"
        if 0 <= index < self.table.rowCount():
            self._rendering = True
            status_cell = self.table.item(index, 0)
            translation_cell = self.table.item(index, 3)
            if status_cell:
                status_cell.setText("translated")
            if translation_cell:
                translation_cell.setText(result)
            self._rendering = False
        if not self.autosave_timer.isActive():
            self.autosave_timer.start()

    def _translation_progress(self, completed, total, current_text):
        self.progress.setValue(completed)
        self.status.setText(f"{completed}/{total} çevrildi · {current_text}")

    def _quota_paused(self, message):
        self._set_busy(False)
        self.autosave_timer.stop()
        self.save()
        if message == "TEST_QUOTA_SIMULATION":
            self.status.setText("TEST MODU — Çeviri API isteği gönderilmeden duraklatıldı. Çalışma kaydedildi.")
            QMessageBox.information(
                self, "Kota duraklatma testi",
                "Test başarılı: çeviri kuyruğu güvenli biçimde duraklatıldı ve çalışma kaydedildi. "
                "Bu test Gemini API'ye istek göndermedi, gerçek kotanı tüketmedi. "
                "Bekleme süresi sona erdiğinde 'Bekleyenleri çevir' düğmesiyle devam edebilirsin."
            )
            return
        self.status.setText("Kota nedeniyle duraklatıldı. Tamamlanan çeviriler kaydedildi.")
        QMessageBox.warning(self, "Gemini kotası", "API isteği kota sınırına takıldı. İlerleme kaydedildi. Google API erişimi tekrar kullanılabilir olduğunda veya farklı bir projeye ait uygun anahtar eklediğinde bekleyenleri sürdürebilirsin.\n\n" + message)

    def _translation_failed(self, message):
        self._set_busy(False)
        self.autosave_timer.stop()
        self.save()
        QMessageBox.warning(self, "Çeviri hatası", message)

    def _translation_completed(self):
        self._set_busy(False)
        self.autosave_timer.stop()
        self.save()
        self.status.setText("Çeviri kuyruğu tamamlandı. Çevirileri gözden geçir.")

    def _set_busy(self, busy):
        for button in (self.scan_btn, self.translate_btn, self.export_btn):
            button.setEnabled(not busy)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers if busy else (QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed))

    def closeEvent(self, event):
        if (self.worker and self.worker.isRunning()) or (self.scan_worker and self.scan_worker.isRunning()):
            QMessageBox.information(self, "İşlem sürüyor", "Tarama veya çeviri işlemi tamamlanana kadar bu pencereyi kapatamazsın. Tamamlanan çeviriler otomatik kaydedilir.")
            event.ignore()
            return
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
            self.save(silent=True)
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
