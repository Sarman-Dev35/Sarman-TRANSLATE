from __future__ import annotations

import json
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import keyring
from PySide6.QtCore import QTimer, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget
)

SERVICE = "Sarman.TRANSLATE.Gemini"
AI_STUDIO_URL = "https://aistudio.google.com/apikey"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class ModelFetchWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key

    def run(self):
        try:
            request = urllib.request.Request(
                MODELS_URL,
                headers={"x-goog-api-key": self.api_key, "Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            models = [
                model for model in data.get("models", [])
                if "generateContent" in model.get("supportedGenerationMethods", [])
            ]
            models.sort(key=lambda model: model.get("name", ""))
            self.completed.emit(models)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            self.failed.emit(f"Google API yanıtı: HTTP {exc.code}. {detail}")
        except Exception as exc:
            self.failed.emit(f"Bağlantı kurulamadı: {type(exc).__name__}: {exc}")


class GeminiSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini API · Sarman TRANSLATE")
        self.setMinimumWidth(570)
        self.deadline = None
        self.model_worker = None
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.update_countdown)
        self.build_ui()
        self.load_key()
        self.setStyleSheet("""
            QDialog, QWidget { background:#0c0d10; color:#eeeae5; font-family:'Segoe UI'; font-size:13px; }
            QLabel#title { font-size:22px; font-weight:750; }
            QLabel#muted { color:#999ba3; }
            QLabel#status { color:#e9a36b; background:#211b16; border:1px solid #493323; border-radius:8px; padding:12px; }
            QLineEdit, QComboBox { background:#141519; border:1px solid #34353c; border-radius:8px; padding:10px; color:#fff; }
            QPushButton { background:#1a1b20; border:1px solid #34353c; border-radius:8px; padding:10px 14px; }
            QPushButton:hover { border-color:#e58a43; }
            QPushButton#primary { background:#e58a43; color:#1a120c; border:0; font-weight:800; }
        """)

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(13)
        title = QLabel("Gemini API ayarları")
        title.setObjectName("title")
        root.addWidget(title)
        intro = QLabel("Kendi Google Gemini API anahtarını ekle. Anahtar yalnızca bu Windows kullanıcı hesabının kimlik bilgisi kasasında saklanır; GitHub'a veya oyun klasörlerine yazılmaz.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Gemini API anahtarını buraya yapıştır")
        self.key_input.setEchoMode(QLineEdit.Password)
        self.show_btn = QPushButton("Göster")
        self.show_btn.clicked.connect(self.toggle_key_visibility)
        row.addWidget(self.key_input, 1)
        row.addWidget(self.show_btn)
        root.addLayout(row)

        actions = QHBoxLayout()
        open_btn = QPushButton("Google AI Studio'yu aç")
        open_btn.clicked.connect(lambda: webbrowser.open(AI_STUDIO_URL))
        save_btn = QPushButton("Anahtarı kaydet")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_key)
        self.test_btn = QPushButton("Bağlantıyı test et")
        self.test_btn.clicked.connect(self.test_key)
        delete_btn = QPushButton("Anahtarı sil")
        delete_btn.clicked.connect(self.delete_key)
        actions.addWidget(open_btn)
        actions.addWidget(delete_btn)
        actions.addStretch()
        actions.addWidget(save_btn)
        actions.addWidget(self.test_btn)
        root.addLayout(actions)

        root.addWidget(QLabel("Kullanılabilir Gemini modeli"))
        self.model_combo = QComboBox()
        self.model_combo.addItem("Bağlantı testi sonrası modeller yüklenecek")
        self.model_combo.currentIndexChanged.connect(self.save_model_choice)
        root.addWidget(self.model_combo)
        self.api_status = QLabel("API anahtarı eklenmedi.")
        self.api_status.setObjectName("status")
        self.api_status.setWordWrap(True)
        root.addWidget(self.api_status)

        root.addWidget(QLabel("Kota uyarısı test komutları"))
        help_text = QLabel("Geliştirici testi içindir. Komutları aşağıya yazıp Enter'a basarak kota uyarısını ve geri sayımı taklit edebilirsin. Gerçek API kotanı değiştirmez.")
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        root.addWidget(help_text)
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("/kotabitimiuyarısı1dk  ·  /kotabitimiuyarısı1saat  ·  /kotabitimiuyarısıgünlük")
        self.command_input.returnPressed.connect(self.run_test_command)
        root.addWidget(self.command_input)
        self.countdown = QLabel("Test sayacı beklemede.")
        self.countdown.setObjectName("status")
        root.addWidget(self.countdown)

        note = QLabel("Not: Google API anahtarları doğrudan uygulama içinden sessizce oluşturulamaz. Google'ın güvenli sayfası açılır; anahtarı sen oluşturup buraya yapıştırırsın. Ücretsiz katman model ve proje limitlerine tabidir.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def load_key(self):
        try:
            value = keyring.get_password(SERVICE, "user-api-key")
            if value:
                self.key_input.setText(value)
                self.api_status.setText("Kayıtlı API anahtarı bulundu. Bağlantıyı test edebilirsin.")
        except Exception:
            self.api_status.setText("Windows kimlik bilgisi kasasına erişilemedi. Anahtar kaydedilemedi.")

    def toggle_key_visibility(self):
        visible = self.key_input.echoMode() == QLineEdit.Password
        self.key_input.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.show_btn.setText("Gizle" if visible else "Göster")

    def save_key(self):
        value = self.key_input.text().strip()
        if not value:
            QMessageBox.warning(self, "Gemini API", "Önce API anahtarını gir.")
            return
        try:
            keyring.set_password(SERVICE, "user-api-key", value)
            self.save_model_choice()
            self.api_status.setText("API anahtarı Windows kimlik bilgisi kasasına kaydedildi.")
            QMessageBox.information(self, "Gemini API", "API anahtarı güvenli yerel kasaya kaydedildi.")
        except Exception as exc:
            QMessageBox.critical(self, "Gemini API", f"Anahtar güvenli biçimde kaydedilemedi: {exc}")

    def delete_key(self):
        answer = QMessageBox.question(self, "API anahtarı silinsin mi?", "Kayıtlı Gemini API anahtarı bu Windows kullanıcı hesabının kimlik bilgisi kasasından silinecek.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            keyring.delete_password(SERVICE, "user-api-key")
            self.key_input.clear()
            self.api_status.setText("Kayıtlı API anahtarı silindi.")
        except keyring.errors.PasswordDeleteError:
            self.api_status.setText("Silinecek kayıtlı API anahtarı bulunamadı.")
        except Exception as exc:
            QMessageBox.warning(self, "Gemini API", f"Anahtar silinemedi: {exc}")

    def save_model_choice(self):
        model = self.model_combo.currentData()
        if model:
            try:
                keyring.set_password(SERVICE, "model", str(model))
            except Exception:
                pass

    def test_key(self):
        value = self.key_input.text().strip()
        if not value:
            QMessageBox.warning(self, "Gemini API", "Test için API anahtarını gir.")
            return
        self.api_status.setText("Google Gemini bağlantısı kontrol ediliyor…")
        self.test_btn.setEnabled(False)
        self.model_worker = ModelFetchWorker(value, self)
        self.model_worker.completed.connect(self.models_loaded)
        self.model_worker.failed.connect(self.models_failed)
        self.model_worker.start()

    def models_loaded(self, models):
        self.model_combo.clear()
        for model in models:
            name = model.get("name", "").removeprefix("models/")
            self.model_combo.addItem(f"{name}  ·  {model.get('displayName', name)}", name)
        preferred = self.model_combo.findData("gemini-2.5-flash")
        if preferred >= 0:
            self.model_combo.setCurrentIndex(preferred)
        self.save_model_choice()
        self.api_status.setText(
            f"Bağlantı başarılı. {len(models)} metin üretimi destekleyen model listelendi. "
            "Modelin listelenmesi ücretsiz kullanım garantisi değildir; erişim ve kota Google projesine göre değişir."
        )
        self.test_btn.setEnabled(True)

    def models_failed(self, message):
        self.api_status.setText(message)
        self.test_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.model_worker and self.model_worker.isRunning():
            self.model_worker.wait(16000)
        event.accept()

    def run_test_command(self):
        command = self.command_input.text().strip().casefold()
        durations = {
            "/kotabitimiuyarısı1dk": 60,
            "/kotabitimiuyarısı1saat": 3600,
            "/kotabitimiuyarısıgünlük": 86400,
        }
        seconds = durations.get(command)
        if seconds is None:
            self.countdown.setText("Komut tanınmadı. Komutları aynen yazıp tekrar dene.")
            return
        self.deadline = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        self.countdown.setText("TEST MODU — Gemini API kotası doldu. Çeviri duraklatıldı. Yeni API ekleyebilir veya yenilenmeyi bekleyebilirsin.")
        self.timer.start()
        self.update_countdown()
        self.command_input.clear()

    def update_countdown(self):
        if not self.deadline:
            return
        remaining = max(0, int((self.deadline - datetime.now(timezone.utc)).total_seconds()))
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.countdown.setText(
            f"TEST MODU — Kota yenilenmesine kalan süre: {hours:02d}:{minutes:02d}:{seconds:02d}"
        )
        if remaining <= 0:
            self.timer.stop()
            self.countdown.setText("TEST TAMAMLANDI — Simüle edilen kota süresi doldu. Gerçek API kotası etkilenmedi.")
            self.deadline = None
