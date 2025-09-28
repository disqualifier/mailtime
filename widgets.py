import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTextEdit,
    QTextBrowser, QDialog, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
from utils import load_svg_icon
from workers import IMAPWorker, FileIOWorker, FolderWorker, IMAPDeleteWorker

log = logging.getLogger('MailClient')


class MailTab(QWidget):
    def __init__(self, account: Dict, default_imap: Dict, parent_window):
        super().__init__()
        self.account = account
        self.default_imap = default_imap
        self.worker = None
        self.parent_window = parent_window
        self.is_connected = False
        self.last_sync_type = None
        self.last_sync_folder = None
        self.viewing_cache = False
        self.sync_error = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: #1a1a1a; padding: 10px;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(10, 5, 10, 5)

        self.folder_label = QLabel(self.account.get('email', 'Unknown'))
        self.folder_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: transparent;
                margin-right: 6px;
            }
            QLabel:hover {
                background-color: #2a2a2a;
            }
        """)
        self.folder_label.setToolTip("Click to copy email address")
        self.folder_label.mousePressEvent = self._copy_email_address
        self.folder_combo = QComboBox()
        self.folder_combo.addItems(["Inbox", "All Folders"])

        self.folder_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px 15px;
                min-width: 120px;
                font-size: 13px;
                margin-right: 4px;
            }
            QComboBox:hover {
                border: 1px solid #824ffb;
                background-color: #353535;
            }
            QComboBox:focus {
                border: 2px solid #824ffb;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                outline: none;
                width: 25px;
                background-color: transparent;
                subcontrol-origin: padding;
                subcontrol-position: top right;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #e0e0e0;
                selection-background-color: #824ffb;
                selection-color: white;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 5px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 15px;
                border-radius: 4px;
                margin: 2px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #3a3a3a;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #824ffb;
                color: white;
            }
        """)

        sync_button_style = """
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 3px;
            }
            QPushButton:hover {
                background-color: #9366ff;
            }
            QPushButton:pressed {
                background-color: #6b3dd9;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #666666;
            }
        """

        self.folder_refresh_btn = QPushButton("")
        self.folder_refresh_btn.setIcon(load_svg_icon("folder", 16))
        self.folder_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                margin-left: 0px;
                margin-right: 4px;
                max-width: 35px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #824ffb;
            }
        """)
        self.folder_refresh_btn.clicked.connect(self.fetch_folders)
        self.folder_refresh_btn.setToolTip("Refresh folder list")

        self.sync_folder_btn = QPushButton("Sync")
        self.sync_folder_btn.setIcon(load_svg_icon("refresh", 12))
        self.sync_folder_btn.setStyleSheet(sync_button_style)
        self.sync_folder_btn.clicked.connect(self.sync_folder)

        self.sync_mailbox_btn = QPushButton("Sync All")
        self.sync_mailbox_btn.setIcon(load_svg_icon("refresh", 12))
        self.sync_mailbox_btn.setStyleSheet(sync_button_style)
        self.sync_mailbox_btn.clicked.connect(self.sync_mailbox)

        self.clear_cache_btn = QPushButton("Clear")
        self.clear_cache_btn.setIcon(load_svg_icon("trash", 12))
        clear_button_style = """
            QPushButton {
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 3px;
            }
            QPushButton:hover {
                background-color: #f44336;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #666666;
            }
        """
        self.clear_cache_btn.setStyleSheet(clear_button_style)
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        self.clear_cache_btn.setToolTip("Clear cached emails for this account")

        self.edit_account_btn = QPushButton()
        self.edit_account_btn.setIcon(load_svg_icon("pen-to-square", 12))
        edit_button_style = """
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 8px;
                margin-right: 3px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
        """
        self.edit_account_btn.setStyleSheet(edit_button_style)
        self.edit_account_btn.clicked.connect(self.edit_account)
        self.edit_account_btn.setToolTip("Edit account settings")

        top_bar_layout.addWidget(self.folder_label)
        top_bar_layout.addWidget(self.edit_account_btn)
        top_bar_layout.addWidget(self.folder_refresh_btn)
        top_bar_layout.addWidget(self.folder_combo)
        top_bar_layout.addWidget(self.sync_folder_btn)
        top_bar_layout.addWidget(self.sync_mailbox_btn)
        top_bar_layout.addWidget(self.clear_cache_btn)
        top_bar_layout.addStretch()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2a2a2a;
                height: 2px;
            }
        """)

        self.email_table = QTableWidget()
        self.email_table.setColumnCount(5)
        self.email_table.setHorizontalHeaderLabels(["ID", "Date", "From", "Subject", "Delete"])

        header = self.email_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.email_table.setColumnWidth(0, 50)
        self.email_table.setColumnWidth(1, 160)
        self.email_table.setColumnWidth(2, 250)
        self.email_table.setColumnWidth(4, 60)
        self.email_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.email_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.email_table.itemSelectionChanged.connect(self._on_email_selected)
        self.email_table.setStyleSheet("""
            QTableWidget {
                background-color: #1a1a1a;
                color: #e0e0e0;
                gridline-color: transparent;
                border: none;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #824ffb;
                color: white;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #e0e0e0;
                padding: 8px;
                border: none;
                border-right: 1px solid #1a1a1a;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background-color: #3a3a3a;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #824ffb;
            }
        """)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        preview_toolbar = QWidget()
        preview_toolbar.setStyleSheet("background-color: #2a2a2a; padding: 5px;")
        preview_toolbar_layout = QHBoxLayout(preview_toolbar)
        preview_toolbar_layout.setContentsMargins(10, 5, 10, 5)

        self.text_view_btn = QPushButton(" Text")
        self.text_view_btn.setIcon(load_svg_icon("file-text", 16))
        self.html_view_btn = QPushButton(" HTML")
        self.html_view_btn.setIcon(load_svg_icon("globe", 16))

        view_button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #824ffb;
                color: white;
            }
        """

        active_button_style = """
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: 1px solid #824ffb;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #9366ff;
                border: 1px solid #9366ff;
            }
        """

        self.text_view_btn.setStyleSheet(active_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
        self.html_view_btn.setStyleSheet(view_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")

        self.text_view_btn.clicked.connect(lambda: self._set_view_mode("text"))
        self.html_view_btn.clicked.connect(lambda: self._set_view_mode("html"))

        self.current_view_mode = "text"

        self.popup_btn = QPushButton(" Pop Out")
        self.popup_btn.setIcon(load_svg_icon("external-link", 16))
        popup_button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-left: 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #824ffb;
                color: white;
            }
        """
        self.popup_btn.setStyleSheet(popup_button_style)
        self.popup_btn.clicked.connect(self._popup_email_viewer)
        self.popup_btn.setToolTip("Open email in popup window")

        preview_toolbar_layout.addWidget(self.text_view_btn)
        preview_toolbar_layout.addWidget(self.html_view_btn)
        preview_toolbar_layout.addStretch()
        preview_toolbar_layout.addWidget(self.popup_btn)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Select an email to preview")
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: none;
                padding: 10px;
                font-size: 13px;
            }
        """)

        self.preview_html = QTextBrowser()
        self.preview_html.setReadOnly(True)
        self.preview_html.setOpenExternalLinks(True)
        self.preview_html.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: none;
                padding: 10px;
            }
        """)
        self.preview_html.hide()

        preview_layout.addWidget(preview_toolbar)
        preview_layout.addWidget(self.preview_text)
        preview_layout.addWidget(self.preview_html)

        splitter.addWidget(self.email_table)
        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(top_bar)
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.emails = []
        self.all_emails = []

        self.folder_combo.currentTextChanged.connect(self._on_folder_changed)

        self._load_cached_emails()

        log.info(f"Created tab for {account.get('email', 'Unknown')}")

    def _on_folder_changed(self, folder_name: str):
        """Handle folder selection change - show only emails from selected folder"""
        log.info(f"Folder changed to: {folder_name}")
        self._filter_emails_by_folder(folder_name)

    def _filter_emails_by_folder(self, folder_name: str):
        """Filter and display emails from the specified folder"""
        if not hasattr(self, 'all_emails') or not self.all_emails:
            log.debug("No emails to filter")
            return

        if folder_name == "All Folders":
            filtered_emails = self.all_emails.copy()
            filtered_emails = sorted(filtered_emails, key=lambda x: x.get('date', ''), reverse=True)
            show_folder_in_subject = True
        elif folder_name == "Inbox":
            filtered_emails = [email for email in self.all_emails
                            if email.get('folder', 'Inbox') in ['Inbox', 'INBOX']]
            show_folder_in_subject = False
        else:
            filtered_emails = [email for email in self.all_emails
                            if email.get('folder', '') == folder_name]
            show_folder_in_subject = False

        log.info(f"Filtering emails: {len(self.all_emails)} total -> {len(filtered_emails)} for folder '{folder_name}'")

        self.email_table.setRowCount(0)
        self.emails = filtered_emails

        for email in filtered_emails:
            row = self.email_table.rowCount()
            self.email_table.insertRow(row)
            self.email_table.setItem(row, 0, QTableWidgetItem(email["id"]))
            self.email_table.setItem(row, 1, QTableWidgetItem(email["date"]))
            self.email_table.setItem(row, 2, QTableWidgetItem(email["from"]))

            subject_text = email["subject"]
            if show_folder_in_subject and email.get('folder'):
                subject_text += f" [{email['folder']}]"
            self.email_table.setItem(row, 3, QTableWidgetItem(subject_text))

            # Add delete button
            delete_btn = QPushButton()
            delete_btn.setIcon(load_svg_icon("trash", 14, "#ff4444"))
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    padding: 4px;
                    margin: 2px;
                }
                QPushButton:hover {
                    background-color: transparent;
                }
                QPushButton:pressed {
                    background-color: transparent;
                }
            """)

            # Handle icon color change on hover manually
            def on_enter(event):
                delete_btn.setIcon(load_svg_icon("trash", 14, "#cc3333"))

            def on_leave(event):
                delete_btn.setIcon(load_svg_icon("trash", 14, "#ff4444"))

            delete_btn.enterEvent = on_enter
            delete_btn.leaveEvent = on_leave
            delete_btn.setToolTip(f"Delete this email")
            delete_btn.clicked.connect(lambda checked, email_data=email: self._delete_email(email_data))
            self.email_table.setCellWidget(row, 4, delete_btn)

        log.info(f"Displayed {len(filtered_emails)} emails for folder '{folder_name}'")

    def _delete_email(self, email_data):
        """Delete a specific email from the inbox and cache"""
        from PyQt6.QtWidgets import QMessageBox

        # Check if we're connected/synced
        if not self.is_connected:
            reply = QMessageBox.question(
                self,
                "Sync Required",
                f"You need to be synced to delete emails from the server.\n\nWould you like to sync now and then delete this email?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Store email data for deletion after sync
                self._pending_delete_email = email_data
                self.sync_folder()
                return
            else:
                return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Delete Email",
            f"Are you sure you want to delete this email from both the server and locally?\n\nFrom: {email_data.get('from', 'Unknown')}\nSubject: {email_data.get('subject', 'No Subject')}\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            email_id = email_data.get('id', '')
            email_folder = email_data.get('folder', 'INBOX')

            # First delete from IMAP server
            if self.account.get("use_default", True):
                host = self.default_imap.get("host", "")
                port = self.default_imap.get("port", 993)
                use_ssl = self.default_imap.get("use_ssl", True)
            else:
                host = self.account.get("host", "")
                port = self.account.get("port", 993)
                use_ssl = self.account.get("use_ssl", True)

            if not host:
                QMessageBox.warning(self, "Delete Error", "No IMAP host configured, cannot delete from server")
                return

            # Show loading cursor
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

            # Start IMAP deletion
            self.delete_worker = IMAPDeleteWorker(
                self.account["email"],
                self.account["password"],
                host,
                port,
                use_ssl,
                email_folder,
                email_id
            )
            self.delete_worker.deleted.connect(lambda success, msg: self._on_email_deleted_from_server(success, msg, email_data))
            self.delete_worker.error.connect(lambda error: self._on_email_delete_error(error, email_data))
            self.delete_worker.finished.connect(lambda: self._restore_cursor())
            self.delete_worker.start()

            log.info(f"Starting IMAP deletion for email: {email_data.get('subject', 'No Subject')}")

        except Exception as e:
            QApplication.restoreOverrideCursor()  # Restore cursor on error
            log.error(f"Error starting email deletion: {e}")
            QMessageBox.critical(self, "Delete Error", f"Failed to start email deletion: {str(e)}")

    def _on_email_deleted_from_server(self, success, message, email_data):
        """Handle successful server deletion"""
        if success:
            # Clear entire cache since IMAP renumbers all emails after delete/expunge
            log.info(f"Email deleted from server and locally: {email_data.get('subject', 'No Subject')}")
            log.info("Clearing cache and resyncing due to IMAP email renumbering")

            # Clear all local data
            self.all_emails = []
            self.emails = []

            # Clear table
            self.email_table.setRowCount(0)

            # Clear preview
            if hasattr(self, 'current_email'):
                self.current_email = None
                self.preview_text.clear()
                self.preview_html.clear()

            # Clear cache file
            self._save_cached_emails()

            # Trigger fresh sync to get correct email IDs from server
            log.info("Starting fresh sync after delete to update email IDs")
            self.sync_folder()

    def _on_email_delete_error(self, error_msg, email_data):
        """Handle email deletion errors"""
        QApplication.restoreOverrideCursor()  # Restore cursor on error
        log.error(f"Error deleting email from server: {error_msg}")
        QMessageBox.critical(self, "Server Delete Error", f"Failed to delete email from server:\n\n{error_msg}\n\nThe email was not deleted.")

    def _restore_cursor(self):
        """Restore normal cursor after async operation"""
        QApplication.restoreOverrideCursor()

    def _check_pending_delete(self):
        """Check if there's a pending email deletion after sync"""
        if hasattr(self, '_pending_delete_email') and self._pending_delete_email:
            email_to_delete = self._pending_delete_email
            self._pending_delete_email = None
            log.info("Processing pending email deletion after sync")
            self._delete_email(email_to_delete)

    def _get_cache_file_path(self):
        """Get the cache file path for this account"""
        email = self.account.get('email', 'unknown')
        safe_email = hashlib.md5(email.encode()).hexdigest()
        cache_dir = Path.home() / ".mailtime"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"{safe_email}_emails.json"

    def _load_cached_emails(self):
        """Load cached emails from disk asynchronously"""
        self._set_cache_loading_state(True)

        self.cache_worker = FileIOWorker("load_cache", cache_file_path=str(self._get_cache_file_path()))
        self.cache_worker.cache_loaded.connect(self._on_cache_loaded)
        self.cache_worker.error.connect(self._on_cache_load_error)
        self.cache_worker.finished.connect(lambda: setattr(self, 'cache_worker', None))
        self.cache_worker.start()

    def _on_cache_loaded(self, cached_data):
        """Handle successful cache loading"""
        try:
            if cached_data and 'emails' in cached_data:
                self.all_emails = cached_data.get('emails', [])
                log.info(f"Loaded {len(self.all_emails)} cached emails asynchronously")

                self.viewing_cache = True
                self.sync_error = None
                log.info(f"Cache loaded for {self.account.get('email')}, setting status to cache (yellow orb)")

                current_folder = self.folder_combo.currentText()
                self._filter_emails_by_folder(current_folder)

                self._update_connection_status("cache")
            else:
                log.debug(f"No cache data found for {self.account.get('email')}")
                self.viewing_cache = False
                self.sync_error = None

            if hasattr(self.parent_window, '_update_accounts_list'):
                self.parent_window._update_accounts_list()

        finally:
            self._set_cache_loading_state(False)

    def _on_cache_load_error(self, error_msg):
        """Handle cache loading errors"""
        log.error(f"Error loading cached emails: {error_msg}")
        self.all_emails = []
        self.viewing_cache = False
        self.sync_error = str(error_msg)
        self._set_cache_loading_state(False)

    def _set_cache_loading_state(self, loading: bool):
        """Show/hide cache loading indicator"""
        if loading:
            self.folder_refresh_btn.setText("")
            self.folder_refresh_btn.setEnabled(False)
            self.sync_folder_btn.setEnabled(False)
            self.sync_mailbox_btn.setEnabled(False)
            self.clear_cache_btn.setEnabled(False)
        else:
            self.folder_refresh_btn.setText("")
            self.folder_refresh_btn.setEnabled(True)
            self.sync_folder_btn.setEnabled(True)
            self.sync_mailbox_btn.setEnabled(True)
            self.clear_cache_btn.setEnabled(True)

    def _save_cached_emails(self):
        """Save emails to disk cache asynchronously"""
        cache_data = {
            'account_email': self.account.get('email'),
            'last_updated': datetime.now().isoformat(),
            'emails': self.all_emails
        }

        self.save_worker = FileIOWorker("save_cache",
                                      cache_file_path=str(self._get_cache_file_path()),
                                      cache_data=cache_data)
        self.save_worker.cache_saved.connect(self._on_cache_saved)
        self.save_worker.error.connect(self._on_cache_save_error)
        self.save_worker.finished.connect(lambda: setattr(self, 'save_worker', None))
        self.save_worker.start()

    def _on_cache_saved(self, success):
        """Handle successful cache saving"""
        if success:
            log.info(f"Saved {len(self.all_emails)} emails to cache file asynchronously")

    def _on_cache_save_error(self, error_msg):
        """Handle cache saving errors"""
        log.error(f"Error saving cached emails: {error_msg}")

    def _clear_cached_emails(self):
        """Clear the email cache for this account asynchronously"""
        self._set_cache_loading_state(True)

        self.all_emails = []
        self.emails = []
        self.email_table.setRowCount(0)

        self.clear_worker = FileIOWorker("clear_cache", cache_file_path=str(self._get_cache_file_path()))
        self.clear_worker.cache_cleared.connect(self._on_cache_cleared)
        self.clear_worker.error.connect(self._on_cache_clear_error)
        self.clear_worker.finished.connect(lambda: setattr(self, 'clear_worker', None))
        self.clear_worker.start()

    def _on_cache_cleared(self, success):
        """Handle successful cache clearing"""
        if success:
            log.info("Cleared cache file asynchronously")

        self.viewing_cache = False
        self.is_connected = False
        self.sync_error = None
        self._update_connection_status(False)

        log.info("Cleared in-memory email cache and updated status to disconnected")
        self._set_cache_loading_state(False)

    def _on_cache_clear_error(self, error_msg):
        """Handle cache clearing errors"""
        log.error(f"Error clearing cached emails: {error_msg}")
        self.viewing_cache = False
        self.is_connected = False
        self.sync_error = None
        self._update_connection_status(False)
        self._set_cache_loading_state(False)

    def clear_cache(self):
        """Clear the email cache for this account with confirmation"""
        reply = QMessageBox.question(
            self,
            "Clear Email Cache",
            f"Are you sure you want to clear all cached emails for {self.account.get('email', 'this account')}?\n\nThis will remove all locally stored emails and you'll need to sync again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_cached_emails()
            log.info(f"User cleared email cache for {self.account.get('email')}")

    def sync_emails(self):
        """Synchronize emails for selected account"""
        self.sync_folder()

    def fetch_folders(self):
        """Fetch available folders from IMAP server and populate the dropdown"""
        log.info(f"Fetching folders for {self.account.get('email')}")

        self._set_loading_state(True)

        if self.account.get("use_default", True):
            host = self.default_imap.get("host", "")
            port = self.default_imap.get("port", 993)
            use_ssl = self.default_imap.get("use_ssl", True)
        else:
            host = self.account.get("host", "")
            port = self.account.get("port", 993)
            use_ssl = self.account.get("use_ssl", True)

        if not host:
            log.warning("No IMAP host configured, cannot fetch folders")
            self._reset_folder_button()
            return

        # Show loading cursor
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.folder_worker = FolderWorker(
            self.account["email"],
            self.account["password"],
            host,
            port,
            use_ssl
        )
        self.folder_worker.folders_fetched.connect(self._on_folders_loaded)
        self.folder_worker.finished.connect(self._reset_folder_button)
        self.folder_worker.finished.connect(self._restore_cursor)
        self.folder_worker.error.connect(lambda: self._restore_cursor())
        self.folder_worker.start()

    def _reset_folder_button(self):
        """Reset folder refresh button to normal state"""
        self._set_loading_state(False)

    def _on_folders_loaded(self, folders):
        """Append fetched folders to the dropdown (INBOX is always first)"""
        current_selection = self.folder_combo.currentText()

        current_items = [self.folder_combo.itemText(i) for i in range(self.folder_combo.count())]

        if folders:
            for folder in folders:
                if (folder not in current_items and
                    folder.upper() != 'INBOX' and
                    folder != 'Inbox' and
                    folder != 'All Folders'):
                    self.folder_combo.addItem(folder)

        if "All Folders" not in current_items:
            self.folder_combo.addItem("All Folders")

        index = self.folder_combo.findText(current_selection)
        if index >= 0:
            self.folder_combo.setCurrentIndex(index)

        log.info(f"Folder list updated with {self.folder_combo.count()} folders")

    def sync_folder(self):
        """Synchronize emails from specific folder"""
        log.info(f"Sync Folder button clicked for {self.account.get('email')}")
        current_folder = self.folder_combo.currentText()

        if current_folder == "All Folders":
            self.sync_mailbox()
            return

        self._disable_sync_buttons("Syncing")
        self.last_sync_type = "folder"
        self.last_sync_folder = current_folder
        self._perform_sync(current_folder)

    def sync_mailbox(self):
        """Synchronize entire mailbox for account"""
        log.info(f"Sync Mailbox button clicked for {self.account.get('email')}")
        self._disable_sync_buttons("Syncing All")
        self.last_sync_type = "mailbox"
        self.last_sync_folder = "ALL"

        folders_to_sync = []
        for i in range(self.folder_combo.count()):
            folder_name = self.folder_combo.itemText(i)
            if folder_name and folder_name != "" and folder_name != "All Folders":
                folders_to_sync.append(folder_name)

        if not folders_to_sync:
            folders_to_sync = ["Inbox"]

        log.info(f"Syncing {len(folders_to_sync)} folders from dropdown: {folders_to_sync}")
        self._sync_multiple_folders(folders_to_sync)

    def _sync_multiple_folders(self, folders):
        """Sync multiple folders sequentially, preserving emails"""
        self.folders_to_sync = folders.copy()
        self.current_folder_index = 0
        self.all_emails = []
        self._sync_next_folder()

    def _sync_next_folder(self):
        """Sync the next folder in the list"""
        if self.current_folder_index >= len(self.folders_to_sync):
            log.info(f"All folders synced, found {len(self.all_emails)} total emails")
            self._on_all_folders_synced(self.all_emails)
            return

        folder_name = self.folders_to_sync[self.current_folder_index]
        log.info(f"Syncing folder {self.current_folder_index + 1}/{len(self.folders_to_sync)}: {folder_name}")

        if self.account.get("use_default", True):
            host = self.default_imap.get("host", "")
            port = self.default_imap.get("port", 993)
            use_ssl = self.default_imap.get("use_ssl", True)
        else:
            host = self.account.get("host", "")
            port = self.account.get("port", 993)
            use_ssl = self.account.get("use_ssl", True)

        if not host:
            log.error("No IMAP host configured!")
            self._enable_sync_buttons()
            return

        self.worker = IMAPWorker(
            self.account["email"],
            self.account["password"],
            host,
            port,
            use_ssl,
            folder_name
        )
        self.worker.finished.connect(self._on_folder_emails_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.connection_status.connect(self._update_connection_status)
        self.worker.start()

    def _on_folder_emails_loaded(self, emails):
        """Handle emails from a single folder during multi-folder sync"""
        folder_name = self.folders_to_sync[self.current_folder_index]
        log.info(f"Loaded {len(emails)} emails from folder: {folder_name}")

        for email_data in emails:
            email_data['folder'] = folder_name
        self.all_emails.extend(emails)

        self.current_folder_index += 1
        self._sync_next_folder()

    def _on_all_folders_synced(self, all_emails):
        """Called when all folders have been synced"""
        sorted_emails = sorted(all_emails, key=lambda x: x.get('date', ''), reverse=True)[:200]

        if not hasattr(self, 'all_emails'):
            self.all_emails = []

        existing_ids = {email['id'] for email in self.all_emails}
        new_emails = [email for email in sorted_emails if email['id'] not in existing_ids]
        self.all_emails.extend(new_emails)

        log.info(f"Multi-folder sync: Added {len(new_emails)} new emails to storage, total stored: {len(self.all_emails)}")

        if new_emails:
            self._save_cached_emails()

        current_folder = self.folder_combo.currentText()
        self._filter_emails_by_folder(current_folder)

        self._enable_sync_buttons()
        self.parent_window._update_accounts_list()

    def _disable_sync_buttons(self, text):
        self._set_loading_state(True)

    def _enable_sync_buttons(self):
        self._set_loading_state(False)

    def _set_loading_state(self, loading: bool):
        """Set loading state: folder button shows hourglass, sync buttons get grayed out"""
        if loading:
            self.folder_refresh_btn.setText("")
            self.folder_refresh_btn.setEnabled(False)

            disabled_style = """
                QPushButton {
                    background-color: #3a3a3a;
                    color: #666666;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 15px;
                    font-size: 13px;
                    font-weight: bold;
                    margin-right: 3px;
                }
            """
            self.sync_folder_btn.setEnabled(False)
            self.sync_folder_btn.setStyleSheet(disabled_style)
            self.sync_mailbox_btn.setEnabled(False)
            self.sync_mailbox_btn.setStyleSheet(disabled_style)
            self.clear_cache_btn.setEnabled(False)
        else:
            self.folder_refresh_btn.setText("")
            self.folder_refresh_btn.setEnabled(True)

            sync_button_style = """
                QPushButton {
                    background-color: #824ffb;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 15px;
                    font-size: 13px;
                    font-weight: bold;
                    margin-right: 3px;
                }
                QPushButton:hover {
                    background-color: #9366ff;
                }
                QPushButton:pressed {
                    background-color: #6b3dd9;
                }
            """
            self.sync_folder_btn.setEnabled(True)
            self.sync_folder_btn.setText("Sync")
            self.sync_folder_btn.setStyleSheet(sync_button_style)
            self.sync_mailbox_btn.setEnabled(True)
            self.sync_mailbox_btn.setText("Sync All")
            self.sync_mailbox_btn.setStyleSheet(sync_button_style)
            self.clear_cache_btn.setEnabled(True)

    def _perform_sync(self, folder):
        """Execute email synchronization with progress updates"""
        if self.account.get("use_default", True):
            host = self.default_imap.get("host", "")
            port = self.default_imap.get("port", 993)
            use_ssl = self.default_imap.get("use_ssl", True)
            log.debug(f"Using default IMAP: {host}:{port}")
        else:
            host = self.account.get("host", "")
            port = self.account.get("port", 993)
            use_ssl = self.account.get("use_ssl", True)
            log.debug(f"Using account-specific IMAP: {host}:{port}")

        if not host:
            log.error("No IMAP host configured!")
            QMessageBox.critical(self, "Error", "No IMAP host configured. Please set default IMAP settings or configure account-specific settings.")
            self._enable_sync_buttons()
            return

        # Show loading cursor
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.worker = IMAPWorker(
            self.account["email"],
            self.account["password"],
            host,
            port,
            use_ssl,
            folder
        )
        self.worker.finished.connect(self._on_emails_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.connection_status.connect(self._update_connection_status)
        self.worker.finished.connect(self._restore_cursor)
        self.worker.error.connect(lambda: self._restore_cursor())
        self.worker.start()

    def _update_connection_status(self, status):
        """Update connection status: True (green), False (red), 'cache' (yellow)"""
        log.debug(f"Updating connection status for {self.account.get('email')} to: {status}")

        if status == "cache":
            self.is_connected = None
            self.viewing_cache = True
            self.sync_error = None
        elif status is True:
            self.is_connected = True
            self.viewing_cache = False
            self.sync_error = None
        else:
            self.is_connected = False
            self.viewing_cache = False

        if hasattr(self.parent_window, 'update_tab_status'):
            self.parent_window.update_tab_status(self, status)
        else:
            log.error(f"Parent window missing update_tab_status method. Type: {type(self.parent_window)}")

    def _on_emails_loaded(self, emails: List[Dict]):
        """Handle emails received from IMAP worker"""
        log.info(f"Loading {len(emails)} emails into storage")

        folder_name = self.last_sync_folder if self.last_sync_folder and self.last_sync_folder != "ALL" else "Inbox"
        for email_data in emails:
            email_data['folder'] = folder_name

        if not hasattr(self, 'all_emails'):
            self.all_emails = []

        # Create unique keys using id + subject + from for better deduplication
        existing_keys = {(email['id'], email.get('subject', ''), email.get('from', '')) for email in self.all_emails}
        new_emails = []

        for email in emails:
            email_key = (email['id'], email.get('subject', ''), email.get('from', ''))
            if email_key not in existing_keys:
                new_emails.append(email)
                existing_keys.add(email_key)
            else:
                log.debug(f"Skipping duplicate email: ID {email['id']}, Subject: {email.get('subject', 'No Subject')[:50]}")
        self.all_emails.extend(new_emails)

        log.info(f"Added {len(new_emails)} new emails to storage, total stored: {len(self.all_emails)}")

        if new_emails:
            self._save_cached_emails()

        self.viewing_cache = False
        self.sync_error = None

        current_folder = self.folder_combo.currentText()
        self._filter_emails_by_folder(current_folder)

        self._enable_sync_buttons()
        self.parent_window._update_accounts_list()
        log.info("Email storage and filtering updated successfully")

        # Check for pending email deletion after sync
        self._check_pending_delete()

    def copy_email_to_clipboard(self, item):
        """Copy email content to clipboard when clicked"""
        try:
            if item is None:
                log.warning("copy_email_to_clipboard called with None item")
                return

            row = item.row()
            log.debug(f"Copying email from row {row}, total emails: {len(self.emails)}")

            if row < len(self.emails):
                email_data = self.emails[row]
                from_addr = email_data.get('from', 'Unknown')
                subject = email_data.get('subject', 'No Subject')
                date = email_data.get('date', 'Unknown Date')
                body = email_data.get('body', 'No content available')
                email_text = f"From: {from_addr}\nSubject: {subject}\nDate: {date}\n\n{body}"
                QApplication.clipboard().setText(email_text)
                log.info(f"Copied email to clipboard: {subject[:50]}...")
            else:
                log.warning(f"Row {row} is out of range for emails list (length: {len(self.emails)})")
        except Exception as e:
            log.error(f"Error copying email to clipboard: {e}")
            import traceback
            traceback.print_exc()

    def _copy_email_address(self, event):
        """Copy the email address to clipboard when label is clicked"""
        try:
            email_address = self.account.get('email', 'Unknown')
            QApplication.clipboard().setText(email_address)
            log.info(f"Copied email address to clipboard: {email_address}")
        except Exception as e:
            log.error(f"Error copying email address to clipboard: {e}")

    def _on_email_selected(self):
        selected = self.email_table.selectedItems()
        if selected:
            row = selected[0].row()
            if row < len(self.emails):
                self.current_email = self.emails[row]
                self._update_preview_mode()

    def _set_view_mode(self, mode):
        self.current_view_mode = mode

        view_button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #824ffb;
                color: white;
            }
        """

        active_button_style = """
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: 1px solid #824ffb;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #9366ff;
                border: 1px solid #9366ff;
            }
        """

        if mode == "text":
            self.text_view_btn.setStyleSheet(active_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
            self.html_view_btn.setStyleSheet(view_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")
        else:
            self.text_view_btn.setStyleSheet(view_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
            self.html_view_btn.setStyleSheet(active_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")

        self._update_preview_mode()

    def _update_preview_mode(self):
        """Update email preview display mode"""
        if not hasattr(self, 'current_email'):
            return

        email_data = self.current_email

        if self.current_view_mode == "text":
            self.preview_html.hide()
            self.preview_text.show()
            preview = f"From: {email_data['from']}\n"
            preview += f"Subject: {email_data['subject']}\n"
            preview += f"Date: {email_data['date']}\n\n"
            preview += email_data['body_text']
            self.preview_text.setPlainText(preview)
            log.debug(f"Switched to text view for email ID {email_data['id']}")
        else:
            self.preview_text.hide()
            self.preview_html.show()

            header_html = f"""
            <div style='background-color: #f8f8f8; padding: 15px; margin-bottom: 15px; border-left: 4px solid #824ffb; font-family: Arial, sans-serif;'>
                <div style='color: #333; font-size: 14px; margin-bottom: 8px;'><strong>From:</strong> {email_data['from']}</div>
                <div style='color: #333; font-size: 14px; margin-bottom: 8px;'><strong>Subject:</strong> {email_data['subject']}</div>
                <div style='color: #333; font-size: 14px;'><strong>Date:</strong> {email_data['date']}</div>
            </div>
            """

            if email_data.get('body_html'):
                full_html = header_html + email_data['body_html']
                self.preview_html.setHtml(full_html)
            else:
                full_html = header_html + f"<pre style='color: #333; font-family: monospace; padding: 15px;'>{email_data['body_text']}</pre>"
                self.preview_html.setHtml(full_html)
            log.debug(f"Switched to HTML view for email ID {email_data['id']}")

    def _popup_email_viewer(self):
        """Create a popup window for the currently selected email"""
        if not hasattr(self, 'current_email') or not self.current_email:
            QMessageBox.information(self, "No Email Selected", "Please select an email to view in popup.")
            return

        email_data = self.current_email

        popup = QDialog(self)
        popup.setWindowTitle(f"Email: {email_data['subject']}")
        popup.setMinimumSize(800, 600)
        popup.resize(1000, 700)
        popup.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #2a2a2a; border-bottom: 2px solid #824ffb;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        header_layout.setSpacing(8)

        from_label = QLabel(f"<span style='color: #999; font-weight: bold;'>From:</span> <span style='color: #e0e0e0;'>{email_data['from']}</span>")
        from_label.setStyleSheet("font-size: 14px;")
        from_label.setWordWrap(True)

        subject_label = QLabel(f"<span style='color: #999; font-weight: bold;'>Subject:</span> <span style='color: #e0e0e0;'>{email_data['subject']}</span>")
        subject_label.setStyleSheet("font-size: 14px;")
        subject_label.setWordWrap(True)

        date_label = QLabel(f"<span style='color: #999; font-weight: bold;'>Date:</span> <span style='color: #e0e0e0;'>{email_data['date']}</span>")
        date_label.setStyleSheet("font-size: 14px;")

        header_layout.addWidget(from_label)
        header_layout.addWidget(subject_label)
        header_layout.addWidget(date_label)

        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background-color: #2a2a2a; padding: 10px;")
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(15, 5, 15, 5)

        popup_text_btn = QPushButton(" Text")
        popup_text_btn.setIcon(load_svg_icon("file-text", 16))
        popup_html_btn = QPushButton(" HTML")
        popup_html_btn.setIcon(load_svg_icon("globe", 16))

        popup_view_button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #824ffb;
            }
            QPushButton:pressed {
                background-color: #824ffb;
                color: white;
            }
        """

        popup_active_button_style = """
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: 1px solid #824ffb;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #9366ff;
                border: 1px solid #9366ff;
            }
        """

        popup_text_btn.setStyleSheet(popup_active_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
        popup_html_btn.setStyleSheet(popup_view_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")

        toolbar_layout.addWidget(popup_text_btn)
        toolbar_layout.addWidget(popup_html_btn)
        toolbar_layout.addStretch()

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        popup_text_view = QTextEdit()
        popup_text_view.setReadOnly(True)
        popup_text_view.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: none;
                padding: 15px;
                font-size: 14px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        popup_text_view.setPlainText(email_data['body_text'])

        popup_html_view = QTextBrowser()
        popup_html_view.setReadOnly(True)
        popup_html_view.setOpenExternalLinks(True)
        popup_html_view.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: none;
                padding: 15px;
            }
        """)

        if email_data.get('body_html'):
            popup_html_view.setHtml(email_data['body_html'])
        else:
            popup_html_view.setHtml(f"<pre style='color: #333; font-family: monospace; padding: 15px;'>{email_data['body_text']}</pre>")

        popup_html_view.hide()

        content_layout.addWidget(popup_text_view)
        content_layout.addWidget(popup_html_view)

        def set_popup_text_view():
            """Switch popup to text view mode"""
            popup_text_btn.setStyleSheet(popup_active_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
            popup_html_btn.setStyleSheet(popup_view_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")
            popup_html_view.hide()
            popup_text_view.show()

        def set_popup_html_view():
            """Switch popup to HTML view mode"""
            popup_text_btn.setStyleSheet(popup_view_button_style + "border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
            popup_html_btn.setStyleSheet(popup_active_button_style + "border-top-right-radius: 8px; border-bottom-right-radius: 8px;")
            popup_text_view.hide()
            popup_html_view.show()

        popup_text_btn.clicked.connect(set_popup_text_view)
        popup_html_btn.clicked.connect(set_popup_html_view)

        layout.addWidget(header_widget)
        layout.addWidget(toolbar_widget)
        layout.addWidget(content_widget)

        popup.exec()
        log.info(f"Opened popup for email: {email_data['subject']}")

    def _on_error(self, error: str):
        log.error(f"Sync failed: {error}")

        self.sync_error = error
        self.viewing_cache = False
        self.is_connected = False

        detailed_error = f"Failed to sync emails for {self.account.get('email', 'account')}:\n\n{error}\n\nPlease check your internet connection, account credentials, and server settings."
        QMessageBox.critical(self, "Email Sync Error", detailed_error)

        self._enable_sync_buttons()
        self.parent_window._update_accounts_list()


    def edit_account(self):
        """Open account dialog to edit account settings"""
        from dialogs import AccountDialog
        dialog = AccountDialog(self, self.account, self.default_imap)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_account = dialog.get_account_data()
            self.account.update(updated_account)
            self.folder_label.setText(self.account.get('email', 'No email'))
            if hasattr(self.parent_window, '_save_config'):
                self.parent_window._save_config()
            log.info(f"Updated account settings for {self.account.get('email')}")

    def filter_emails(self, search_text: str):
        """Filter displayed emails based on search text"""
        try:
            if not hasattr(self, 'all_emails') or not self.all_emails:
                log.debug("No emails to filter")
                return

            search_text = search_text.strip().lower()

            if not search_text:
                # Show all emails when search is empty - use existing logic
                if hasattr(self, '_filter_emails_by_folder'):
                    self._filter_emails_by_folder()
                else:
                    # Fallback: show all emails for current folder
                    current_folder = getattr(self, 'current_folder', 'Inbox')
                    self.emails = [email for email in self.all_emails if email.get('folder', 'INBOX') == current_folder]
                    self._populate_table()
                return

            # Filter emails by search text (matches subject, from, or body)
            filtered_emails = []
            for email in self.all_emails:
                if not isinstance(email, dict):
                    continue

                try:
                    # Search in subject, from, and body text - safe access
                    subject = str(email.get('subject', '')).lower()
                    from_addr = str(email.get('from', '')).lower()
                    body_text = str(email.get('body_text', '')).lower()

                    if search_text in subject or search_text in from_addr or search_text in body_text:
                        filtered_emails.append(email)

                except Exception as e:
                    log.debug(f"Error processing email during search: {e}")
                    continue

            # Update current emails and redisplay
            current_folder = getattr(self, 'current_folder', 'Inbox')
            self.emails = [email for email in filtered_emails if email.get('folder', 'INBOX') == current_folder]

            # Safely populate table
            if hasattr(self, 'email_table') and hasattr(self, '_populate_table'):
                self._populate_table()

            log.debug(f"Search complete: {len(self.emails)} results for '{search_text}'")

        except Exception as e:
            log.error(f"Critical error in filter_emails: {e}")
            # Emergency fallback - just clear the table rather than crash
            if hasattr(self, 'email_table'):
                self.email_table.setRowCount(0)