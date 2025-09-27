"""
mailtime - PyQt6-based IMAP email client application

A modular email client with support for multiple accounts, caching, and search functionality.
"""

from .main import MailClient
from .widgets import MailTab
from .dialogs import AccountDialog, SettingsDialog, EmailSearchDialog
from .workers import IMAPWorker, FileIOWorker, FolderWorker
from .utils import load_svg_icon, get_status_circle

__version__ = "1.0.0"
__author__ = "mailtime"

__all__ = [
    "MailClient",
    "MailTab",
    "AccountDialog",
    "SettingsDialog",
    "EmailSearchDialog",
    "IMAPWorker",
    "FileIOWorker",
    "FolderWorker",
    "load_svg_icon",
    "get_status_circle"
]