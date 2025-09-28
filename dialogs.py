import logging
import webbrowser
from typing import Optional, Dict
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QLabel, QFormLayout, QCheckBox, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QSplitter,
    QTextEdit, QApplication, QScrollArea
)
from PyQt6.QtCore import Qt
from utils import load_svg_icon

log = logging.getLogger('MailClient')


def get_imap_settings_for_domain(email: str) -> Dict:
    """Auto-detect IMAP settings based on email domain"""
    if not email or '@' not in email:
        return {"host": "", "port": 993, "use_ssl": True}

    domain = email.split('@')[1].lower()

    provider_settings = {
        'gmail.com': {"host": "imap.gmail.com", "port": 993, "use_ssl": True},
        'googlemail.com': {"host": "imap.gmail.com", "port": 993, "use_ssl": True},
        'outlook.com': {"host": "outlook.office365.com", "port": 993, "use_ssl": True},
        'hotmail.com': {"host": "outlook.office365.com", "port": 993, "use_ssl": True},
        'live.com': {"host": "outlook.office365.com", "port": 993, "use_ssl": True},
        'yahoo.com': {"host": "imap.mail.yahoo.com", "port": 993, "use_ssl": True},
        'icloud.com': {"host": "imap.mail.me.com", "port": 993, "use_ssl": True},
        'me.com': {"host": "imap.mail.me.com", "port": 993, "use_ssl": True},
        'aol.com': {"host": "imap.aol.com", "port": 993, "use_ssl": True},
    }

    if domain in provider_settings:
        return provider_settings[domain]

    return {"host": f"imap.{domain}", "port": 993, "use_ssl": True}


class AccountDialog(QDialog):
    def __init__(self, parent=None, account_data: Optional[Dict] = None, default_imap: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Account")
        self.setMinimumWidth(450)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #824ffb;
            }
            QLineEdit:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 1px solid #2a2a2a;
            }
            QCheckBox:disabled {
                color: #666666;
            }
            QCheckBox::indicator:disabled {
                background-color: #1a1a1a;
                border: 1px solid #2a2a2a;
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #3a3a3a;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #2a2a2a;
                border: 1px solid #824ffb;
                image: url(assets/fontawesome_icons/check.svg);
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
            QPushButton:pressed {
                background-color: #6b3dd9;
            }
        """)

        self.account_data = account_data or {}
        self.default_imap = default_imap or {}

        layout = QFormLayout()
        layout.setSpacing(12)

        self.name_input = QLineEdit(self.account_data.get("name", ""))
        self.email_input = QLineEdit(self.account_data.get("email", ""))
        self.password_input = QLineEdit(self.account_data.get("password", ""))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.use_default_checkbox = QCheckBox("Use Default IMAP Server")
        self.use_default_checkbox.setChecked(self.account_data.get("use_default", False))
        self.use_default_checkbox.stateChanged.connect(self._toggle_imap_fields)

        self.host_input = QLineEdit(self.account_data.get("host", ""))
        self.port_input = QLineEdit(str(self.account_data.get("port", 993)))
        self.ssl_checkbox = QCheckBox("Use SSL")
        self.ssl_checkbox.setChecked(self.account_data.get("use_ssl", True))

        layout.addRow("Account Name:", self.name_input)
        layout.addRow("Email:", self.email_input)
        layout.addRow("Password:", self.password_input)
        layout.addRow("", self.use_default_checkbox)
        layout.addRow("IMAP Host:", self.host_input)
        layout.addRow("IMAP Port:", self.port_input)
        layout.addRow("", self.ssl_checkbox)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
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
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout.addRow(buttons)
        self.setLayout(layout)
        self._toggle_imap_fields()

    def _toggle_imap_fields(self):
        enabled = not self.use_default_checkbox.isChecked()
        self.host_input.setEnabled(enabled)
        self.port_input.setEnabled(enabled)
        self.ssl_checkbox.setEnabled(enabled)

    def get_account_data(self) -> Dict:
        """Get account configuration data from form"""
        account_data = {
            "name": self.name_input.text(),
            "email": self.email_input.text(),
            "password": self.password_input.text(),
            "use_default": self.use_default_checkbox.isChecked(),
            "host": self.host_input.text(),
            "port": int(self.port_input.text()) if self.port_input.text().isdigit() else 993,
            "use_ssl": self.ssl_checkbox.isChecked()
        }

        if (account_data["use_default"] and
            not self.default_imap.get("host") and
            account_data["email"]):
            auto_settings = get_imap_settings_for_domain(account_data["email"])
            account_data.update(auto_settings)
            account_data["use_default"] = False
            log.info(f"Auto-detected IMAP settings for {account_data['email']}: {auto_settings}")

        return account_data


class SettingsDialog(QDialog):
    def __init__(self, parent=None, default_imap: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Default IMAP Settings")
        self.setMinimumWidth(450)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #824ffb;
            }
            QLineEdit:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 1px solid #2a2a2a;
            }
            QCheckBox:disabled {
                color: #666666;
            }
            QCheckBox::indicator:disabled {
                background-color: #1a1a1a;
                border: 1px solid #2a2a2a;
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #3a3a3a;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #2a2a2a;
                border: 1px solid #824ffb;
                image: url(assets/fontawesome_icons/check.svg);
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
            QPushButton:pressed {
                background-color: #6b3dd9;
            }
        """)

        layout = QFormLayout()
        layout.setSpacing(12)

        self.host_input = QLineEdit(default_imap.get("host", "") if default_imap else "")
        self.port_input = QLineEdit(str(default_imap.get("port", 993)) if default_imap else "993")
        self.ssl_checkbox = QCheckBox("Use SSL")
        self.ssl_checkbox.setChecked(default_imap.get("use_ssl", True) if default_imap else True)

        layout.addRow("IMAP Host:", self.host_input)
        layout.addRow("IMAP Port:", self.port_input)
        layout.addRow("", self.ssl_checkbox)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
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
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout.addRow(buttons)
        self.setLayout(layout)

    def get_settings(self) -> Dict:
        """Get current application settings"""
        return {
            "host": self.host_input.text(),
            "port": int(self.port_input.text()) if self.port_input.text().isdigit() else 993,
            "use_ssl": self.ssl_checkbox.isChecked()
        }


class EmailSearchDialog(QDialog):
    def __init__(self, parent=None, all_emails=None):
        super().__init__(parent)
        self.setWindowTitle("Email Search - mail time!")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        if parent:
            self.setWindowModality(Qt.WindowModality.NonModal)
            self.setParent(parent, Qt.WindowType.Window)
        self.all_emails = all_emails or []
        self.search_results = []
        self.current_email = None

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
        """)

        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_widget.setFixedHeight(110)
        header_widget.setStyleSheet("background-color: #2a2a2a; border-bottom: 2px solid #824ffb;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(4)

        title_label = QLabel("Search Cached Emails")
        title_label.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: bold; margin: 0px;")

        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search subjects and email bodies...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 2px solid #4a4a4a;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #824ffb;
            }
        """)

        self.search_btn = QPushButton(" Search")
        self.search_btn.setIcon(load_svg_icon("search", 16))
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #824ffb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9366ff;
            }
            QPushButton:pressed {
                background-color: #6b3dd9;
            }
        """)

        self.clear_btn = QPushButton(" Clear")
        self.clear_btn.setIcon(load_svg_icon("trash", 14))
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #777777;
            }
            QPushButton:pressed {
                background-color: #555555;
            }
        """)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.clear_btn)

        self.results_label = QLabel(f"Total cached emails: {len(self.all_emails)}")
        self.results_label.setStyleSheet("color: #999; font-size: 10px; margin: 0px;")

        header_layout.addWidget(title_label)
        header_layout.addLayout(search_layout)
        header_layout.addWidget(self.results_label)

        layout.addWidget(header_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2a2a2a;
                width: 2px;
            }
        """)

        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(10, 10, 5, 10)

        results_header = QLabel("Search Results")
        results_header.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold; margin-bottom: 10px;")

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["To", "Date", "From", "Subject"])
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.results_table.setColumnWidth(0, 180)
        self.results_table.setColumnWidth(1, 140)
        self.results_table.setColumnWidth(2, 200)

        self.results_table.setStyleSheet("""
            QTableWidget {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                gridline-color: #3a3a3a;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a3a;
            }
            QTableWidget::item:selected {
                background-color: #824ffb;
                color: white;
            }
            QTableWidget::item:hover {
                background-color: #3a3a3a;
            }
            QHeaderView::section {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                padding: 10px;
                font-weight: bold;
            }
        """)

        results_layout.addWidget(results_header)
        results_layout.addWidget(self.results_table)

        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(5, 10, 10, 10)

        preview_header = QLabel("Email Preview")
        preview_header.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold; margin-bottom: 10px;")

        self.preview_content = QTextEdit()
        self.preview_content.setReadOnly(True)
        self.preview_content.setPlaceholderText("Select an email from the search results to preview it here.")
        self.preview_content.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 15px;
                font-size: 13px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)

        preview_layout.addWidget(preview_header)
        preview_layout.addWidget(self.preview_content)

        splitter.addWidget(results_widget)
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        self._display_all_emails()

    def _setup_connections(self):
        """Setup signal connections"""
        self.search_input.returnPressed.connect(self._perform_search)
        self.search_btn.clicked.connect(self._perform_search)
        self.clear_btn.clicked.connect(self._clear_search)
        self.results_table.itemSelectionChanged.connect(self._on_email_selected)

    def _display_all_emails(self):
        """Display all emails in the results table"""
        self.search_results = self.all_emails.copy()
        self._populate_results_table()

    def _perform_search(self):
        """Perform search across email subjects and bodies"""
        query = self.search_input.text().strip()
        if not query:
            self._display_all_emails()
            return

        query_lower = query.lower()
        self.search_results = []

        for email in self.all_emails:
            subject_match = query_lower in email.get('subject', '').lower()

            body_match = query_lower in email.get('body_text', '').lower()

            from_match = query_lower in email.get('from', '').lower()

            if subject_match or body_match or from_match:
                self.search_results.append(email)

        self._populate_results_table()
        log.info(f"Search for '{query}' found {len(self.search_results)} results")

    def _clear_search(self):
        """Clear search and show all emails"""
        self.search_input.clear()
        self._display_all_emails()
        self.preview_content.clear()

    def _populate_results_table(self):
        """Populate the results table with search results"""
        self.results_table.setRowCount(len(self.search_results))

        for row, email in enumerate(self.search_results):
            to_item = QTableWidgetItem(email.get('account_email', 'Unknown'))
            to_item.setToolTip(f"Account: {email.get('account_email', 'Unknown')}")

            date_item = QTableWidgetItem(email.get('date', ''))
            date_item.setToolTip(email.get('date', ''))

            from_item = QTableWidgetItem(email.get('from', ''))
            from_item.setToolTip(email.get('from', ''))

            subject_item = QTableWidgetItem(email.get('subject', ''))
            subject_item.setToolTip(email.get('subject', ''))

            self.results_table.setItem(row, 0, to_item)
            self.results_table.setItem(row, 1, date_item)
            self.results_table.setItem(row, 2, from_item)
            self.results_table.setItem(row, 3, subject_item)

        if self.search_input.text().strip():
            self.results_label.setText(f"Found {len(self.search_results)} emails matching '{self.search_input.text()}'")
        else:
            self.results_label.setText(f"Showing all {len(self.search_results)} cached emails")

    def copy_email_to_clipboard(self, item):
        """Copy search result email to clipboard when clicked"""
        try:
            if item is None:
                log.warning("copy_email_to_clipboard called with None item in search dialog")
                return

            row = item.row()
            log.debug(f"Copying search result email from row {row}, total results: {len(self.search_results)}")

            if row < len(self.search_results):
                email_data = self.search_results[row]
                from_addr = email_data.get('from', 'Unknown')
                subject = email_data.get('subject', 'No Subject')
                date = email_data.get('date', 'Unknown Date')
                body = email_data.get('body', 'No content available')
                email_text = f"From: {from_addr}\nSubject: {subject}\nDate: {date}\n\n{body}"
                QApplication.clipboard().setText(email_text)
                log.info(f"Copied search result email to clipboard: {subject[:50]}...")
            else:
                log.warning(f"Row {row} is out of range for search results list (length: {len(self.search_results)})")
        except Exception as e:
            log.error(f"Error copying search result email to clipboard: {e}")
            import traceback
            traceback.print_exc()

    def _on_email_selected(self):
        """Handle email selection in results table"""
        selected_rows = self.results_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        if 0 <= row < len(self.search_results):
            email = self.search_results[row]
            self.current_email = email
            self._display_email_preview(email)

    def _display_email_preview(self, email):
        """Display email preview in the right panel"""
        preview_text = f"Email Details\n\n"
        preview_text += f"To: {email.get('account_email', 'Unknown')}\n"
        preview_text += f"From: {email.get('from', 'Unknown')}\n"
        preview_text += f"Subject: {email.get('subject', 'No Subject')}\n"
        preview_text += f"Date: {email.get('date', 'Unknown')}\n"
        if email.get('folder'):
            preview_text += f"Folder: {email.get('folder', 'Unknown')}\n"
        preview_text += f"\n{'='*50}\n\n"
        preview_text += email.get('body_text', 'No content available')

        self.preview_content.setPlainText(preview_text)


class UpdateDialog(QDialog):
    def __init__(self, current_version: str, latest_version: str, download_url: str, release_notes: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.setWindowTitle("Update Available")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
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
                font-size: 12px;
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
                margin: 4px;
            }
            QPushButton:hover {
                background-color: #9366ff;
            }
            QPushButton:pressed {
                background-color: #6b3dd9;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header with update icon and title
        header_layout = QHBoxLayout()

        # Update icon (using external-link icon)
        icon_label = QLabel()
        icon_label.setPixmap(load_svg_icon("external-link", 32, "#4CAF50").pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(icon_label)

        # Title and version info
        title_layout = QVBoxLayout()
        title_label = QLabel("Update Available!")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        title_layout.addWidget(title_label)

        version_label = QLabel(f"A new version of mailtime is available.\nCurrent: v{current_version}  →  Latest: v{latest_version}")
        version_label.setStyleSheet("font-size: 13px; color: #e0e0e0;")
        title_layout.addWidget(version_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Release notes section
        notes_label = QLabel("What's New:")
        notes_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0; margin-top: 10px;")
        layout.addWidget(notes_label)

        # Scrollable release notes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)

        notes_text = QTextEdit()
        notes_text.setPlainText(release_notes)
        notes_text.setReadOnly(True)
        scroll.setWidget(notes_text)
        layout.addWidget(scroll)

        # Button layout
        button_layout = QHBoxLayout()

        # Later button
        later_btn = QPushButton("Remind Me Later")
        later_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        later_btn.clicked.connect(self.reject)

        # Download button
        download_btn = QPushButton("Download Update")
        download_btn.setIcon(load_svg_icon("external-link", 16, "#ffffff"))
        download_btn.clicked.connect(self._open_download_page)
        download_btn.setDefault(True)

        button_layout.addWidget(later_btn)
        button_layout.addStretch()
        button_layout.addWidget(download_btn)
        layout.addLayout(button_layout)

    def _open_download_page(self):
        """Open the download page in default browser"""
        try:
            webbrowser.open(self.download_url)
            log.info(f"Opened download page: {self.download_url}")
            self.accept()
        except Exception as e:
            log.error(f"Failed to open download page: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Browser Error", f"Could not open download page.\n\nPlease visit:\n{self.download_url}")
            self.accept()