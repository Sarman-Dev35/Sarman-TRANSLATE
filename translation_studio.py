from __future__ import annotations

import json
import hashlib
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, QProgressBar, QLineEdit
)

from translation_core import TextEntry, scan_game_texts, load_workspace, save_workspace, build_translated_files, create_translation_patch, validate_translation
from local_engine import APP_DATA, translate_text, model_status, install_english_turkish_model, uninstall_english_turkish_model, LocalTranslationError, glossary_items, set_glossary_term, delete_glossary_term


class GlossaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sarman · Terim Sözlüğü")
        self.resize(560, 480)
        root = QVBoxLayout(self)
        title = QLabel("Oyun terimleri")
        title.setStyleSheet("font-size:19px;font-weight:750;color:#e58a43")
        root.addWidget(title)
        root.addWidget(QLabel("Eklediğin karşılıklar bütün çevirilerde tutarlı biçimde kullanılır. Var olan terimi aynı İngilizce ifadeyle ekleyerek güncelleyebilirsin."))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["İNGİLİZCE TERİM", "TÜRKÇE KARŞILIĞI"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)
        fields = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("İngilizce terim")
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Türkçe karşılığı")
        fields.addWidget(self.source_input)
        fields.addWidget(self.target_input)
        root.addLayout(fields)
        actions = QHBoxLayout()
        add_btn = QPushButton("Terimi ekle / güncelle")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.add_term)
        remove_btn = QPushButton("Seçileni sil")
        remove_btn.clicked.connect(self.remove_term)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(add_btn)
        actions.addWidget(remove_btn)
        actions.addStretch()
        actions.addWidget(close_btn)
        root.addLayout(actions)
        self.setStyleSheet("""
            QDialog,QWidget{background:#0c0d10;color:#eeeae5;font-family:'Segoe UI';}
            QTableWidget{background:#111216;border:1px solid #292a30;selection-background-color:#35271d;}
            QHeaderView::section{background:#17181d;color:#e58a43;padding:9px;border:0;}
            QLineEdit{background:#141519;border:1px solid #34353c;border-radius:7px;padding:9px;color:#fff;}
            QPushButton{background:#1a1b20;border:1px solid #34353c;border-radius:7px;padding:9px 12px;}
            QPushButton#primary{background:#e58a43;color:#1a120c;border:0;font-weight:800;}
        """)
        self.reload_terms()

    def reload_terms(self):
        terms = glossary_items()
        self.table.setRowCount(len(terms))
        for row, (source, target) in enumerate(terms):
            self.table.setItem(row, 0, QTableWidgetItem(source))
            self.table.setItem(row, 1, QTableWidgetItem(target))

    def add_term(self):
        source, target = self.source_input.text().strip(), self.target_input.text().strip()
        if not source or not target:
            QMessageBox.information(self, "Terim sözlüğü", "İki alanı da doldur.")
            return
        try:
            set_glossary_term(source, target)
            self.source_input.clear()
            self.target_input.clear()
            self.reload_terms()
        except Exception as exc:
            QMessageBox.warning(self, "Terim sözlüğü", str(exc))

    def remove_term(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Terim sözlüğü", "Önce silmek istediğin terimi seç.")
            return
        source = self.table.item(row, 0).text()
        answer = QMessageBox.question(self, "Terim silinsin mi?", f"'{source}' sözlükten kaldırılsın mı?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            delete_glossary_term(source)
            self.reload_terms()


class TextScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, game_dir, source_language="EN", parent=None):
        super().__init__(parent)
        self.game_dir = str(game_dir)
        self.source_language = str(source_language or "EN").upper()

    def run(self):
        try:
            self.completed.emit(scan_game_texts(self.game_dir))
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateWorker(QThread):
    progress = Signal(int, int, str)
    row_done = Signal(int, str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, entries, indices, game_name, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.indices = indices
        self.game_name = game_name

    def run(self):
        groups = {}
        for index in self.indices:
            entry = self.entries[index]
            nearby = []
            for other_index in range(max(0, index - 2), min(len(self.entries), index + 3)):
                other = self.entries[other_index]
                if other_index != index and other.file == entry.file and other.source.strip():
                    nearby.append(other.source)
            context = "\n".join(nearby)
            groups.setdefault((entry.source, context), []).append(index)

        total = len(self.indices)
        done = 0
        for (source, context), indices in groups.items():
            try:
                result = translate_text(source, context=context, game_name=self.game_name)
                for index in indices:
                    self.row_done.emit(index, result)
                    done += 1
                self.progress.emit(done, total, source[:72])
            except LocalTranslationError as exc:
                entry = self.entries[indices[0]]
                self.failed.emit(f"{entry.file} · {entry.locator}: {exc}")
                return
        self.completed.emit()


class ModelInstallWorker(QThread):
    completed = Signal()
    failed = Signal(str)
    progress = Signal(int, int, float, int)

    def run(self):
        try:
            install_english_turkish_model(lambda done, total, speed, eta: self.progress.emit(done, total, speed, eta))
            self.completed.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslationStudio(QDialog):
    def __init__(self, game, parent=None, source_language="EN"):
        super().__init__(parent)
        self.game = game
        self.source_language = str(source_language or "EN").upper()
        self.entries: list[TextEntry] = []
        game_identity = hashlib.sha256(str(Path(game.path).resolve()).casefold().encode("utf-8")).hexdigest()[:10]
        language_suffix = "" if self.source_language == "EN" else "-" + self._safe_name(self.source_language).lower()
        self.workspace_path = APP_DATA / "workspaces" / (self._safe_name(game.name) + "-" + game_identity + language_suffix + ".json")
        self._operation_busy = False
        self.worker = None
        self.scan_worker = None
        self._scan_generation = 0
        self._rendering = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(750)
        self.autosave_timer.timeout.connect(lambda: self.save(silent=True))
        self.setWindowTitle(f"Çeviri Atölyesi · {game.name}")
        self.resize(1050, 700)
        self._build()
        self._load_existing()
        self.refresh_model_status()

    @staticmethod
    def _safe_name(value):
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:80] or "game"

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel(f"{self.game.name}  /  ÇEVİRİ ATÖLYESİ")
        title.setStyleSheet("font-size:20px;font-weight:800;color:#e58a43")
        root.addWidget(title)
        self.language_label = QLabel(
            f"KAYNAK DİL: {self.source_language}  →  HEDEF DİL: TÜRKÇE"
            + ("  ·  Otomatik model desteği mevcut." if self.source_language == "EN"
               else "  ·  Otomatik model şu anda yalnızca İngilizce kaynak metinleri destekliyor.")
        )
        self.language_label.setStyleSheet("color:#b9a18d;font-weight:700;padding:4px 0;")
        root.addWidget(self.language_label)
        root.addWidget(QLabel("Seçilen kaynak diline ait açık metin dosyaları taranır. Orijinal oyun dosyaları çeviri sırasında değiştirilmez."))
        actions = QHBoxLayout()
        self.scan_btn = QPushButton("Metinleri tara")
        self.scan_btn.clicked.connect(self.scan)
        self.translate_btn = QPushButton("Bekleyenleri çevir")
        self.translate_btn.clicked.connect(self.translate_pending)
        self.export_btn = QPushButton("Yama ZIP'i oluştur")
        self.export_btn.clicked.connect(self.export_patch)
        self.glossary_btn = QPushButton("Terim sözlüğü")
        self.glossary_btn.clicked.connect(self.manage_glossary)
        self.model_btn = QPushButton("Modeli indir · 1,13 GB")
        self.model_btn.clicked.connect(self.install_model)
        self.remove_model_btn = QPushButton("Modeli cihazdan kaldır")
        self.remove_model_btn.clicked.connect(self.remove_model)
        self.remove_model_btn.setVisible(False)
        for button in (self.scan_btn, self.translate_btn, self.model_btn, self.remove_model_btn, self.glossary_btn, self.export_btn):
            actions.addWidget(button)
        root.addLayout(actions)
        self.model_status_label = QLabel("")
        self.model_status_label.setStyleSheet("color:#b9a18d;padding:4px;")
        root.addWidget(self.model_status_label)
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
        self._scan_generation += 1
        generation = self._scan_generation
        worker = TextScanWorker(self.game.path, self.source_language, self)
        self.scan_worker = worker
        worker.generation = generation
        worker.completed.connect(self.scan_completed)
        worker.failed.connect(self.scan_failed)
        worker.finished.connect(self._scan_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _scan_thread_finished(self):
        worker = self.sender()
        if worker is self.scan_worker:
            self.scan_worker = None

    def scan_completed(self, found):
        worker = self.sender()
        if worker is not None and worker is not self.scan_worker:
            return
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
        self.refresh_model_status()

    def scan_failed(self, message):
        worker = self.sender()
        if worker is not None and worker is not self.scan_worker:
            return
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

    def manage_glossary(self):
        GlossaryDialog(self).exec()

    def refresh_model_status(self):
        info = model_status()
        self.model_status_label.setText(
            info["message"] + "  ·  " + info.get("model_path", "")
            + "  ·  İlk kurulum internet gerektirir; sonrasında çevrimdışı çalışır."
        )
        self.model_btn.setVisible(not info["installed"])
        if info.get("partial_present"):
            self.model_btn.setText("İndirmeye devam et")
        elif info.get("present"):
            self.model_btn.setText("Bozuk modeli yeniden indir")
        else:
            self.model_btn.setText("Modeli indir · 1,13 GB")
        busy = self._operation_busy or bool(self.worker and self.worker.isRunning())
        self.model_btn.setEnabled(not info["installed"] and not busy)
        has_model_files = bool(info.get("present") or info.get("partial_present"))
        self.remove_model_btn.setVisible(has_model_files)
        self.remove_model_btn.setEnabled(has_model_files and not busy)
        self.translate_btn.setEnabled(
            info["installed"] and bool(self.entries) and self.source_language == "EN" and not busy
        )

    def install_model(self):
        if self.worker and self.worker.isRunning():
            return
        self.model_btn.setEnabled(False)
        self.remove_model_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Model indiriliyor · %p%")
        self.status.setText("Hy-MT2 İngilizce → Türkçe çeviri modeli indiriliyor…")
        self.model_status_label.setText("Bağlantı kuruluyor… · yaklaşık 1,13 GB")
        self.worker = ModelInstallWorker(self)
        self.worker.completed.connect(self._model_installed)
        self.worker.failed.connect(self._model_install_failed)
        self.worker.finished.connect(self._worker_thread_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.progress.connect(self._model_download_progress)
        self.worker.start()

    def _model_download_progress(self, downloaded, total, speed, eta):
        if total > 0:
            percent = min(100, int(downloaded * 100 / total))
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            speed_text = f"{speed / (1024 * 1024):.2f} MB/sn" if speed > 0 else "hız ölçülüyor…"
            eta_text = f" · yaklaşık {eta // 60} dk {eta % 60} sn kaldı" if eta > 0 else ""
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
            self.progress.setFormat(f"Model indiriliyor · %p%")
            self.model_status_label.setText(
                f"İndirilen: {mb_done:,.1f} / {mb_total:,.1f} MB  ·  {speed_text}{eta_text}"
            )

    def _model_installed(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Model indirildi ve doğrulandı · %p%")
        self.status.setText("Hy-MT2 hazır. Artık internet olmadan çeviri yapabilirsin.")
        self.refresh_model_status()

    def remove_model(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Çeviri sürüyor", "Model kullanımdayken kaldırılamaz. Çevirinin tamamlanmasını bekle.")
            return
        info = model_status()
        if not (info.get("present", False) or info.get("partial_present", False)):
            self.refresh_model_status()
            return
        answer = QMessageBox.question(
            self, "Çeviri modeli kaldırılsın mı?",
            "Hy-MT2 model dosyası uygulamanın .exe dosyasının bulunduğu klasörden silinecek. "
            "Terim sözlüğün, çeviri hafızan ve oyun çalışma kayıtların korunacak. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            removed = uninstall_english_turkish_model()
            self.status.setText("Çeviri modeli cihazdan kaldırıldı." if removed else "Silinecek model dosyası bulunamadı.")
            self.refresh_model_status()
        except LocalTranslationError as exc:
            QMessageBox.warning(self, "Model kaldırılamadı", str(exc))

    def _model_install_failed(self, message):
        self.status.setText("Model kurulumu başarısız.")
        self.model_btn.setEnabled(True)
        self.refresh_model_status()
        QMessageBox.warning(self, "Çeviri modeli", message)

    def translate_pending(self):
        if self.source_language != "EN":
            QMessageBox.information(
                self, "Kaynak dil desteklenmiyor",
                "Bu sürümdeki Hy-MT2 modeli yalnızca İngilizce → Türkçe çeviri yapabiliyor. "
                "Seçili dil dosyalarını tarayabilir ve elle çevirebilirsin; otomatik çeviri için İngilizce seç."
            )
            return
        info = model_status()
        if not info["installed"]:
            QMessageBox.information(self, "Çeviri modeli", "Önce yaklaşık 1,13 GB boyutundaki Hy-MT2 çeviri modelini indir.")
            return
        indices = [i for i, entry in enumerate(self.entries) if entry.status != "translated" or not entry.translated]
        if not indices:
            QMessageBox.information(self, "Çeviri", "Çevrilecek bekleyen metin yok.")
            return
        self._set_busy(True)
        self.progress.setRange(0, len(indices))
        self.worker = TranslateWorker(self.entries, indices, self.game.name, self)
        self.worker.progress.connect(self._translation_progress)
        self.worker.row_done.connect(self._translation_done)
        self.worker.failed.connect(self._translation_failed)
        self.worker.completed.connect(self._translation_completed)
        self.worker.finished.connect(self._worker_thread_finished)
        self.worker.finished.connect(self.worker.deleteLater)
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

    def _translation_failed(self, message):
        self._set_busy(False)
        self.autosave_timer.stop()
        self.save()
        QMessageBox.warning(self, "Yerel çeviri hatası", message)

    def _translation_completed(self):
        self._set_busy(False)
        self.autosave_timer.stop()
        self.save()
        self.status.setText("Yapay zekâ çevirisi tamamlandı. Terimleri ve kelime oyunlarını gözden geçir.")

    def _worker_thread_finished(self):
        worker = self.sender()
        if worker is self.worker:
            self.worker = None
        self._operation_busy = False
        self.refresh_model_status()

    def _set_busy(self, busy):
        self._operation_busy = busy
        self.scan_btn.setEnabled(not busy and not (self.scan_worker and self.scan_worker.isRunning()))
        self.export_btn.setEnabled(not busy and bool(self.entries))
        self.glossary_btn.setEnabled(not busy)
        self.table.setEditTriggers(
            QTableWidget.NoEditTriggers if busy
            else (QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        )
        self.refresh_model_status()

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
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.information(self, "Yama", "Metin taraması bitmeden yama oluşturulamaz.")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Yama", "Çeviri işlemi bitmeden yama oluşturulamaz.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Yama paketini kaydet", f"{self._safe_name(self.game.name)}-tr.zip", "ZIP (*.zip)")
        if not filename:
            return
        try:
            created = create_translation_patch(self.game.path, self.entries, filename, self.game.name)
            QMessageBox.information(self, "Yama oluşturuldu", f"Yama paketi oluşturuldu ve doğrulandı:\n{created}\n\nNot: Paket yalnızca desteklenen metin dosyalarını içerir. Oyunun bu dosyaları yüklemesi/etkinleştirmesi oyun motoruna bağlıdır.")
        except Exception as exc:
            QMessageBox.critical(self, "Yama oluşturma", str(exc))
