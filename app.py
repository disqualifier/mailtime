import sys
import asyncio
import logging
from PyQt6.QtWidgets import (
     QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
     QTabWidget, QPushButton, QTableWidget, QTableWidgetItem, QDialog,
     QLineEdit, QLabel, QFormLayout, QCheckBox, QHeaderView, QMessageBox,
     QComboBox, QTextEdit, QSplitter, QTextBrowser, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QIcon, QPalette, QColor, QPixmap, QTextCursor, QPainter
from PyQt6.QtSvg import QSvgRenderer
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import hashlib
from aioimaplib import IMAP4_SSL, IMAP4
import email
from email.utils import parsedate_to_datetime

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


def load_svg_icon(name: str, size: int = 16, color: str = "#000000") -> QIcon:
    """Load FontAwesome SVG icon and return as QIcon"""
    try:
        svg_path = Path(__file__).parent / "assets" / "fontawesome_icons" / f"{name}.svg"
        if svg_path.exists():
            with open(svg_path, 'r') as f:
                svg_content = f.read()
            if color != "#000000":
                if 'fill=' not in svg_content:
                    svg_content = svg_content.replace('<path d=', f'<path fill="{color}" d=')
                else:
                    svg_content = svg_content.replace('fill="currentColor"', f'fill="{color}"')

            renderer = QSvgRenderer()
            renderer.load(svg_content.encode())

            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()

            return QIcon(pixmap)
        else:
            log.warning(f"SVG icon not found: {svg_path}")
            return QIcon()
    except Exception as e:
        log.error(f"Error loading SVG icon {name}: {e}")
        return QIcon()


def get_status_circle(color: str) -> str:
    """Return colored circle character for status"""
    if color == "red":
        return "●"
    elif color == "yellow":
        return "●"
    elif color == "green":
        return "●"
    else:
        return "●"


class IMAPWorker(QThread):
     finished = pyqtSignal(list)
     error = pyqtSignal(str)
     connection_status = pyqtSignal(bool)

     def __init__(self, email_addr: str, password: str, host: str, port: int, use_ssl: bool, folder: str):
          super().__init__()
          self.email_addr = email_addr
          self.password = password
          self.host = host
          self.port = port
          self.use_ssl = use_ssl
          self.folder = folder

     def run(self):
          """Execute IMAP email fetching in separate thread"""
          try:
               log.info(f"Starting IMAP sync for {self.email_addr} on {self.host}:{self.port} (SSL={self.use_ssl})")
               loop = asyncio.new_event_loop()
               asyncio.set_event_loop(loop)
               emails = loop.run_until_complete(self._fetch_emails())
               loop.close()
               log.info(f"Sync completed, found {len(emails)} emails")
               self.connection_status.emit(True)
               self.finished.emit(emails)
          except Exception as e:
               log.error(f"Sync error: {str(e)}", exc_info=True)
               self.connection_status.emit(False)
               self.error.emit(str(e))

     async def _fetch_emails(self):
          log.debug(f"Connecting to {self.host}:{self.port}")
          mail = IMAP4_SSL(self.host, port=self.port) if self.use_ssl else IMAP4(self.host, port=self.port)
          await mail.wait_hello_from_server()
          log.debug("Server hello received")

          await mail.login(self.email_addr, self.password)
          log.debug("Login successful")

          if self.folder == "ALL":
               return await self._fetch_all_folders(mail)
          else:
               await mail.select(f'"{self.folder}"')
               log.debug(f"Folder '{self.folder}' selected")
               return await self._fetch_folder_emails(mail)

          is_microsoft = any(domain in self.email_addr.lower() for domain in ["@hotmail.com", "@outlook.com", "@live.com"]) or "exchange" in self.host.lower()

          email_ids = []
          if is_microsoft:
               log.debug("Using FETCH method for Microsoft/Exchange")
               result, data = await mail.fetch('1:*', '(UID)')
               if result == "OK" and data:
                    for line in data:
                         if isinstance(line, bytes) and b'FETCH (UID' in line:
                              try:
                                   decoded = line.decode()
                                   seq_num = int(decoded.split()[0])
                                   email_ids.append(seq_num)
                              except:
                                   continue
          else:
               log.debug("Using SEARCH method")
               result, data = await mail.search("ALL")
               if result == "OK" and data[0]:
                    email_ids = [int(eid) for eid in data[0].split()]

          log.debug(f"Found {len(email_ids)} email IDs")

          if not email_ids:
               log.warning("No emails found")
               await mail.logout()
               return []

          email_ids = sorted(email_ids, reverse=True)[-50:]
          log.info(f"Processing {len(email_ids)} emails")
          emails = []

          for email_id in email_ids:
               try:
                    result, data = await mail.fetch(str(email_id), "(RFC822)")
                    if result == "OK" and data and len(data) > 1:
                         raw_bytes = data[1]
                         msg = email.message_from_bytes(raw_bytes)

                         date_str = msg.get("Date", "Unknown")
                         try:
                              parsed_date = parsedate_to_datetime(date_str)
                              date_display = parsed_date.strftime("%Y-%m-%d %H:%M")
                         except:
                              date_display = date_str

                         body_text = ""
                         body_html = ""
                         if msg.is_multipart():
                              for part in msg.walk():
                                   if part.get_content_type() == "text/plain":
                                        body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                                   elif part.get_content_type() == "text/html":
                                        body_html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                         else:
                              if msg.get_content_type() == "text/plain":
                                   body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                              elif msg.get_content_type() == "text/html":
                                   body_html = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")

                         emails.append({
                              "id": str(email_id),
                              "from": msg.get("From", "Unknown"),
                              "subject": msg.get("Subject", "No Subject"),
                              "date": date_display,
                              "body_text": body_text[:500] if body_text else body_html[:500],
                              "body_html": body_html
                         })
                         log.debug(f"Processed email ID {email_id}: {msg.get('Subject', 'No Subject')}")
               except Exception as e:
                    log.error(f"Error processing email ID {email_id}: {str(e)}")
                    continue

          await mail.logout()
          log.debug("Logged out from server")
          return emails

     async def _fetch_folder_emails(self, mail):
          is_microsoft = any(domain in self.email_addr.lower() for domain in ["@hotmail.com", "@outlook.com", "@live.com"]) or "exchange" in self.host.lower()

          email_ids = []
          if is_microsoft:
               log.debug("Using FETCH method for Microsoft/Exchange")
               result, data = await mail.fetch('1:*', '(UID)')
               if result == "OK" and data:
                    for line in data:
                         if isinstance(line, bytes) and b'FETCH (UID' in line:
                              try:
                                   decoded = line.decode()
                                   seq_num = int(decoded.split()[0])
                                   email_ids.append(seq_num)
                              except:
                                   continue
          else:
               log.debug("Using SEARCH method")
               result, data = await mail.search("ALL")
               if result == "OK" and data[0]:
                    email_ids = [int(eid) for eid in data[0].split()]

          log.debug(f"Found {len(email_ids)} email IDs")

          if not email_ids:
               log.warning("No emails found in folder")
               return []

          email_ids = sorted(email_ids, reverse=True)[-50:]
          log.info(f"Processing {len(email_ids)} emails")
          emails = []

          for email_id in email_ids:
               try:
                    result, data = await mail.fetch(str(email_id), "(RFC822)")
                    if result == "OK" and data and len(data) > 1:
                         raw_bytes = data[1]
                         msg = email.message_from_bytes(raw_bytes)

                         date_str = msg.get("Date", "Unknown")
                         try:
                              parsed_date = parsedate_to_datetime(date_str)
                              date_display = parsed_date.strftime("%Y-%m-%d %H:%M")
                         except:
                              date_display = date_str

                         body_text = ""
                         body_html = ""
                         if msg.is_multipart():
                              for part in msg.walk():
                                   if part.get_content_type() == "text/plain":
                                        try:
                                             body_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                             body_text += str(part.get_payload())
                                   elif part.get_content_type() == "text/html":
                                        try:
                                             body_html += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                             body_html += str(part.get_payload())
                         else:
                              if msg.get_content_type() == "text/plain":
                                   try:
                                        body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                   except:
                                        body_text = str(msg.get_payload())
                              elif msg.get_content_type() == "text/html":
                                   try:
                                        body_html = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                   except:
                                        body_html = str(msg.get_payload())

                         emails.append({
                              "id": str(email_id),
                              "from": msg.get("From", "Unknown"),
                              "subject": msg.get("Subject", "No Subject"),
                              "date": date_display,
                              "body_text": body_text[:500] if body_text else body_html[:500],
                              "body_html": body_html
                         })
                         log.debug(f"Processed email ID {email_id}: {msg.get('Subject', 'No Subject')}")
               except Exception as e:
                    log.error(f"Error processing email ID {email_id}: {str(e)}")
                    continue
          return emails

     async def _fetch_all_folders(self, mail):
          result, folders = await mail.list('""', '*')
          all_emails = []

          if result == "OK" and folders:
               folder_names = []
               excluded_folders = ['Arquivo Morto', 'Archive', 'Outbox']

               for folder_info in folders:
                    if isinstance(folder_info, bytes):
                         folder_info = folder_info.decode()

                    log.debug(f"Processing folder line: {folder_info}")

                    try:
                         folder_name = None
                         if folder_info.count('"') >= 4:
                              parts = folder_info.split('"')
                              if len(parts) >= 4:
                                   folder_name = parts[3]
                                   log.debug(f"Quoted folder found: '{folder_name}'")
                         elif '"/"' in folder_info:
                              parts = folder_info.split('"/"')
                              if len(parts) > 1:
                                   folder_name = parts[1].strip()
                                   log.debug(f"Unquoted folder found: '{folder_name}'")

                         if (folder_name and folder_name != '/' and folder_name != '' and
                             folder_name not in excluded_folders and
                             not any(excluded in folder_name for excluded in excluded_folders)):
                              folder_names.append(folder_name)

                    except Exception as e:
                         log.debug(f"Error parsing folder info: {folder_info} - {e}")
                         continue

               log.info(f"Found {len(folder_names)} valid folders to sync: {folder_names}")

               for folder_name in folder_names[:5]:
                    try:
                         log.debug(f"Syncing folder: {folder_name}")
                         await mail.select(f'"{folder_name}"')
                         folder_emails = await self._fetch_folder_emails(mail)
                         for email_data in folder_emails:
                              email_data['folder'] = folder_name
                         all_emails.extend(folder_emails)
                    except Exception as e:
                         log.warning(f"Failed to sync folder {folder_name}: {e}")
                         continue

          all_emails = sorted(all_emails, key=lambda x: x.get('date', ''), reverse=True)[:50]
          return all_emails


class FileIOWorker(QThread):
     """Async file I/O worker to prevent UI blocking"""
     cache_loaded = pyqtSignal(dict)
     cache_saved = pyqtSignal(bool)
     cache_cleared = pyqtSignal(bool)
     config_loaded = pyqtSignal(dict)
     config_saved = pyqtSignal(bool)
     log_loaded = pyqtSignal(str)
     error = pyqtSignal(str)

     def __init__(self, operation_type, **kwargs):
          super().__init__()
          self.operation_type = operation_type
          self.kwargs = kwargs

     def run(self):
          try:
               if self.operation_type == "load_cache":
                    self._load_cache()
               elif self.operation_type == "save_cache":
                    self._save_cache()
               elif self.operation_type == "clear_cache":
                    self._clear_cache()
               elif self.operation_type == "load_config":
                    self._load_config()
               elif self.operation_type == "save_config":
                    self._save_config()
               elif self.operation_type == "load_log":
                    self._load_log()
          except Exception as e:
               self.error.emit(str(e))

     def _load_cache(self):
          """Load email cache from disk"""
          cache_file = Path(self.kwargs['cache_file_path'])
          if cache_file.exists():
               with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    self.cache_loaded.emit(cached_data)
          else:
               self.cache_loaded.emit({})

     def _save_cache(self):
          """Save email cache to disk"""
          cache_file = Path(self.kwargs['cache_file_path'])
          cache_data = self.kwargs['cache_data']
          with open(cache_file, 'w', encoding='utf-8') as f:
               json.dump(cache_data, f, indent=2)
          self.cache_saved.emit(True)

     def _clear_cache(self):
          cache_file = Path(self.kwargs['cache_file_path'])
          if cache_file.exists():
               cache_file.unlink()
          self.cache_cleared.emit(True)

     def _load_config(self):
          """Load application configuration from disk"""
          config_file = Path(self.kwargs['config_file_path'])
          if config_file.exists():
               with open(config_file, "r") as f:
                    config_data = json.load(f)
                    self.config_loaded.emit(config_data)
          else:
               default_config = {"accounts": [], "default_imap": {}}
               self.config_loaded.emit(default_config)

     def _save_config(self):
          """Save application configuration to disk"""
          config_file = Path(self.kwargs['config_file_path'])
          config_data = self.kwargs['config_data']
          with open(config_file, "w") as f:
               json.dump(config_data, f, indent=2)
          self.config_saved.emit(True)

     def _load_log(self):
          """Load log file content for display"""
          log_file = Path(self.kwargs['log_file_path'])
          if log_file.exists():
               with open(log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    if len(lines) > 1000:
                         content = '\n'.join(lines[-1000:])
                         content = "... (showing last 1000 lines) ...\n\n" + content
                    self.log_loaded.emit(content)
          else:
               self.log_loaded.emit("Log file not found.\n\nThe log file is created when the application starts. Try running some operations and refresh.")


class FolderWorker(QThread):
     folders_fetched = pyqtSignal(list)

     def __init__(self, email_addr: str, password: str, host: str, port: int, use_ssl: bool):
          super().__init__()
          self.email_addr = email_addr
          self.password = password
          self.host = host
          self.port = port
          self.use_ssl = use_ssl

     def run(self):
          try:
               loop = asyncio.new_event_loop()
               asyncio.set_event_loop(loop)
               folders = loop.run_until_complete(self._fetch_folders())
               loop.close()
               self.folders_fetched.emit(folders)
          except Exception as e:
               log.error(f"Error fetching folders: {str(e)}")
               self.folders_fetched.emit([])

     async def _fetch_folders(self):
          try:
               mail = IMAP4_SSL(self.host, port=self.port) if self.use_ssl else IMAP4(self.host, port=self.port)
               await mail.wait_hello_from_server()
               await mail.login(self.email_addr, self.password)

               result, folders = await mail.list('""', '*')
               folder_names = []

               if result == "OK" and folders:
                    for folder_info in folders:
                         if isinstance(folder_info, bytes):
                              folder_info = folder_info.decode()

                         log.debug(f"Processing folder line: {folder_info}")


                         try:
                              if folder_info.count('"') >= 4:
                                   parts = folder_info.split('"')
                                   if len(parts) >= 4:
                                        folder_name = parts[3]
                                        log.debug(f"Quoted folder found: '{folder_name}'")
                                        if folder_name and folder_name != '/':
                                             folder_names.append(folder_name)
                              elif '"/"' in folder_info:
                                   parts = folder_info.split('"/"')
                                   if len(parts) > 1:
                                        folder_name = parts[1].strip()
                                        log.debug(f"Unquoted folder found: '{folder_name}'")
                                        if folder_name and folder_name not in ['/', '""', '']:
                                             folder_names.append(folder_name)
                              else:
                                   log.debug(f"Could not parse folder line: {folder_info}")
                         except Exception as e:
                              log.debug(f"Error parsing folder info: {folder_info} - {e}")
                              continue

               await mail.logout()

               log.debug(f"Parsed folder names: {folder_names}")

               folder_mappings = {
                    'INBOX': ['INBOX', 'Inbox'],
                    'SENT': ['SENT', 'Sent', 'Sent Items', 'Sent Mail'],
                    'DRAFTS': ['DRAFTS', 'Drafts', 'Draft'],
                    'TRASH': ['TRASH', 'Trash', 'Deleted', 'Deleted Items'],
                    'SPAM': ['SPAM', 'Spam', 'Junk', 'Junk E-mail', 'Bulk Mail'],
                    'NOTES': ['NOTES', 'Notes']
               }

               excluded_folders = ['Arquivo Morto', 'Archive', 'Outbox']

               sorted_folders = []

               for standard_name, variations in folder_mappings.items():
                    for folder in folder_names:
                         if folder in variations and folder not in excluded_folders:
                              if folder not in sorted_folders:
                                   sorted_folders.append(folder)
                                   break

               for folder in folder_names:
                    if (folder not in sorted_folders and
                        folder not in excluded_folders and
                        not any(excluded in folder for excluded in excluded_folders)):
                         sorted_folders.append(folder)

               return sorted_folders

          except Exception as e:
               log.error(f"Error in _fetch_folders: {str(e)}")
               return []


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
               QCheckBox {
                    color: #e0e0e0;
                    font-size: 13px;
               }
               QCheckBox:disabled {
                    color: #666666;
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
               QCheckBox::indicator:disabled {
                    background-color: #1a1a1a;
                    border: 1px solid #2a2a2a;
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
          self.use_default_checkbox.setChecked(self.account_data.get("use_default", True))
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
          self.email_table.setColumnCount(4)
          self.email_table.setHorizontalHeaderLabels(["ID", "Date", "From", "Subject"])

          header = self.email_table.horizontalHeader()
          header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
          header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
          header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
          header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

          self.email_table.setColumnWidth(0, 50)
          self.email_table.setColumnWidth(1, 160)
          self.email_table.setColumnWidth(2, 250)
          self.email_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
          self.email_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
          self.email_table.itemSelectionChanged.connect(self._on_email_selected)
          self.email_table.setStyleSheet("""
               QTableWidget {
                    background-color: #1a1a1a;
                    color: #e0e0e0;
                    gridline-color: #2a2a2a;
                    border: none;
               }
               QTableWidget::item {
                    padding: 8px;
                    border-bottom: 1px solid #2a2a2a;
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

          log.info(f"Displayed {len(filtered_emails)} emails for folder '{folder_name}'")

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

     def edit_account(self):
          """Open account dialog to edit account settings"""
          dialog = AccountDialog(self, self.account)
          if dialog.exec() == QDialog.DialogCode.Accepted:
               updated_account = dialog.get_account_data()
               self.account.update(updated_account)
               self.folder_label.setText(self.account.get('email', 'No email'))
               if hasattr(self.parent_window, '_save_config'):
                    self.parent_window._save_config()
               log.info(f"Updated account settings for {self.account.get('email')}")

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

          self.folder_worker = FolderWorker(
               self.account["email"],
               self.account["password"],
               host,
               port,
               use_ssl
          )
          self.folder_worker.folders_fetched.connect(self._on_folders_loaded)
          self.folder_worker.finished.connect(self._reset_folder_button)
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

          self.parent_window.update_tab_status(self, status)

     def _on_emails_loaded(self, emails: List[Dict]):
          """Handle emails received from IMAP worker"""
          log.info(f"Loading {len(emails)} emails into storage")

          folder_name = self.last_sync_folder if self.last_sync_folder and self.last_sync_folder != "ALL" else "Inbox"
          for email_data in emails:
               email_data['folder'] = folder_name

          if not hasattr(self, 'all_emails'):
               self.all_emails = []

          existing_ids = {email['id'] for email in self.all_emails}
          new_emails = [email for email in emails if email['id'] not in existing_ids]
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
          preview_text += f"\n{'='*48}\n\n"
          preview_text += email.get('body_text', 'No content available')

          self.preview_content.setPlainText(preview_text)


class MailClient(QMainWindow):
     def __init__(self):
          super().__init__()
          self.setWindowTitle("mail time!")
          self.setMinimumSize(1200, 700)

          self.active_workers = []

          self._load_local_icon()


          self.setStyleSheet("""
               * {
                    outline: none;
               }
               QMainWindow {
                    background-color: #0a0a0a;
               }
               QTabWidget::pane {
                    border: none;
                    background-color: #1a1a1a;
               }
               QTabBar {
                    margin-left: 2px;
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
               QMessageBox {
                    background-color: #1a1a1a;
               }
               QMessageBox QLabel {
                    color: #e0e0e0;
               }
               QMessageBox QPushButton {
                    background-color: #824ffb;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 20px;
                    min-width: 80px;
               }
               QMessageBox QPushButton:hover {
                    background-color: #9366ff;
               }
          """)

          self.config_file = Path.home() / ".mailtime" / "config.json"
          self.config = {"default_imap": {}, "accounts": []}
          self._load_config_async()
          log.info(f"Loaded config from {self.config_file}")

          central_widget = QWidget()
          self.setCentralWidget(central_widget)
          layout = QVBoxLayout(central_widget)
          layout.setContentsMargins(0, 0, 0, 0)
          layout.setSpacing(0)

          toolbar = QWidget()
          toolbar.setFixedHeight(50)
          toolbar.setStyleSheet("background-color: #1a1a1a; border-bottom: 2px solid #824ffb;")
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

          accounts_menu_btn.setStyleSheet("""
               QPushButton {
                    background-color: #824ffb;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 10px 15px;
                    font-size: 16px;
                    font-weight: bold;
               }
               QPushButton:hover {
                    background-color: #9366ff;
               }
               QPushButton:pressed {
                    background-color: #6b3dd9;
               }
          """)

          for btn in [add_account_btn, import_accounts_btn, search_btn, settings_btn]:
               btn.setStyleSheet("""
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
                    padding: 2px;
               }
               QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                    border-radius: 4px;
               }
          """)
          self.mailbox_icon_btn.setToolTip("Click to open debug log viewer")
          self.mailbox_icon_btn.setEnabled(True)
          self.mailbox_icon_btn.clicked.connect(self._open_log_viewer)
          toolbar_layout.addWidget(self.mailbox_icon_btn)

          self.tabs = QTabWidget()
          self.tabs.setTabsClosable(True)
          self.tabs.setMovable(True)
          self.tabs.tabCloseRequested.connect(self.close_tab)

          self.tabs.tabBar().setUsesScrollButtons(True)
          self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)

          self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
          self.content_splitter.setStyleSheet("""
               QSplitter::handle {
                    background-color: #1a1a1a;
                    border: none;
                    width: 0px;
                    height: 0px;
               }
          """)

          self.accounts_panel = QWidget()
          self.accounts_panel.setMinimumWidth(0)
          self.accounts_panel.setMaximumWidth(350)
          self.accounts_panel.setStyleSheet("""
               QWidget {
                    background-color: #1a1a1a;
                    border-right: 1px solid #2a2a2a;
               }
          """)
          self.accounts_panel.hide()

          accounts_panel_layout = QVBoxLayout(self.accounts_panel)
          accounts_panel_layout.setContentsMargins(5, 5, 5, 5)
          accounts_panel_layout.setSpacing(5)

          panel_header = QLabel("All Accounts")
          panel_header.setStyleSheet("""
               QLabel {
                    color: #e0e0e0;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 5px 0;
                    border-bottom: 1px solid #2a2a2a;
                    margin-bottom: 5px;
               }
          """)
          accounts_panel_layout.addWidget(panel_header)

          self.accounts_list = QListWidget()
          self.accounts_list.setStyleSheet("""
               QListWidget {
                    background-color: #2a2a2a;
                    color: #e0e0e0;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    padding: 5px;
               }
               QListWidget::item {
                    padding: 6px 8px 6px 4px;
                    border-radius: 3px;
                    margin: 2px;
                    font-size: 11px;
               }
               QListWidget::item:hover {
                    background-color: #3a3a3a;
               }
               QListWidget::item:selected {
                    background-color: #824ffb;
               }
          """)
          self.accounts_list.itemDoubleClicked.connect(self.switch_to_account_tab)
          accounts_panel_layout.addWidget(self.accounts_list)

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
          self.clear_all_btn.clicked.connect(self.clear_all_accounts)
          accounts_panel_layout.addWidget(self.clear_all_btn)

          self.content_splitter.addWidget(self.accounts_panel)
          self.content_splitter.addWidget(self.tabs)
          self.content_splitter.setStretchFactor(0, 0)
          self.content_splitter.setStretchFactor(1, 1)
          self.content_splitter.setSizes([0, 1000])

          layout.addWidget(toolbar)
          layout.addWidget(self.content_splitter)

          self.tab_status_map = {}

          self._set_toolbar_icon()

          log.info("Mail client initialized")

     def _load_config_async(self):
          """Load config file asynchronously"""
          config_worker = FileIOWorker("load_config", config_file_path=str(self.config_file))
          config_worker.config_loaded.connect(self._on_config_loaded)
          config_worker.error.connect(self._on_config_load_error)
          config_worker.finished.connect(lambda: self._cleanup_worker(config_worker))
          self.active_workers.append(config_worker)
          config_worker.start()

     def _on_config_loaded(self, config_data):
          """Handle successful config loading"""
          self.config = config_data
          log.info(f"Config loaded asynchronously from {self.config_file}")

          for account in self.config.get("accounts", []):
               if not account.get("hidden", False):
                    self._add_mail_tab(account)
          self._update_accounts_list()

     def _on_config_load_error(self, error_msg):
          """Handle config loading errors"""
          log.error(f"Error loading config: {error_msg}")

     def _load_config(self) -> Dict:
          """Load application configuration from disk"""
          """Synchronous config loading (kept for compatibility)"""
          if self.config_file.exists():
               with open(self.config_file, "r") as f:
                    return json.load(f)
          return {"default_imap": {}, "accounts": []}

     def _save_config(self):
          """Save application configuration to disk"""
          """Save config file asynchronously"""
          config_worker = FileIOWorker("save_config",
                                     config_file_path=str(self.config_file),
                                     config_data=self.config)
          config_worker.config_saved.connect(self._on_config_saved)
          config_worker.error.connect(self._on_config_save_error)
          config_worker.finished.connect(lambda: self._cleanup_worker(config_worker))
          self.active_workers.append(config_worker)
          config_worker.start()

     def _on_config_saved(self, success):
          """Handle successful config saving"""
          if success:
               log.debug(f"Config saved asynchronously to {self.config_file}")

     def _on_config_save_error(self, error_msg):
          """Handle config saving errors"""
          log.error(f"Error saving config: {error_msg}")

     def _cleanup_worker(self, worker):
          """Remove worker from active list when finished"""
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
               if hasattr(tab, 'cache_worker') and tab.cache_worker and tab.cache_worker.isRunning():
                    tab.cache_worker.quit()
                    if not tab.cache_worker.wait(1000):
                         tab.cache_worker.terminate()
               if hasattr(tab, 'save_worker') and tab.save_worker and tab.save_worker.isRunning():
                    tab.save_worker.quit()
                    if not tab.save_worker.wait(1000):
                         tab.save_worker.terminate()
               if hasattr(tab, 'clear_worker') and tab.clear_worker and tab.clear_worker.isRunning():
                    tab.clear_worker.quit()
                    if not tab.clear_worker.wait(1000):
                         tab.clear_worker.terminate()
               if hasattr(tab, 'folder_worker') and tab.folder_worker and tab.folder_worker.isRunning():
                    tab.folder_worker.quit()
                    if not tab.folder_worker.wait(1000):
                         tab.folder_worker.terminate()

          log.info("Thread cleanup completed")
          event.accept()

     def add_account(self):
          """Add new email account to configuration"""
          log.info("Opening add account dialog")
          dialog = AccountDialog(self, None, self.config.get("default_imap", {}))
          if dialog.exec() == QDialog.DialogCode.Accepted:
               account = dialog.get_account_data()
               new_email = account['email'].lower()

               existing_emails = [acc.get('email', '').lower() for acc in self.config.get("accounts", [])]
               if new_email in existing_emails:
                    log.info(f"Account {account['email']} already exists, ignoring duplicate")
                    return

               self.config["accounts"].append(account)
               self._save_config()
               self._add_mail_tab(account)
               self._update_accounts_list()
               log.info(f"Added account: {account.get('email')}")

     def import_accounts(self):
          """Import accounts from selected file"""
          from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QPushButton
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

          instructions = QLabel("Import Formats:\n• email:password\n• email:password:name\n• email:password:name:host:port\n\nFormats without host:port use default settings.\nOne account per line:")
          layout.addWidget(instructions)

          text_edit = QTextEdit()
          text_edit.setPlaceholderText("user@example.com:password123\nuser2@gmail.com:password456:Work Gmail\nuser3@company.com:password789:Company:imap.company.com:993")
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

                         new_email = account['email'].lower()
                    existing_emails = [acc.get('email', '').lower() for acc in self.config.get("accounts", [])]
                    if new_email in existing_emails:
                         log.info(f"Account {account['email']} already exists, ignoring duplicate")
                         continue

                    self.config["accounts"].append(account)
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
               item = QListWidgetItem(f"{status} {account_name}")
               item.setData(Qt.ItemDataRole.UserRole, i)
               self.accounts_list.addItem(item)

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

     def clear_all_accounts(self):
          """Remove all configured accounts after confirmation"""
          reply = QMessageBox.question(self, "Clear All Accounts",
                                     "Are you sure you want to remove all accounts? This action cannot be undone.\n\nThis will also clear all cached emails.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
          if reply == QMessageBox.StandardButton.Yes:
               for i in range(self.tabs.count()):
                    tab_widget = self.tabs.widget(i)
                    if hasattr(tab_widget, '_clear_cached_emails'):
                         tab_widget._clear_cached_emails()

               self._clear_all_cache_files()

               while self.tabs.count() > 0:
                    tab_widget = self.tabs.widget(0)
                    if tab_widget in self.tab_status_map:
                         del self.tab_status_map[tab_widget]
                    self.tabs.removeTab(0)

               self.config["accounts"] = []
               self._save_config()
               self._update_accounts_list()
               log.info("All accounts and cached emails cleared")

     def _clear_all_cache_files(self):
          """Clear all cache files in the cache directory"""
          try:
               cache_dir = Path.home() / ".mailtime"
               if cache_dir.exists():
                    for cache_file in cache_dir.glob("*.json"):
                         cache_file.unlink()
                         log.debug(f"Deleted cache file: {cache_file}")
                    log.info(f"Cleared all cache files from {cache_dir}")
          except Exception as e:
               log.error(f"Error clearing cache files: {e}")

     def _load_local_icon(self):
          """Load application icon from resources"""
          try:
               icon_path = "./assets/icon.png"
               if Path(icon_path).exists():
                    pixmap = QPixmap(icon_path)
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

     def _play_startup_sound(self):
          try:
               sound_path = Path("./assets/mail.mp3")
               if sound_path.exists():
                    try:
                         import pygame
                         pygame.mixer.init()
                         pygame.mixer.music.load(str(sound_path))
                         pygame.mixer.music.play()
                         log.info("Startup sound played with pygame")
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
                                             log.info(f"Startup sound played with {player}")
                                             break
                                        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                                             continue
                              elif system == "windows":
                                   import winsound
                                   winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
                                   log.info("Startup sound played with winsound")
                              elif system == "darwin":
                                   subprocess.run(["afplay", str(sound_path)], check=True)
                                   log.info("Startup sound played with afplay")
                         except Exception as fallback_error:
                              log.warning(f"Could not play sound with any method: {fallback_error}")
               else:
                    log.warning("mail.mp3 not found in project directory")
          except Exception as e:
               log.error(f"Error playing startup sound: {e}")

     def _set_toolbar_icon(self):
          if hasattr(self, '_icon_pixmap') and hasattr(self, 'mailbox_icon_btn'):
               try:
                    scaled_pixmap = self._icon_pixmap.scaled(32, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.mailbox_icon_btn.setIcon(QIcon(scaled_pixmap))
                    self.mailbox_icon_btn.setIconSize(scaled_pixmap.size())
                    log.info("Toolbar icon set successfully")
               except Exception as e:
                    log.error(f"Error setting toolbar icon: {e}")

     def _add_mail_tab(self, account: Dict):
          tab = MailTab(account, self.config.get("default_imap", {}), self)
          tab_name = account.get("name", account.get("email", "Unknown"))
          index = self.tabs.addTab(tab, f"🔴 {tab_name}")
          self.tab_status_map[tab] = False
          log.debug(f"Added tab for {account.get('email')}")

          QTimer.singleShot(100, lambda: self._update_accounts_list())

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

     def update_tab_status(self, tab: MailTab, status):
          """Update tab status: True (green), False (red), 'cache' (yellow)"""
          index = self.tabs.indexOf(tab)
          if index >= 0:
               account = self.config["accounts"][index]
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

     def close_tab(self, index: int):
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
          self._play_startup_sound()
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
                    font-size: 13px;
                    font-weight: bold;
                    margin-left: 10px;
               }
               QPushButton:hover {
                    background-color: #9366ff;
               }
               QPushButton:pressed {
                    background-color: #6b3dd9;
               }
          """)

          header_layout.addWidget(title_label)
          header_layout.addStretch()
          header_layout.addWidget(refresh_btn)

          log_text = QTextEdit()
          log_text.setReadOnly(True)
          log_text.setStyleSheet("""
               QTextEdit {
                    background-color: #0a0a0a;
                    color: #e0e0e0;
                    border: none;
                    padding: 15px;
                    font-size: 12px;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
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

     def open_search(self):
          """Open the email search dialog"""
          log.info("Opening search dialog")

          all_cached_emails = []
          for i in range(self.tabs.count()):
               tab = self.tabs.widget(i)
               if hasattr(tab, 'all_emails') and tab.all_emails:
                    account_email = tab.account.get('email', 'Unknown')
                    for email in tab.all_emails:
                         email_with_account = email.copy()
                         email_with_account['account_email'] = account_email
                         all_cached_emails.append(email_with_account)

          if not all_cached_emails:
               QMessageBox.information(self, "No Cached Emails",
                                     "No cached emails found to search.\n\nSync some emails first to use the search feature.")
               return

          log.info(f"Found {len(all_cached_emails)} cached emails across all accounts")

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


if __name__ == "__main__":
     log.info("Starting IMAP Mail Client")
     app = QApplication(sys.argv)
     window = MailClient()
     window.show()
     sys.exit(app.exec())