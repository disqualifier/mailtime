import asyncio
import logging
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from aioimaplib import IMAP4_SSL, IMAP4
import email
from email.utils import parsedate_to_datetime

log = logging.getLogger('MailClient')


class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str, str)  # latest_version, download_url, release_notes
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version: str, repo_url: str = "https://api.github.com/repos/anthropics/claude-code/releases/latest"):
        super().__init__()
        self.current_version = current_version
        self.repo_url = repo_url

    def run(self):
        """Check for updates from GitHub releases"""
        try:
            log.info(f"Checking for updates... Current version: {self.current_version}")

            # Make request to GitHub API
            req = urllib.request.Request(self.repo_url)
            req.add_header('User-Agent', f'mailtime/{self.current_version}')

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))

                    latest_version = data.get('tag_name', '').lstrip('v')
                    download_url = data.get('html_url', '')
                    release_notes = data.get('body', 'No release notes available.')

                    if self._is_newer_version(latest_version, self.current_version):
                        log.info(f"Update available: {latest_version}")
                        self.update_available.emit(latest_version, download_url, release_notes)
                    else:
                        log.info("No updates available")
                        self.no_update.emit()
                else:
                    log.warning(f"GitHub API returned status {response.status}")
                    self.error.emit(f"Failed to check for updates (HTTP {response.status})")

        except urllib.error.URLError as e:
            log.warning(f"Network error checking for updates: {e}")
            self.error.emit(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse GitHub API response: {e}")
            self.error.emit(f"Invalid response from update server")
        except Exception as e:
            log.error(f"Unexpected error checking for updates: {e}")
            self.error.emit(f"Update check failed: {str(e)}")

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Compare version strings (basic semantic versioning)"""
        try:
            def version_tuple(v):
                return tuple(map(int, v.split('.')))

            latest_tuple = version_tuple(latest)
            current_tuple = version_tuple(current)

            return latest_tuple > current_tuple
        except (ValueError, AttributeError):
            # If version parsing fails, assume no update needed
            return False


class IMAPDeleteWorker(QThread):
    deleted = pyqtSignal(bool, str)  # success, message
    error = pyqtSignal(str)

    def __init__(self, email_addr: str, password: str, host: str, port: int, use_ssl: bool, folder: str, email_id: str):
        super().__init__()
        self.email_addr = email_addr
        self.password = password
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.folder = folder
        self.email_id = email_id
        self.max_retries = 3
        self.base_timeout = 5

    def run(self):
        """Execute IMAP email deletion with retry logic"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                timeout = self.base_timeout + (attempt * 2)  # Progressive timeout: 5s, 7s, 9s
                log.info(f"IMAP delete attempt {attempt + 1}/{self.max_retries} for email ID {self.email_id} (timeout: {timeout}s)")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(asyncio.wait_for(self._delete_email(), timeout=timeout))
                loop.close()

                if success:
                    log.info(f"Email {self.email_id} deleted successfully on attempt {attempt + 1}")
                    self.deleted.emit(True, f"Email deleted successfully from server")
                else:
                    log.warning(f"Email {self.email_id} not found on server (may already be deleted)")
                    self.deleted.emit(True, f"Email not found on server (may already be deleted)")
                return

            except asyncio.TimeoutError as e:
                last_error = f"Delete timeout after {timeout} seconds"
                log.warning(f"IMAP delete attempt {attempt + 1} timed out for email {self.email_id}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(1)
                continue

            except Exception as e:
                last_error = str(e)
                log.warning(f"IMAP delete attempt {attempt + 1} failed for email {self.email_id}: {str(e)}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(1)
                continue

        # All retries failed
        log.error(f"All {self.max_retries} IMAP delete attempts failed for email {self.email_id}")
        self.error.emit(f"Delete failed after {self.max_retries} attempts. Last error: {last_error}")

    async def _delete_email(self):
        log.debug(f"Connecting to {self.host}:{self.port} for deletion")

        # Create connection with shorter timeouts
        if self.use_ssl:
            mail = IMAP4_SSL(self.host, port=self.port)
        else:
            mail = IMAP4(self.host, port=self.port)

        # Set shorter timeout for server hello
        await mail.wait_hello_from_server()
        log.debug("Server hello received for deletion")

        # Set shorter timeout for login
        await mail.login(self.email_addr, self.password)
        log.debug("Login successful for deletion")

        # Set shorter timeout for folder selection
        await mail.select(f'"{self.folder}"')
        log.debug(f"Folder '{self.folder}' selected for deletion")

        # Search for the email by ID with timeout
        search_result = await mail.search(f"UID {self.email_id}")
        if not search_result or not search_result[1] or search_result[1] == [b'']:
            log.warning(f"Email with UID {self.email_id} not found in folder {self.folder}")
            await mail.logout()
            return False

        # Mark for deletion with timeout
        await mail.store(self.email_id, '+FLAGS (\\Deleted)')
        log.debug(f"Email {self.email_id} marked for deletion")

        # Expunge to permanently delete with timeout
        await mail.expunge()
        log.debug(f"Expunge completed for email {self.email_id}")

        await mail.logout()
        return True


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
        self.max_retries = 3
        self.base_timeout = 15  # More generous timeout - let server respond naturally
        self._connection_cache = None  # Simple connection reuse

    def run(self):
        """Execute IMAP email fetching in separate thread with retry logic"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                timeout = self.base_timeout + (attempt * 5)  # Progressive timeout: 15s, 20s, 25s
                log.info(f"IMAP sync attempt {attempt + 1}/{self.max_retries} for {self.email_addr} (timeout: {timeout}s)")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                emails = loop.run_until_complete(asyncio.wait_for(self._fetch_emails(), timeout=timeout))
                loop.close()

                log.info(f"Sync completed on attempt {attempt + 1}, found {len(emails)} emails")
                self.connection_status.emit(True)
                self.finished.emit(emails)
                return

            except asyncio.TimeoutError as e:
                last_error = f"Connection timeout after {timeout} seconds"
                log.warning(f"IMAP sync attempt {attempt + 1} timed out for {self.email_addr}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(1)  # Brief pause between retries
                continue

            except Exception as e:
                last_error = str(e)
                log.warning(f"IMAP sync attempt {attempt + 1} failed for {self.email_addr}: {str(e)}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(1)  # Brief pause between retries
                continue

        # All retries failed
        log.error(f"All {self.max_retries} IMAP sync attempts failed for {self.email_addr}")
        self.connection_status.emit(False)
        self.error.emit(f"Connection failed after {self.max_retries} attempts. Last error: {last_error}")

    async def _fetch_emails(self):
        log.debug(f"Connecting to {self.host}:{self.port}")

        # Create connection with shorter internal timeouts
        if self.use_ssl:
            mail = IMAP4_SSL(self.host, port=self.port)
        else:
            mail = IMAP4(self.host, port=self.port)

        # Wait for server hello - let natural IMAP handle timing if server is responding
        await mail.wait_hello_from_server()
        log.debug("Server hello received")

        # Login - let natural IMAP handle timing if server is responding
        await mail.login(self.email_addr, self.password)
        log.debug("Login successful")

        if self.folder == "ALL":
            return await self._fetch_all_folders(mail)
        else:
            try:
                select_result = await mail.select(f'"{self.folder}"')
                if hasattr(select_result, 'result') and select_result.result != 'OK':
                    raise Exception(f"Folder selection failed: {select_result}")
                log.debug(f"Folder '{self.folder}' selected successfully")
                return await self._fetch_folder_emails(mail)
            except Exception as e:
                log.error(f"Failed to select folder '{self.folder}': {str(e)}")
                await mail.logout()
                raise Exception(f"Cannot access folder '{self.folder}': {str(e)}")


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

        email_ids = sorted(email_ids, reverse=True)[-25:]  # Reduced from 50 to 25 for faster sync
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