"""
fdm_qt.py - PySide6 GUI wrapper for existing DownloadManager in fdm.py
"""

import sys, os, time, threading, math, queue
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QToolBar, QLabel, QSplitter,
    QListWidget, QListWidgetItem, QStatusBar, QFileDialog, QMessageBox, QComboBox,
    QInputDialog, QProgressBar, QHBoxLayout, QDialog, QPushButton, QSpinBox,
    QDialogButtonBox, QFormLayout, QLineEdit, QGroupBox, QMenu, QSystemTrayIcon
)
from PySide6.QtGui import QIcon, QFont, QAction, QColor, QBrush, QKeySequence
from PySide6.QtCore import Qt, QTimer, QSize, QObject, Signal
# Import the existing backend (DownloadManager) and translator
try:
    from fdm import DownloadManager, DownloadDB
except Exception as e:
    print("Failed to import DownloadManager from fdm.py:", e)
    DownloadManager = None
    DownloadDB = None

try:
    from translator import Translator
except:
    # Fallback translator if not available
    class Translator:
        def __init__(self, lang="en", locales_dir=None):
            self.lang = lang
            self.translations = {}
            
        def t(self, key):
            # Simple fallback translations
            translations = {
                "app_title": "FDM - Free Download Manager",
                "btn_add": "Add Download",
                "btn_start": "Start",
                "btn_pause": "Pause",
                "btn_remove": "Remove",
                "btn_settings": "Settings",
                "menu_file": "Filename",
                "label_size": "Size",
                "label_progress": "Progress",
                "label_speed": "Speed",
                "label_status": "Status",
                "add_url_title": "Add Download",
                "add_url_prompt": "Enter URL:",
                "success": "Success",
                "download_added": "Download added successfully",
                "error": "Error",
                "download_failed": "Failed to add download",
                "start_failed": "Failed to start download",
                "pause_failed": "Failed to pause download",
                "confirm_remove": "Confirm Removal",
                "confirm_remove_text": "Are you sure you want to remove this download?",
                "remove_failed": "Failed to remove download",
                "download_complete": "Download Complete",
                "download_complete_text": "Download completed successfully",
                "download_error_text": "Download error",
                "total_downloads": "Total Downloads",
                "total_bytes": "Total Bytes",
                "avg_speed": "Average Speed"
            }
            return translations.get(key, key)
            
        def available_languages(self):
            return ["en"]
            
        def load_language(self, lang_code):
            self.lang = lang_code

# Create a thread-safe message queue for UI updates
class UIMessageQueue(QObject):
    message_signal = Signal(str, str, str)  # url, type, message
    
    def __init__(self):
        super().__init__()
        self.queue = queue.Queue()
        
    def put_message(self, url, msg_type, message):
        self.queue.put((url, msg_type, message))
        self.message_signal.emit(url, msg_type, message)
        
    def get_message(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

class SettingsDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Settings")
        self.resize(400, 300)
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QFormLayout(self)
        
        # Save path
        self.save_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_save_path)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.save_path_edit)
        path_layout.addWidget(self.browse_btn)
        
        layout.addRow("Save Path:", path_layout)
        
        # Max connections
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 16)
        layout.addRow("Max Connections:", self.connections_spin)
        
        # Chunk size
        self.chunk_combo = QComboBox()
        self.chunk_combo.addItems(["AUTO", "1024", "2048", "4096", "8192", "16384", "32768", "65536", "131072"])
        layout.addRow("Chunk Size:", self.chunk_combo)
        
        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        layout.addRow("Timeout (seconds):", self.timeout_spin)
        
        # Proxy
        self.proxy_edit = QLineEdit()
        layout.addRow("Proxy (optional):", self.proxy_edit)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        layout.addRow("Theme:", self.theme_combo)
        
        # Language
        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "es", "fr", "de"])
        layout.addRow("Language:", self.language_combo)
        
        # Threads per download
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        layout.addRow("Threads per Download:", self.threads_spin)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        layout.addRow(self.buttons)
        
    def browse_save_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.save_path_edit.text())
        if path:
            self.save_path_edit.setText(path)
            
    def load_settings(self):
        if self.manager:
            config = self.manager.config
            self.save_path_edit.setText(config.get("save_path", ""))
            self.connections_spin.setValue(config.get("max_connections", 8))
            
            chunk_size = config.get("chunk_size", "AUTO")
            if chunk_size == "AUTO":
                self.chunk_combo.setCurrentText("AUTO")
            else:
                self.chunk_combo.setCurrentText(str(chunk_size))
                    
            self.timeout_spin.setValue(config.get("timeout", 30))
            self.proxy_edit.setText(config.get("proxy", ""))
            self.theme_combo.setCurrentText(config.get("theme", "light"))
            self.language_combo.setCurrentText(config.get("language", "en"))
            self.threads_spin.setValue(config.get("threads_per_download", 4))

    def save_settings(self):
        if self.manager:
            self.manager.config["save_path"] = self.save_path_edit.text()
            self.manager.config["max_connections"] = self.connections_spin.value()
            
            chunk_val = self.chunk_combo.currentText()
            if chunk_val == "AUTO":
                self.manager.config["chunk_size"] = "AUTO"
            else:
                self.manager.config["chunk_size"] = int(chunk_val)
                
            self.manager.config["timeout"] = self.timeout_spin.value()
            self.manager.config["proxy"] = self.proxy_edit.text() or None
            self.manager.config["theme"] = self.theme_combo.currentText()
            self.manager.config["language"] = self.language_combo.currentText()
            self.manager.config["threads_per_download"] = self.threads_spin.value()
            
            self.manager.save_config()
            
    def accept(self):
        self.save_settings()
        super().accept()

class FDMQtMain(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize backend manager
        self.manager = None
        if DownloadManager:
            try:
                self.manager = DownloadManager()
            except Exception as e:
                print("Error initializing DownloadManager:", e)
                self.manager = None

        # Translator (use manager language if available)
        lang = "en"
        if self.manager and hasattr(self.manager, "config"):
            lang = self.manager.config.get("language", "en")
        self.tr = Translator(lang, locales_dir=os.path.join(os.path.dirname(__file__), "locales"))

        self.setWindowTitle(self.tr.t("app_title"))
        self.resize(1100, 700)

        # Store tree items for efficient updates
        self.tree_items = {}

        # Message queue for thread-safe UI updates
        self.ui_message_queue = UIMessageQueue()
        self.ui_message_queue.message_signal.connect(self.handle_ui_message)

        # Apply theme
        self.apply_theme()

        self._setup_ui()
        
        # Setup system tray icon
        self.setup_tray_icon()
        
        # Start timer to refresh UI from manager state
        self.timer = QTimer(self)
        self.timer.setInterval(500)  # Update more frequently
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start()

        # Load existing downloads
        self.load_existing_downloads()

    def apply_theme(self):
        """Apply the theme from the manager's config"""
        if not self.manager:
            return
            
        theme = self.manager.config.get("theme", "light")
        
        # Simple theme application - you can expand this with proper stylesheets
        if theme == "dark":
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2d2d30;
                    color: #ffffff;
                }
                QTreeWidget {
                    background-color: #3e3e42;
                    color: #ffffff;
                    alternate-background-color: #2d2d30;
                    selection-background-color: #505050;
                    selection-color: #ffffff;
                }
                QHeaderView::section {
                    background-color: #3e3e42;
                    color: #ffffff;
                    padding: 4px;
                    border: 1px solid #6e6e6e;
                }
                QToolBar {
                    background-color: #3e3e42;
                    border: none;
                }
                QStatusBar {
                    background-color: #3e3e42;
                    color: #ffffff;
                }
                QMenuBar {
                    background-color: #3e3e42;
                    color: #ffffff;
                }
                QMenuBar::item:selected {
                    background-color: #505050;
                }
                QMenu {
                    background-color: #3e3e42;
                    color: #ffffff;
                    border: 1px solid #6e6e6e;
                }
                QMenu::item:selected {
                    background-color: #505050;
                }
                QLineEdit {
                    background-color: #3e3e42;
                    color: #ffffff;
                    border: 1px solid #6e6e6e;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #505050;
                    color: #ffffff;
                    border: 1px solid #6e6e6e;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #606060;
                }
                QPushButton:pressed {
                    background-color: #404040;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QTreeWidget {
                    background-color: #ffffff;
                    color: #000000;
                    alternate-background-color: #f0f0f0;
                    selection-background-color: #d0d0d0;
                    selection-color: #000000;
                }
                QHeaderView::section {
                    background-color: #e0e0e0;
                    color: #000000;
                    padding: 4px;
                    border: 1px solid #d0d0d0;
                }
                QToolBar {
                    background-color: #e0e0e0;
                    border: none;
                }
                QStatusBar {
                    background-color: #e0e0e0;
                    color: #000000;
                }
                QTreeWidget::item:selected {
                    background-color: #d0d0d0;
                    color: #000000;
                }
                QTreeWidget::item:hover {
                    background-color: #e0e0e0;
                }
            """)

    def _setup_ui(self):
        # Toolbar
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        add_action = QAction(QIcon(), "+" + " " + self.tr.t("btn_add"), self)
        add_action.triggered.connect(self.on_add)
        add_action.setShortcut(QKeySequence("Ctrl+N"))
        
        start_action = QAction(QIcon(), self.tr.t("btn_start"), self)
        start_action.triggered.connect(self.on_start)
        start_action.setShortcut(QKeySequence("Ctrl+S"))
        
        pause_action = QAction(QIcon(), self.tr.t("btn_pause"), self)
        pause_action.triggered.connect(self.on_pause)
        pause_action.setShortcut(QKeySequence("Ctrl+P"))
        
        remove_action = QAction(QIcon(), self.tr.t("btn_remove"), self)
        remove_action.triggered.connect(self.on_remove)
        remove_action.setShortcut(QKeySequence("Delete"))
        
        settings_action = QAction(QIcon(), self.tr.t("btn_settings"), self)
        settings_action.triggered.connect(self.on_settings)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))

        toolbar.addAction(add_action)
        toolbar.addAction(start_action)
        toolbar.addAction(pause_action)
        toolbar.addAction(remove_action)
        toolbar.addAction(settings_action)

        # Download list (columns: filename, size, progress, speed, status)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            self.tr.t("menu_file"), 
            self.tr.t("label_size"), 
            self.tr.t("label_progress"), 
            self.tr.t("label_speed"), 
            self.tr.t("label_status")
        ])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 150)
        self.tree.setColumnWidth(3, 100)
        self.tree.setColumnWidth(4, 100)
        
        # Enable multi-selection with Ctrl and Shift
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        
        # Enable keyboard navigation
        self.tree.setAlternatingRowColors(True)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.global_label = QLabel("")
        self.status.addPermanentWidget(self.global_label)

        # Add credit to status bar
        self.credit_label = QLabel("0xbytecode 🦅")
        self.status.addPermanentWidget(self.credit_label)

        # Language selector in toolbar
        self.lang_combo = QComboBox()
        langs = self.tr.available_languages()
        for l in langs:
            self.lang_combo.addItem(l)
        try:
            self.lang_combo.setCurrentText(self.tr.lang)
        except Exception:
            pass
        self.lang_combo.currentTextChanged.connect(self.on_language_changed)
        toolbar.addWidget(QLabel("Language:"))
        toolbar.addWidget(self.lang_combo)

        # Layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tree)
        self.setCentralWidget(central)
        
        # Add keyboard shortcuts
        self.setup_shortcuts()

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F1 for help
        help_action = QAction(self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.show_help)
        self.addAction(help_action)
        
        # F2 for adding download
        add_action = QAction(self)
        add_action.setShortcut(QKeySequence("F2"))
        add_action.triggered.connect(self.on_add)
        self.addAction(add_action)
        
        # F5 for refresh
        refresh_action = QAction(self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.refresh_ui)
        self.addAction(refresh_action)

    def show_help(self):
        """Show help dialog"""
        help_text = """
        FDM - Free Download Manager Help
        
        Shortcuts:
        - F1: Show this help
        - F2: Add new download
        - F5: Refresh download list
        - Ctrl+N: Add new download
        - Ctrl+S: Start selected downloads
        - Ctrl+P: Pause selected downloads
        - Delete: Remove selected downloads
        - Ctrl+,: Open settings
        
        Multi-select:
        - Click: Select single item
        - Ctrl+Click: Toggle selection of item
        - Shift+Click: Select range of items
        - Ctrl+A: Select all items
        """
        QMessageBox.information(self, "Help", help_text)

    def setup_tray_icon(self):
        """Setup system tray icon with better error handling"""
        try:
            # Try multiple possible icon paths
            icon_paths = [
                "fdm.png",
                os.path.join(os.path.dirname(__file__), "fdm.png"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "fdm.png"),
                "icons/fdm.png",
            ]
            
            tray_icon = None
            for path in icon_paths:
                if os.path.exists(path):
                    tray_icon = QIcon(path)
                    break
            
            # If no icon file found, use a fallback
            if tray_icon is None or tray_icon.isNull():
                # Create a simple icon programmatically
                from PySide6.QtGui import QPixmap, QPainter, QColor
                pixmap = QPixmap(32, 32)
                pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
                painter = QPainter(pixmap)
                painter.setBrush(QColor(0, 120, 215))  # Blue color
                painter.drawEllipse(4, 4, 24, 24)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(8, 22, "FDM")
                painter.end()
                tray_icon = QIcon(pixmap)
                
        except Exception as e:
            print("Error creating tray icon:", e)
            # Use system default icon
            tray_icon = QIcon.fromTheme("download", QIcon.fromTheme("network-transmit-receive"))
        
        # Create tray icon
        self.tray_icon = QSystemTrayIcon(tray_icon, self)
        self.tray_icon.setToolTip("FDM Download Manager")
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show)
        
        hide_action = tray_menu.addAction("Hide")
        hide_action.triggered.connect(self.hide)
        
        tray_menu.addSeparator()
        
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        
        # Show the tray icon
        self.tray_icon.show()
        
    def on_tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def closeEvent(self, event):
        """Handle application close event"""
        # Hide to tray instead of closing
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def load_existing_downloads(self):
        """Load existing downloads from the database"""
        if not self.manager:
            return
            
        # Load active downloads from database
        try:
            # Check if the manager has the load_downloads_from_db method
            if hasattr(self.manager, 'load_downloads_from_db'):
                self.manager.load_downloads_from_db()
            else:
                # Fallback: load from database directly
                db = DownloadDB()
                active_downloads = db.get_active_downloads()
                
                for download in active_downloads:
                    db_id, url, filename, total_size, downloaded, status = download
                    
                    # Recreate the download object
                    self.manager.downloads[url] = {
                        "file_path": os.path.join(self.manager.config["save_path"], filename),
                        "size": total_size,
                        "downloaded": downloaded,
                        "speed": 0,
                        "status": status,
                        "start_time": time.time(),
                        "db_id": db_id,
                        "progress_callback": None,
                        "complete_callback": None,
                        "error_callback": None
                    }
        except Exception as e:
            print("Error loading downloads from database:", e)
        
        # Add them to the tree
        for url, download in self.manager.downloads.items():
            self.add_download_to_tree(url, download)

    def add_download_to_tree(self, url, download):
        """Add a download to the tree widget"""
        filename = os.path.basename(download["file_path"])
        size = download["size"]
        downloaded = download["downloaded"]
        
        # Calculate progress percentage
        if size > 0:
            progress = (downloaded / size) * 100
            progress_str = f"{progress:.1f}%"
        else:
            progress_str = "Unknown"
            
        speed = download.get("speed", 0)
        status = download.get("status", "queued")
        
        # Format size and speed
        size_str = self.format_size(size) if size > 0 else "Unknown"
        speed_str = self.format_speed(speed)
        
        item = QTreeWidgetItem([
            filename, 
            size_str, 
            progress_str, 
            speed_str, 
            status.capitalize()
        ])
        item.setData(0, Qt.UserRole, url)
        
        # Colorize based on status with proper text contrast
        if status == "completed":
            for i in range(5):
                item.setBackground(i, QBrush(QColor(200, 255, 200)))  # Light green
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
        elif status == "error":
            for i in range(5):
                item.setBackground(i, QBrush(QColor(255, 200, 200)))  # Light red
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
        elif status == "downloading":
            for i in range(5):
                item.setBackground(i, QBrush(QColor(200, 200, 255)))  # Light blue
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
        elif status == "paused":
            for i in range(5):
                item.setBackground(i, QBrush(QColor(255, 255, 200)))  # Light yellow
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
        elif status == "queued":
            for i in range(5):
                item.setBackground(i, QBrush(QColor(230, 230, 230)))  # Light gray
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                
        self.tree.addTopLevelItem(item)
        self.tree_items[url] = item

    def on_add(self):
        """Add a new download"""
        url, ok = QInputDialog.getText(self, self.tr.t("add_url_title"), self.tr.t("add_url_prompt"))
        if ok and url:
            if self.manager:
                try:
                    # Get number of threads from settings
                    num_threads = self.manager.config.get("threads_per_download", 4)
                    
                    # Fix the callback signatures to handle arguments properly
                    key = self.manager.create_multi_threaded_download(
                        url,
                        progress_callback=lambda downloaded, speed: self.on_download_progress(url, downloaded, speed),
                        complete_callback=lambda url=url: self.on_download_complete(url),
                        error_callback=lambda error=None: self.on_download_error(url, error),
                        num_threads=num_threads
                    )
                    
                    if key:
                        # Add to tree
                        self.add_download_to_tree(key, self.manager.downloads[key])
                        QMessageBox.information(self, self.tr.t("success"), self.tr.t("download_added"))
                    else:
                        QMessageBox.critical(self, self.tr.t("error"), self.tr.t("download_failed"))
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg:
                        QMessageBox.critical(self, self.tr.t("error"), 
                                           "Server is limiting requests (Error 429). Please try again later.")
                    else:
                        QMessageBox.critical(self, self.tr.t("error"), f"{self.tr.t('download_failed')}: {error_msg}")

    def on_start(self):
        """Start selected downloads"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            url = item.data(0, Qt.UserRole)
            if url and self.manager:
                try:
                    if "threads" in self.manager.downloads[url]:
                        # Multi-threaded download
                        self.manager.start_multi_threaded_download(url)
                    else:
                        # Single-threaded download
                        self.manager.start_download(url)
                except Exception as e:
                    self.ui_message_queue.put_message(url, "error", f"{self.tr.t('start_failed')}: {str(e)}")

    def on_pause(self):
        """Pause selected downloads"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            url = item.data(0, Qt.UserRole)
            if url and self.manager:
                try:
                    self.manager.pause_download(url)
                except Exception as e:
                    self.ui_message_queue.put_message(url, "error", f"{self.tr.t('pause_failed')}: {str(e)}")

    def on_remove(self):
        """Remove selected downloads"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
            
        reply = QMessageBox.question(self, self.tr.t("confirm_remove"), 
                                   f"{self.tr.t('confirm_remove_text')}\n\n{len(selected_items)} downloads selected",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes and self.manager:
            for item in selected_items:
                url = item.data(0, Qt.UserRole)
                try:
                    self.manager.remove_download(url)
                    # Remove from tree
                    if url in self.tree_items:
                        index = self.tree.indexOfTopLevelItem(self.tree_items[url])
                        if index >= 0:
                            self.tree.takeTopLevelItem(index)
                        del self.tree_items[url]
                except Exception as e:
                    self.ui_message_queue.put_message(url, "error", f"{self.tr.t('remove_failed')}: {str(e)}")

    def on_settings(self):
        """Open settings dialog"""
        if self.manager:
            dialog = SettingsDialog(self.manager, self)
            if dialog.exec():
                # Settings were saved, update UI if needed
                self.apply_theme()
                # Update language if changed
                if hasattr(self, 'tr') and self.manager.config.get("language") != self.tr.lang:
                    self.on_language_changed(self.manager.config["language"])

    def on_download_progress(self, url, downloaded, speed):
        """Update progress for a download - called from download thread"""
        # Use message queue to handle UI updates in main thread
        self.ui_message_queue.put_message(url, "progress", f"{downloaded},{speed}")

    def on_download_complete(self, url):
        """Handle download completion - called from download thread"""
        # Use message queue to handle UI updates in main thread
        self.ui_message_queue.put_message(url, "complete", "")

    def on_download_error(self, url, error):
        """Handle download error - called from download thread"""
        # Use message queue to handle UI updates in main thread
        self.ui_message_queue.put_message(url, "error", error)

    def handle_ui_message(self, url, msg_type, message):
        """Handle UI messages from the message queue in the main thread"""
        if msg_type == "progress" and url in self.tree_items:
            # Update progress
            parts = message.split(",")
            if len(parts) == 2:
                downloaded = int(parts[0])
                speed = float(parts[1])
                
                item = self.tree_items[url]
                download = self.manager.downloads[url]
                
                # Update progress
                if download["size"] > 0:
                    progress = (downloaded / download["size"]) * 100
                    item.setText(2, f"{progress:.1f}%")
                else:
                    item.setText(2, "Unknown")
                    
                # Update speed
                item.setText(3, self.format_speed(speed))
                
        elif msg_type == "complete" and url in self.tree_items:
            # Download completed
            item = self.tree_items[url]
            download = self.manager.downloads[url]
            
            item.setText(2, "100%")
            item.setText(3, "0 B/s")
            item.setText(4, "Completed")
            
            # Set completion background with proper text contrast
            for i in range(5):
                item.setBackground(i, QBrush(QColor(200, 255, 200)))  # Light green
                item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                
            # Show completion message
            QMessageBox.information(self, self.tr.t("download_complete"), 
                                  f"{self.tr.t('download_complete_text')}: {os.path.basename(download['file_path'])}")
            
        elif msg_type == "error":
            # Download error
            if url in self.tree_items:
                item = self.tree_items[url]
                item.setText(4, f"Error: {message[:20]}...")
                
                # Set error background with proper text contrast
                for i in range(5):
                    item.setBackground(i, QBrush(QColor(255, 200, 200)))  # Light red
                    item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                    
            # Show error message
            QMessageBox.critical(self, self.tr.t("error"), 
                               f"{self.tr.t('download_error_text')}: {message}")

    def refresh_ui(self):
        """Refresh the UI with current download states"""
        if not self.manager:
            return
            
        # Update global stats
        try:
            stats = self.manager.db.get_overall_stats()
            if stats:
                total_downloads, total_bytes, avg_speed = stats
                self.global_label.setText(
                    f"{self.tr.t('total_downloads')}: {total_downloads} | "
                    f"{self.tr.t('total_bytes')}: {self.format_size(total_bytes)} | "
                    f"{self.tr.t('avg_speed')}: {self.format_speed(avg_speed)}"
                )
        except Exception as e:
            print("Error updating global stats:", e)

        # Update individual download items
        for url, download in self.manager.downloads.items():
            if url in self.tree_items:
                item = self.tree_items[url]
                
                # Update progress
                if download["size"] > 0:
                    progress = (download["downloaded"] / download["size"]) * 100
                    item.setText(2, f"{progress:.1f}%")
                else:
                    item.setText(2, "Unknown")
                    
                # Update speed
                speed = download.get("speed", 0)
                item.setText(3, self.format_speed(speed))
                
                # Update status
                item.setText(4, download.get("status", "unknown").capitalize())
                
                # Update color based on status with proper text contrast
                status = download.get("status", "unknown")
                if status == "completed":
                    for i in range(5):
                        item.setBackground(i, QBrush(QColor(200, 255, 200)))  # Light green
                        item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                elif status == "error":
                    for i in range(5):
                        item.setBackground(i, QBrush(QColor(255, 200, 200)))  # Light red
                        item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                elif status == "downloading":
                    for i in range(5):
                        item.setBackground(i, QBrush(QColor(200, 200, 255)))  # Light blue
                        item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                elif status == "paused":
                    for i in range(5):
                        item.setBackground(i, QBrush(QColor(255, 255, 200)))  # Light yellow
                        item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text
                elif status == "queued":
                    for i in range(5):
                        item.setBackground(i, QBrush(QColor(230, 230, 230)))  # Light gray
                        item.setForeground(i, QBrush(QColor(0, 0, 0)))  # Black text

    def on_language_changed(self, lang_code):
        """Change the application language"""
        try:
            self.tr.load_language(lang_code)
            # Update UI labels
            self.setWindowTitle(self.tr.t("app_title"))
            self.tree.setHeaderLabels([
                self.tr.t("menu_file"), 
                self.tr.t("label_size"), 
                self.tr.t("label_progress"), 
                self.tr.t("label_speed"), 
                self.tr.t("label_status")
            ])
            
            # Save language to manager config/db
            if self.manager:
                try:
                    self.manager.db.set_setting("language", lang_code)
                    self.manager.config['language'] = lang_code
                    self.manager.save_config()
                except Exception as e:
                    print("Error saving language setting:", e)
        except Exception as e:
            print("Language change failed:", e)

    def format_size(self, size_bytes):
        """Format bytes to human-readable format"""
        if size_bytes == 0:
            return "0 B"
            
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = int(max(0, min(len(size_names)-1, int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
        
    def format_speed(self, speed_bytes):
        """Format speed to human-readable format"""
        return self.format_size(speed_bytes) + "/s"

def main():
    app = QApplication(sys.argv)
    window = FDMQtMain()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()