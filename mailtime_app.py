"""
Standalone entry point for mailtime application
"""
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

__version__ = "1.0.0"

if getattr(sys, 'frozen', False):
    application_path = Path(sys._MEIPASS)
else:
    application_path = Path(__file__).parent

if str(application_path) not in sys.path:
    sys.path.insert(0, str(application_path))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QListWidget, QListWidgetItem, QDialog,
    QMessageBox, QSplitter, QLabel, QTextEdit, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import QSizePolicy

from utils import load_svg_icon, get_status_circle, get_resource_path
from workers import FileIOWorker, UpdateChecker
from dialogs import AccountDialog, SettingsDialog, EmailSearchDialog, UpdateDialog
from widgets import MailTab

mailtime_dir = Path.home() / ".mailtime"
mailtime_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(mailtime_dir / 'mail_client.log', mode='w'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('MailClient')


class MailClient(QMainWindow):
    """Main application window with tabbed interface for multiple email accounts"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("mail time!")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)

        self.config_file = Path.home() / ".mailtime" / "config.json"
        self.config = {}
        self.active_workers = []
        self.tab_status_map = {}

        self._setup_ui()
        self._load_local_icon()
        self._load_config_async()

        self.setStyleSheet("* { outline: none; }")

        QTimer.singleShot(2000, self._check_for_updates)

        log.info("Mail client initialized")

    def _setup_ui(self):
        """Setup the main user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_toolbar()

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1a1a1a;
                border: none;
                width: 0px;
                height: 0px;
            }
        """)

        self._setup_accounts_panel()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                margin-top: 6px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background-color: #824ffb;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #3a3a3a;
            }
            QTabBar::close-button {
                width: 18px;
                height: 18px;
                subcontrol-position: right;
                margin: 2px;
            }
        """)

        self.content_splitter.addWidget(self.accounts_panel)
        self.content_splitter.addWidget(self.tabs)
        self.content_splitter.setSizes([0, 1000])

        self.main_layout.addWidget(self.content_splitter)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
                color: #e0e0e0;
            }
        """)

    def _setup_toolbar(self):
        """Setup the main toolbar"""
        toolbar = QWidget()
        toolbar.setFixedHeight(60)
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar.setStyleSheet("background-color: #1a1a1a; border-bottom: 2px solid #824ffb; margin: 0px; padding: 0px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)

        accounts_menu_btn = QPushButton("☰")
        add_account_btn = QPushButton("Add Account")
        add_account_btn.setIcon(load_svg_icon("envelope", 16))
        import_accounts_btn = QPushButton("Import Accounts")
        import_accounts_btn.setIcon(load_svg_icon("folder", 16))
        search_btn = QPushButton("Search")
        search_btn.setIcon(load_svg_icon("search", 16))
        settings_btn = QPushButton("Settings")
        settings_btn.setIcon(load_svg_icon("gear", 16))

        button_style = """
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 15px;
                font-size: 14px;
                font-weight: bold;
                margin-right: 5px;
            }
            QPushButton:hover {
                background-color: #6b3dd9;
            }
            QPushButton:pressed {
                background-color: #5a2ec7;
            }
        """

        for btn in [accounts_menu_btn, add_account_btn, import_accounts_btn, search_btn, settings_btn]:
            btn.setStyleSheet(button_style)

        accounts_menu_btn.clicked.connect(self.toggle_accounts_panel)
        add_account_btn.clicked.connect(self.add_account)
        import_accounts_btn.clicked.connect(self.import_accounts)
        search_btn.clicked.connect(self.open_search)
        settings_btn.clicked.connect(self.open_settings)

        toolbar_layout.addWidget(accounts_menu_btn)
        toolbar_layout.addWidget(add_account_btn)
        toolbar_layout.addWidget(import_accounts_btn)
        toolbar_layout.addWidget(search_btn)
        toolbar_layout.addWidget(settings_btn)
        toolbar_layout.addStretch()

        self.mailbox_icon_btn = QPushButton()
        self.mailbox_icon_btn.setFixedSize(40, 34)
        self.mailbox_icon_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        self.mailbox_icon_btn.setToolTip("Click to open debug log viewer")
        self.mailbox_icon_btn.clicked.connect(self._open_log_viewer)
        toolbar_layout.addWidget(self.mailbox_icon_btn)

        self.main_layout.addWidget(toolbar)

    def _setup_accounts_panel(self):
        """Setup the accounts management panel"""
        self.accounts_panel = QWidget()
        self.accounts_panel.setFixedWidth(0)
        self.accounts_panel.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border-right: 2px solid #3a3a3a;
            }
        """)

        panel_layout = QVBoxLayout(self.accounts_panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        panel_header = QLabel("📧 Account Manager")
        panel_header.setStyleSheet("color: white; font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        panel_layout.addWidget(panel_header)

        self.email_search_bar = QLineEdit()
        self.email_search_bar.setPlaceholderText("🔍 Search accounts...")
        self.email_search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                color: white;
                padding: 8px 12px;
                font-size: 13px;
                margin-bottom: 5px;
            }
            QLineEdit:focus {
                border: 2px solid #824ffb;
                background-color: #242424;
            }
        """)

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._do_email_search)

        self.email_search_bar.textChanged.connect(self._on_search_text_changed)
        panel_layout.addWidget(self.email_search_bar)

        self.accounts_list = QListWidget()
        self.accounts_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item {
                color: #e0e0e0;
                padding: 6px 8px 6px 4px;
                border-radius: 4px;
                margin: 1px;
                font-size: 11px;
            }
            QListWidget::item:selected {
                background-color: #824ffb;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
        """)
        self.accounts_list.itemDoubleClicked.connect(self.switch_to_account_tab)
        panel_layout.addWidget(self.accounts_list)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f44336;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        panel_layout.addWidget(self.clear_all_btn)
        self.clear_all_btn.clicked.connect(self.clear_all_accounts)

    def _load_local_icon(self):
        """Load application icon from resources"""
        try:
            icon_path = get_resource_path("icon.png")
            if Path(icon_path).exists():
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    icon = QIcon(pixmap)
                    self.setWindowIcon(icon)
                    self._icon_pixmap = pixmap
                    log.info("Local icon loaded successfully")
                else:
                    log.warning("Failed to load icon.png - invalid image")
            else:
                log.warning("icon.png not found in project directory")
        except Exception as e:
            log.error(f"Error loading local icon: {e}")

    def _set_toolbar_icon(self):
        """Set the toolbar icon from loaded pixmap"""
        if hasattr(self, '_icon_pixmap') and hasattr(self, 'mailbox_icon_btn'):
            try:
                scaled_pixmap = self._icon_pixmap.scaled(32, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.mailbox_icon_btn.setIcon(QIcon(scaled_pixmap))
                self.mailbox_icon_btn.setIconSize(scaled_pixmap.size())
                log.info("Toolbar icon set successfully")
            except Exception as e:
                log.error(f"Error setting toolbar icon: {e}")

    def _load_config_async(self):
        """Load config file asynchronously"""
        config_worker = FileIOWorker("load_config", config_file_path=str(self.config_file))
        config_worker.config_loaded.connect(self._on_config_loaded)
        config_worker.error.connect(self._on_config_load_error)
        config_worker.finished.connect(lambda: self._cleanup_worker(config_worker))
        self.active_workers.append(config_worker)
        config_worker.start()

    def _on_config_loaded(self, config):
        """Handle config loaded from file"""
        self.config = config
        log.info("Configuration loaded")

        for account in self.config.get("accounts", []):
            if not account.get("hidden", False):
                self._add_mail_tab(account)

        self._update_accounts_list()
        self._set_toolbar_icon()

    def _on_config_load_error(self, error_msg):
        """Handle config loading error"""
        log.warning(f"Could not load config: {error_msg}")
        log.info("Starting with default configuration")

        self.config = {
            "accounts": [],
            "default_imap": {
                "host": "",
                "port": 993,
                "use_ssl": True
            }
        }
        self._save_config()

    def _save_config(self):
        """Save application configuration to disk"""
        config_worker = FileIOWorker("save_config",
                                   config_file_path=str(self.config_file),
                                   config_data=self.config)
        config_worker.config_saved.connect(self._on_config_saved)
        config_worker.error.connect(self._on_config_save_error)
        config_worker.finished.connect(lambda: self._cleanup_worker(config_worker))
        self.active_workers.append(config_worker)
        config_worker.start()

    def _on_config_saved(self, success):
        """Handle config save completion"""
        if success:
            log.debug("Configuration saved successfully")
        else:
            log.error("Failed to save configuration")

    def _on_config_save_error(self, error_msg):
        """Handle config save error"""
        log.error(f"Error saving config: {error_msg}")

    def _cleanup_worker(self, worker):
        """Remove worker from active workers list"""
        if worker in self.active_workers:
            self.active_workers.remove(worker)

    def closeEvent(self, event):
        """Handle application closing - cleanup all threads and close all dialogs"""
        log.info("Application closing, cleaning up threads and dialogs...")

        for widget in QApplication.topLevelWidgets():
            if widget != self and widget.isVisible():
                widget.close()

        for worker in self.active_workers[:]:
            if worker.isRunning():
                worker.quit()
                if not worker.wait(2000):
                    worker.terminate()
                    worker.wait(1000)

        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, 'worker') and tab.worker and tab.worker.isRunning():
                tab.worker.quit()
                if not tab.worker.wait(1000):
                    tab.worker.terminate()

        event.accept()
        log.info("Application cleanup completed")

    def toggle_accounts_panel(self):
        """Show or hide accounts management panel"""
        sizes = self.content_splitter.sizes()
        toolbar_btn = self.sender()

        if sizes[0] == 0:
            toolbar_btn.setText("☰")
            self.accounts_panel.setMinimumWidth(250)
            self.accounts_panel.show()
            self.content_splitter.setSizes([250, sizes[1]])
            self._update_accounts_list()
            log.info("Accounts panel opened")
        else:
            toolbar_btn.setText("☰")
            self.content_splitter.setSizes([0, sizes[0] + sizes[1]])
            self.accounts_panel.hide()
            self.accounts_panel.setMinimumWidth(0)
            log.info("Accounts panel closed")

    def add_account(self):
        """Open dialog to add new email account"""
        dialog = AccountDialog(self, None, self.config.get("default_imap", {}))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            account = dialog.get_account_data()
            new_email = account['email'].lower()

            existing_emails = [acc.get('email', '').lower() for acc in self.config.get("accounts", [])]
            if new_email in existing_emails:
                log.info(f"Account {account['email']} already exists, ignoring duplicate")
                return

            self.config.setdefault("accounts", []).append(account)
            self._save_config()
            self._add_mail_tab(account)
            self._update_accounts_list()
            log.info(f"Added new account: {account['email']}")

    def import_accounts(self):
        """Import accounts from JSON file"""
        from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QPushButton, QHBoxLayout, QDialog
        log.info("Opening import accounts dialog")

        dialog = QDialog(self)
        dialog.setWindowTitle("Import Accounts")
        dialog.setMinimumSize(500, 400)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QTextEdit {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                font-family: monospace;
            }
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9366ff;
            }
        """)

        layout = QVBoxLayout(dialog)

        instructions = QLabel("Import Formats:\n• email:password\n• email:password:name\n• email:password:host:port\n• email:password:name:host:port\n\nFormats without host:port use default settings.\nOne account per line:")
        layout.addWidget(instructions)

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("user@example.com:password123\nuser2@gmail.com:password456:Work Gmail\nuser3@corporate.com:password789:imap.corporate.com:993\nuser4@company.com:password000:Company Mail:imap.company.com:993")
        layout.addWidget(text_edit)

        button_layout = QHBoxLayout()
        import_btn = QPushButton("Import")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(import_btn)
        layout.addLayout(button_layout)

        def import_data():
            """Import configuration data from file"""
            text = text_edit.toPlainText().strip()
            if not text:
                return

            lines = [line.strip() for line in text.split('\n') if line.strip()]
            imported_count = 0

            for line in lines:
                parts = line.split(':')
                if len(parts) == 2:
                    email, password = parts
                    account = {
                        "name": email.split('@')[0] if '@' in email else email,
                        "email": email,
                        "password": password,
                        "use_default": True,
                        "folder": "INBOX"
                    }
                elif len(parts) == 3:
                    email, password, name = parts
                    account = {
                        "name": name,
                        "email": email,
                        "password": password,
                        "use_default": True,
                        "folder": "INBOX"
                    }
                elif len(parts) == 4:
                    email, password, host, port = parts
                    try:
                        port = int(port)
                    except ValueError:
                        continue
                    account = {
                        "name": email.split('@')[0] if '@' in email else email,
                        "email": email,
                        "password": password,
                        "host": host,
                        "port": port,
                        "use_ssl": port == 993,
                        "use_default": False,
                        "folder": "INBOX"
                    }
                elif len(parts) == 5:
                    email, password, name, host, port = parts
                    try:
                        port = int(port)
                    except ValueError:
                        continue
                    account = {
                        "name": name,
                        "email": email,
                        "password": password,
                        "host": host,
                        "port": port,
                        "use_ssl": port == 993,
                        "use_default": False,
                        "folder": "INBOX"
                    }
                else:
                    continue

                # Check for duplicate accounts
                new_email = account['email'].lower()
                existing_emails = [acc.get('email', '').lower() for acc in self.config.get("accounts", [])]
                if new_email in existing_emails:
                    log.info(f"Account {account['email']} already exists, ignoring duplicate")
                    continue

                self.config.setdefault("accounts", []).append(account)
                self._add_mail_tab(account)
                imported_count += 1

            if imported_count > 0:
                self._save_config()
                self._update_accounts_list()
                log.info(f"Imported {imported_count} accounts")

            dialog.accept()

        import_btn.clicked.connect(import_data)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def open_search(self):
        """Open the email search dialog"""
        log.info("Opening search dialog")

        all_cached_emails = []
        for i in range(self.tabs.count()):
            tab_widget = self.tabs.widget(i)
            if hasattr(tab_widget, 'all_emails'):
                for email in tab_widget.all_emails:
                    email_copy = email.copy()
                    email_copy['account_email'] = tab_widget.account.get('email', 'Unknown')
                    all_cached_emails.append(email_copy)

        search_dialog = EmailSearchDialog(self, all_cached_emails)
        search_dialog.show()

    def open_settings(self):
        """Open settings dialog for default IMAP configuration"""
        log.info("Opening settings dialog")
        dialog = SettingsDialog(self, self.config.get("default_imap"))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config["default_imap"] = dialog.get_settings()
            self._save_config()
            log.info(f"Updated default IMAP settings: {self.config['default_imap']}")

    def _add_mail_tab(self, account: Dict):
        """Add a new mail tab for an account"""
        tab = MailTab(account, self.config.get("default_imap", {}), self)
        tab_name = account.get("name", account.get("email", "Unknown"))
        index = self.tabs.addTab(tab, f"🔴 {tab_name}")
        self.tab_status_map[tab] = False
        log.debug(f"Added tab for {account.get('email')}")

        QTimer.singleShot(100, lambda: self._update_accounts_list())
        return index

    def _add_mail_tab_at_position(self, account: Dict, account_index: int):
        """Add a mail tab at the correct position based on config order"""
        tab = MailTab(account, self.config.get("default_imap", {}), self)
        tab_name = account.get("name", account.get("email", "Unknown"))

        target_position = 0
        for i, config_account in enumerate(self.config.get("accounts", [])):
            if i == account_index:
                break
            if not config_account.get("hidden", False):
                target_position += 1

        index = self.tabs.insertTab(target_position, tab, f"🔴 {tab_name}")
        self.tab_status_map[tab] = False
        log.debug(f"Added tab for {account.get('email')} at position {target_position}")

        QTimer.singleShot(100, lambda: self._update_accounts_list())
        return index

    def _truncate_email(self, email):
        """Truncate long email addresses for display only when they would cause horizontal scroll"""
        if '@' not in email:
            return email

        font_metrics = self.accounts_list.fontMetrics()
        available_width = self.accounts_list.width() - 60

        full_text_width = font_metrics.horizontalAdvance(f"🟢 {email}")

        if full_text_width <= available_width:
            return email

        local_part, domain = email.split('@', 1)

        for length in range(len(local_part), 5, -1):
            if length <= 8:
                truncated_local = f"{local_part[:5]}..{local_part[-3:]}"
                test_email = f"{truncated_local}@{domain}"
                test_width = font_metrics.horizontalAdvance(f"🟢 {test_email}")
                if test_width <= available_width:
                    return test_email
            else:
                test_email = f"{local_part[:length]}@{domain}"
                test_width = font_metrics.horizontalAdvance(f"🟢 {test_email}")
                if test_width <= available_width:
                    return test_email

        truncated_local = f"{local_part[:5]}..{local_part[-3:]}"
        return f"{truncated_local}@{domain}"

    def _update_accounts_list(self):
        """Update the accounts list display"""
        self.accounts_list.clear()

        active_accounts = []
        hidden_accounts = []

        for i, account in enumerate(self.config.get("accounts", [])):
            account_email = account.get("email", "Unknown")
            account_name = self._truncate_email(account_email)

            if account.get("hidden", False):
                status = "⚫"
                hidden_accounts.append((status, account_name, i))
            else:
                status = "🔴"
                for j in range(self.tabs.count()):
                    tab_widget = self.tabs.widget(j)
                    if hasattr(tab_widget, 'account') and tab_widget.account == account:
                        tab_status = self.tab_status_map.get(tab_widget, False)
                        if tab_status is None:
                            status = "🟡"
                        elif tab_status is True:
                            status = "🟢"
                        else:
                            status = "🔴"
                        break
                active_accounts.append((status, account_name, i))

        for status, account_name, i in active_accounts + hidden_accounts:
            item_text = f"{status} {account_name}"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, i)
            self.accounts_list.addItem(list_item)

    def switch_to_account_tab(self, item):
        """Switch to the tab for the double-clicked account"""
        account_index = item.data(Qt.ItemDataRole.UserRole)
        if account_index is not None:
            account = self.config.get("accounts", [])[account_index]
            account_email = account.get("email", "")

            if account.get("hidden", False):
                account["hidden"] = False
                self._save_config()
                self._add_mail_tab_at_position(account, account_index)
                self._update_accounts_list()
                for i in range(self.tabs.count()):
                    tab_widget = self.tabs.widget(i)
                    if hasattr(tab_widget, 'account') and tab_widget.account.get("email") == account_email:
                        self.tabs.setCurrentIndex(i)
                        break
            else:
                for i in range(self.tabs.count()):
                    tab_widget = self.tabs.widget(i)
                    if hasattr(tab_widget, 'account') and tab_widget.account.get("email") == account_email:
                        self.tabs.setCurrentIndex(i)
                        break

    def _clear_all_cache_files(self):
        """Clear all email cache files from the mailtime directory"""
        import hashlib
        try:
            mailtime_dir = Path.home() / ".mailtime"
            if not mailtime_dir.exists():
                return

            # Clear cache files for existing accounts
            for account in self.config.get("accounts", []):
                email = account.get('email', '')
                if email:
                    safe_email = hashlib.md5(email.encode()).hexdigest()
                    cache_file = mailtime_dir / f"{safe_email}_emails.json"
                    if cache_file.exists():
                        cache_file.unlink()
                        log.info(f"Removed cache file for {email}")

            # Also clear any orphaned cache files (emails that match the pattern)
            for cache_file in mailtime_dir.glob("*_emails.json"):
                if cache_file.exists():
                    cache_file.unlink()
                    log.info(f"Removed orphaned cache file: {cache_file.name}")

        except Exception as e:
            log.error(f"Error clearing cache files: {e}")

    def clear_all_accounts(self):
        """Clear all accounts with confirmation"""
        if not self.config["accounts"]:
            QMessageBox.information(self, "No Accounts", "There are no accounts to clear.")
            return

        reply = QMessageBox.question(
            self,
            "Clear All Accounts",
            f"Are you sure you want to remove all {len(self.config['accounts'])} email accounts?\n\nThis will:\n• Remove all account configurations\n• Close all open tabs\n• Clear all cached emails\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Close all tabs first
            while self.tabs.count() > 0:
                self.tabs.removeTab(0)

            # Clear all cache files for existing accounts
            self._clear_all_cache_files()

            # Clear all accounts from config
            self.config["accounts"] = []

            # Save empty config
            self._save_config()

            # Update accounts list
            self._update_accounts_list()

            # Clear tab status map
            self.tab_status_map.clear()

            log.info("All accounts cleared by user")
            QMessageBox.information(self, "Accounts Cleared", "All email accounts and cached data have been removed.")

    def close_tab(self, index: int):
        """Close a mail tab"""
        if self.tabs.count() > 0:
            tab_widget = self.tabs.widget(index)
            if hasattr(tab_widget, 'account'):
                for account in self.config["accounts"]:
                    if account == tab_widget.account:
                        account["hidden"] = True
                        break

                account_email = tab_widget.account.get("email", "Unknown")
                if tab_widget in self.tab_status_map:
                    del self.tab_status_map[tab_widget]
                self._save_config()
                self.tabs.removeTab(index)
                self._update_accounts_list()
                log.info(f"Hidden tab for {account_email}")
            else:
                account_email = self.config["accounts"][index].get("email", "Unknown") if index < len(self.config["accounts"]) else "Unknown"
                if tab_widget in self.tab_status_map:
                    del self.tab_status_map[tab_widget]
                self.tabs.removeTab(index)
                self._update_accounts_list()
                log.info(f"Closed tab for {account_email}")

    def _open_log_viewer(self):
        self._play_debug_sound()
        """Open a popup window with the mail_client.log contents"""
        log.info("Opening log viewer")

        dialog = QDialog(self)
        dialog.setWindowTitle("Debug Log Viewer - mail time!")
        dialog.setMinimumSize(900, 700)
        dialog.resize(1200, 800)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setParent(self, Qt.WindowType.Window)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #2a2a2a; padding: 15px; border-bottom: 2px solid #824ffb;")
        header_layout = QHBoxLayout(header_widget)

        title_label = QLabel("Debug Log Viewer")
        title_label.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: bold;")

        refresh_btn = QPushButton(" Refresh")
        refresh_btn.setIcon(load_svg_icon("refresh", 12))
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6b3dd9;
            }
            QPushButton:pressed {
                background-color: #5a2ec7;
            }
        """)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)

        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: none;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
            }
        """)

        def load_log_content():
            """Load log file content asynchronously"""
            refresh_btn.setText("⏳ Loading...")
            refresh_btn.setEnabled(False)
            log_text.setPlainText("Loading log file...")

            log_worker = FileIOWorker("load_log", log_file_path=Path.home() / ".mailtime" / "mail_client.log")
            self.active_workers.append(log_worker)

            def on_log_loaded(content):
                """Handle log content loaded from file"""
                log_text.setPlainText(content)
                cursor = log_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                log_text.setTextCursor(cursor)
                refresh_btn.setText(" Refresh")
                refresh_btn.setIcon(load_svg_icon("refresh", 12))
                refresh_btn.setEnabled(True)
                if log_worker in self.active_workers:
                    self.active_workers.remove(log_worker)

            def on_log_error(error_msg):
                """Handle log loading error"""
                log_text.setPlainText(f"Error reading log file: {error_msg}")
                refresh_btn.setText(" Refresh")
                refresh_btn.setIcon(load_svg_icon("refresh", 12))
                refresh_btn.setEnabled(True)
                if log_worker in self.active_workers:
                    self.active_workers.remove(log_worker)

            log_worker.log_loaded.connect(on_log_loaded)
            log_worker.error.connect(on_log_error)
            log_worker.start()

        refresh_btn.clicked.connect(load_log_content)

        load_log_content()

        layout.addWidget(header_widget)
        layout.addWidget(log_text)

        footer_widget = QWidget()
        footer_widget.setStyleSheet("background-color: #2a2a2a; padding: 10px; border-top: 1px solid #3a3a3a;")
        footer_layout = QHBoxLayout(footer_widget)

        info_label = QLabel("💡 This log shows debug information for troubleshooting connection and sync issues.")
        info_label.setStyleSheet("color: #999; font-size: 12px;")
        footer_layout.addWidget(info_label)

        layout.addWidget(footer_widget)

        original_close_event = dialog.closeEvent
        def dialog_close_event(event):
            for worker in self.active_workers[:]:
                if isinstance(worker, FileIOWorker) and hasattr(worker, 'log_file_path'):
                    if worker.isRunning():
                        worker.quit()
                        worker.wait(1000)
                    if worker in self.active_workers:
                        self.active_workers.remove(worker)
            if original_close_event:
                original_close_event(event)
            else:
                event.accept()

        dialog.closeEvent = dialog_close_event
        dialog.show()

    def _play_debug_sound(self):
        try:
            sound_path = get_resource_path("mail.mp3")
            if sound_path.exists():
                try:
                    import pygame
                    pygame.mixer.init()
                    pygame.mixer.music.load(str(sound_path))
                    pygame.mixer.music.play()
                    log.info("Debug sound played with pygame")
                except ImportError:
                    log.warning("pygame not available, trying alternative...")
                    try:
                        import subprocess
                        import platform
                        system = platform.system().lower()

                        if system == "linux":
                            for player in ["paplay", "aplay", "mpg123", "ffplay"]:
                                try:
                                    subprocess.run([player, str(sound_path)],
                                                 check=True, capture_output=True, timeout=5)
                                    log.info(f"Debug sound played with {player}")
                                    break
                                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                                    continue
                        elif system == "windows":
                            import winsound
                            winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
                            log.info("Debug sound played with winsound")
                        elif system == "darwin":
                            subprocess.run(["afplay", str(sound_path)], check=True)
                            log.info("Debug sound played with afplay")
                    except Exception as fallback_error:
                        log.warning(f"Could not play sound with any method: {fallback_error}")
            else:
                log.warning("mail.mp3 not found in project directory")
        except Exception as e:
            log.error(f"Error playing debug sound: {e}")

    def update_tab_status(self, tab, status):
        """Update tab status: True (green), False (red), 'cache' (yellow)"""
        log.debug(f"update_tab_status called with status: {status}")
        index = self.tabs.indexOf(tab)
        if index >= 0:
            tab_email = tab.account.get('email', '')
            account = None
            for acc in self.config["accounts"]:
                if acc.get('email', '') == tab_email:
                    account = acc
                    break

            if not account:
                log.warning(f"Could not find account config for tab email: {tab_email}")
                return

            tab_name = account.get("name", account.get("email", "Unknown"))

            if status == "cache":
                status_icon = "🟡"
                connected = None
                status_text = "viewing cache"
            elif status is True:
                status_icon = "🟢"
                connected = True
                status_text = "connected"
            else:
                status_icon = "🔴"
                connected = False
                status_text = "disconnected"

            self.tabs.setTabText(index, f"{status_icon} {tab_name}")
            self.tab_status_map[tab] = connected

            if hasattr(self, 'accounts_list'):
                self._update_accounts_list()
            log.debug(f"Updated tab status for {tab_name}: {status_text}")

    def _check_for_updates(self):
        """Check for application updates from GitHub releases"""
        try:
            repo_url = "https://api.github.com/repos/dsql/mailtime/releases/latest"

            self.update_checker = UpdateChecker(__version__, repo_url)
            self.update_checker.update_available.connect(self._on_update_available)
            self.update_checker.no_update.connect(self._on_no_update)
            self.update_checker.error.connect(self._on_update_error)
            self.update_checker.finished.connect(lambda: setattr(self, 'update_checker', None))
            self.update_checker.start()

        except Exception as e:
            log.error(f"Failed to start update check: {e}")

    def _on_update_available(self, latest_version: str, download_url: str, release_notes: str):
        """Handle when an update is available"""
        log.info(f"Update available: {latest_version}")
        try:
            dialog = UpdateDialog(__version__, latest_version, download_url, release_notes, self)
            dialog.exec()
        except Exception as e:
            log.error(f"Failed to show update dialog: {e}")

    def _on_no_update(self):
        """Handle when no update is available"""
        log.debug("No updates available")

    def _on_update_error(self, error_msg: str):
        """Handle update check errors"""
        log.warning(f"Update check failed: {error_msg}")

    def _on_search_text_changed(self, text: str):
        """Handle search text changes with debouncing"""
        self.search_timer.stop()
        self.search_timer.start(300)

    def _do_email_search(self):
        """Perform the actual account search in the hamburger menu"""
        try:
            search_text = self.email_search_bar.text().strip().lower()

            for i in range(self.accounts_list.count()):
                item = self.accounts_list.item(i)
                if item:
                    account_text = item.text().lower()

                    if not search_text or search_text in account_text:
                        item.setHidden(False)
                    else:
                        item.setHidden(True)

            log.debug(f"Filtered accounts list for search: '{search_text}'")

        except Exception as e:
            log.error(f"Error during account search: {e}")

    def _filter_current_tab_emails(self, search_text: str):
        """Filter emails in the current tab based on search text - DEPRECATED"""
        pass

    def _on_tab_changed(self, index):
        """Handle tab changes - clear search when switching tabs"""
        if hasattr(self, 'email_search_bar'):
            self.email_search_bar.clear()
            self._show_all_accounts()

    def _show_all_accounts(self):
        """Show all accounts in the accounts list"""
        try:
            for i in range(self.accounts_list.count()):
                item = self.accounts_list.item(i)
                if item:
                    item.setHidden(False)
        except Exception as e:
            log.error(f"Error showing all accounts: {e}")


if __name__ == "__main__":
    log.info("Starting IMAP Mail Client")
    app = QApplication(sys.argv)
    window = MailClient()
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
    window.showNormal()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())