Free Fast Download Manager (ffdm cross-platform)

A powerful, multi-threaded download manager with both Tkinter and PySide6 (Qt) GUI interfaces, featuring advanced download capabilities, database persistence, and system tray integration.
Features
Core Functionality

    Multi-threaded Downloads: Download files using multiple threads for faster speeds

    Resume Capability: Continue interrupted downloads from where they left off

    Database Storage: All downloads and settings are stored in SQLite database

    Cross-platform: Works on Windows, macOS, and Linux

    Multiple GUI Options: Choose between Tkinter or Qt interface

Advanced Features

    Smart Chunk Sizing: Automatic or manual chunk size configuration

    Speed Limiting: Configurable connection limits and timeouts

    Proxy Support: HTTP proxy configuration

    Theming: Light and dark theme support

    Multi-language: Support for English, Spanish, French, and German

    System Tray Integration: Minimize to system tray and background operation

    Download History: Complete history of all downloads with statistics

User Interface

    Real-time Progress: Live progress bars and speed indicators

    Batch Operations: Start, pause, stop, or remove multiple downloads simultaneously

    Detailed Information: Comprehensive download details and statistics

    Keyboard Shortcuts: Full keyboard navigation and control

Installation
Prerequisites

    Python 3.7 or higher

    pip (Python package manager)

Dependencies

Install the required dependencies:
```
python -m pip install requests pystray pillow pyside6
```
Installation Steps

    Clone or download the project files

    Ensure both fdm.py and fdm_qt.py are in the same directory

    (Optional) Add an fdm.png icon file to the directory for proper tray icon display

Usage
Starting the Application
Tkinter Version (Default)

```
python fdm.py
```
Qt Version (PySide6)

```
python fdm_qt.py
```

Command Line Arguments

Both versions support these command line arguments:

    --silent: Start the application minimized to system tray

    --debug: Enable debug logging for troubleshooting

Example:

```
python fdm.py --silent
python fdm_qt.py --debug
```
Adding Downloads

    Click the "Add Download" button or press Ctrl+N/F2

    Enter the URL of the file you want to download

    The application will automatically determine the filename or allow you to specify one

Managing Downloads

    Start: Select downloads and click "Start" or press Ctrl+S

    Pause: Select downloads and click "Pause" or press Ctrl+P

    Remove: Select downloads and click "Remove" or press Delete

    Multi-select: Use Ctrl+Click or Shift+Click to select multiple downloads

System Tray Operation

    The application minimizes to system tray when closed

    Double-click the tray icon to show/hide the application

    Right-click the tray icon for quick access to show/hide/exit functions

Configuration
Settings Dialog

Access settings through the "Settings" button or Ctrl+Comma:

    Save Path: Directory where downloads are saved

    Max Connections: Maximum simultaneous connections (1-16)

    Chunk Size: Download chunk size (AUTO or specific sizes from 1KB to 128KB)

    Timeout: Connection timeout in seconds (5-120)

    Proxy: Optional HTTP proxy server

    Theme: Light or dark interface theme

    Language: Application language (en, es, fr, de)

    Threads per Download: Number of threads to use for each download (1-16)

Keyboard Shortcuts

    F1: Show help

    F2: Add new download

    F5: Refresh download list

    Ctrl+N: Add new download

    Ctrl+S: Start selected downloads

    Ctrl+P: Pause selected downloads

    Delete: Remove selected downloads

    Ctrl+,: Open settings

Database

The application uses an SQLite database (downloads.db) to store:

    Download history and status

    Application settings and configuration

    Download statistics and speed metrics

    Session information for resuming downloads

Troubleshooting
Common Issues

    "Cannot start a transaction within a transaction" error

        This has been fixed in the current version with proper database locking

    Tray icon not showing

        The application includes fallback icon creation

        Add an fdm.png file to the application directory for best results

    Download errors

        Check your internet connection

        Verify the URL is correct and accessible

        Try reducing the number of threads or connections

    Slow downloads

        Increase the chunk size in settings

        Add more threads per download

        Check if the server supports range requests

Logs

The application creates a fdm.log file with detailed information about operations and errors. Enable debug mode with --debug for more verbose logging.
Technical Details
Architecture

The application follows a Model-View-Controller pattern:

    Model: DownloadManager and DownloadDB classes handle download logic and data persistence

    View: GUI classes (ModernDownloader and FDMQtMain) handle user interface

    Controller: Mediates between model and view, handling user actions

Threading Model

    Each download uses separate threads for concurrent operations

    Database operations use locking to prevent conflicts

    UI updates are handled through thread-safe message queues

Network Features

    HTTP range requests for resumable downloads

    Automatic retry on network errors

    Chunked encoding support

    Redirect handling

    User-Agent spoofing for compatibility

Contributing

We welcome contributions to the Free Download Manager project:

    Fork the repository

    Create a feature branch

    Make your changes

    Add tests if applicable

    Submit a pull request

Areas for Improvement

    Additional protocol support (FTP, BitTorrent)

    Browser integration extensions

    Enhanced scheduling features

    Cloud storage integration

    Mobile applications

License

This project is open source and available under the MIT License.
Credits

deepseek-coder - 0xbytecode 🦅 - me 
Acknowledgments

    Thanks to the requests library for simplified HTTP operations

    Appreciation to the SQLite team for a robust embedded database

    Gratitude to the Python community for excellent GUI frameworks

Support

For support, bug reports, or feature requests:

    Check the troubleshooting section above

    Review the application logs

    Open an issue on the project repository

Note: This application is designed for legitimate downloading purposes. Please respect copyright laws and terms of service when downloading content.
