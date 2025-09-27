# mail time!

<div align="center">
  <img src="assets/icon.png" alt="mail time!" width="128" height="128">
</div>

A PyQt6-based IMAP email client designed for rapid usage of emails over IMAP, including temp services like hotmail007.

## Features

- **Multi-account support** - Manage multiple email accounts in a tabbed interface
- **IMAP protocol** - Works with any IMAP-compatible email service
- **Temp email services** - Perfect for temporary services like hotmail007
- **Dark theme** - Modern dark UI for comfortable viewing
- **Email caching** - Offline access to previously fetched emails
- **Account management** - Easy account setup and configuration
- **Search functionality** - Quickly find emails across accounts
- **Status indicators** - Real-time connection status for each account

## Installation

### Requirements

- Python 3.10+
- PyQt6
- aioimaplib

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Application

**For Windows/WSL (GUI):**
```bash
./run-windows.sh
```

**For Linux/Mac:**
```bash
./run.sh
```

**Alternative:**
```bash
python3 app.py
```

### Build Executable

**For Windows builds:**
```bash
./run-windows.sh build
```

**For Linux/Mac builds:**
```bash
./run.sh build
```

**Windows batch file:**
```cmd
run.bat build
```

The built executable will be in the `dist/` directory (`mailtime.exe` for Windows).

## Usage

1. **Add Account**: Click the "+" button to add a new IMAP email account
2. **Configure IMAP**: Set up your IMAP server settings (host, port, SSL)
3. **View Emails**: Switch between accounts using the tabs
4. **Search**: Use the search functionality to find specific emails
5. **Manage Accounts**: Hide/show accounts using the hamburger menu

## Supported Services

- Gmail, Outlook, Yahoo
- Corporate email servers
- Temporary email services (hotmail007, etc.)
- Any IMAP-compatible email provider

## Configuration

Configuration is stored in `~/.mailtime/config.json` and includes:
- Account credentials
- IMAP server settings
- Application preferences

Email cache is stored in `~/.mailtime/[email_hash]_emails.json` for offline access.

## Project Structure

```
mailtime/
├── assets/                  # Application assets
│   ├── fontawesome_icons/   # UI icons
│   ├── icon.png            # Application icon
│   ├── icon.ico            # Windows icon
│   └── mail.mp3            # Notification sound
├── app.py                  # Main application (standalone)
├── mailtime_app.py         # Main application (modular)
├── widgets.py              # UI components
├── dialogs.py              # Dialog windows
├── utils.py                # Utility functions
├── workers.py              # Background workers
├── run.sh                  # Linux/Mac runner
├── run.bat                 # Windows batch runner
├── run-windows.sh          # WSL Windows GUI runner
└── requirements.txt        # Dependencies
```

## License

This project is for educational and research purposes.