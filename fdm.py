# Importing Required Modules
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests
import os
import time
import threading
from urllib.parse import urlparse
import json
from datetime import datetime
import math
import sys
import pystray
from PIL import Image, ImageDraw
import io
import sqlite3
import argparse

# Constants
DEFAULT_CHUNK_SIZE = 8192
MAX_CONNECTIONS = 8
CONFIG_FILE = "downloader_config.json"
DB_FILE = "downloads.db"

class DownloadDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.create_tables()
        
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Downloads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                save_path TEXT NOT NULL,
                total_size INTEGER DEFAULT 0,
                downloaded INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_date DATETIME,
                average_speed REAL DEFAULT 0
            )
        ''')
        
        # Download sessions table for tracking speed over time
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id INTEGER,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                downloaded_bytes INTEGER DEFAULT 0,
                average_speed REAL DEFAULT 0,
                FOREIGN KEY (download_id) REFERENCES downloads (id)
            )
        ''')
        
        # Stats table for overall statistics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_downloads INTEGER DEFAULT 0,
                total_downloaded_bytes INTEGER DEFAULT 0,
                average_speed REAL DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Initialize stats if empty
        cursor.execute("SELECT COUNT(*) FROM stats")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO stats (total_downloads, total_downloaded_bytes) VALUES (0, 0)")
            
        self.conn.commit()
        
    def add_download(self, url, filename, save_path):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO downloads (url, filename, save_path) VALUES (?, ?, ?)",
            (url, filename, save_path)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def update_download_progress(self, download_id, downloaded, total_size, status, speed=0):
        cursor = self.conn.cursor()
        
        # Update download record
        cursor.execute(
            "UPDATE downloads SET downloaded = ?, total_size = ?, status = ? WHERE id = ?",
            (downloaded, total_size, status, download_id)
        )
        
        # Update or create download session
        cursor.execute(
            "SELECT id FROM download_sessions WHERE download_id = ? AND end_time IS NULL",
            (download_id,)
        )
        session = cursor.fetchone()
        
        if session:
            session_id = session[0]
            cursor.execute(
                "UPDATE download_sessions SET downloaded_bytes = ?, average_speed = ? WHERE id = ?",
                (downloaded, speed, session_id)
            )
        else:
            cursor.execute(
                "INSERT INTO download_sessions (download_id, downloaded_bytes, average_speed) VALUES (?, ?, ?)",
                (download_id, downloaded, speed)
            )
            
        self.conn.commit()
        
    def complete_download(self, download_id, average_speed):
        cursor = self.conn.cursor()
        
        # Update download record
        cursor.execute(
            "UPDATE downloads SET status = 'completed', completed_date = CURRENT_TIMESTAMP, average_speed = ? WHERE id = ?",
            (average_speed, download_id)
        )
        
        # End the download session
        cursor.execute(
            "UPDATE download_sessions SET end_time = CURRENT_TIMESTAMP WHERE download_id = ? AND end_time IS NULL",
            (download_id,)
        )
        
        # Update stats
        cursor.execute(
            "UPDATE stats SET total_downloads = total_downloads + 1, last_updated = CURRENT_TIMESTAMP"
        )
        
        self.conn.commit()
        
    def get_download_history(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, url, filename, total_size, downloaded, status, added_date, completed_date, average_speed FROM downloads ORDER BY added_date DESC"
        )
        return cursor.fetchall()
    
    def get_active_downloads(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, url, filename, total_size, downloaded, status FROM downloads WHERE status IN ('queued', 'downloading', 'paused')"
        )
        return cursor.fetchall()
    
    def get_overall_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT total_downloads, total_downloaded_bytes, average_speed FROM stats")
        return cursor.fetchone()
    
    def update_overall_speed(self, average_speed):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE stats SET average_speed = ?", (average_speed,))
        self.conn.commit()


class DownloadThread(threading.Thread):
    def __init__(self, url, file_path, start_byte, end_byte, progress_callback, 
                 complete_callback, error_callback, headers=None, timeout=30, db_id=None, db_manager=None):
        super().__init__()
        self.url = url
        self.file_path = file_path
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.progress_callback = progress_callback
        self.complete_callback = complete_callback
        self.error_callback = error_callback
        self.headers = headers or {}
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.downloaded = 0  # Bytes downloaded in this session
        self.speed = 0
        self.last_update_time = time.time()
        self.last_downloaded = 0
        self.total_bytes = end_byte - start_byte + 1 if end_byte > start_byte else 0
        self.db_id = db_id
        self.db_manager = db_manager
        self.speed_samples = []  # For calculating average speed
        
    def run(self):
        try:
            # Add range header for partial download
            range_header = f'bytes={self.start_byte + self.downloaded}-{self.end_byte}'
            self.headers['Range'] = range_header
            
            response = requests.get(self.url, headers=self.headers, stream=True, 
                                  timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Open file in append mode to continue download
            with open(self.file_path, 'ab') as f:
                for chunk in response.iter_content(chunk_size=self.calculate_chunk_size()):
                    if self._stop_event.is_set():
                        break
                        
                    # Wait if paused
                    while self._pause_event.is_set():
                        time.sleep(0.1)
                        if self._stop_event.is_set():
                            break
                    
                    if chunk:
                        f.write(chunk)
                        self.downloaded += len(chunk)
                        
                        # Calculate speed
                        current_time = time.time()
                        time_diff = current_time - self.last_update_time
                        
                        if time_diff >= 0.5:  # Update speed every 0.5 seconds
                            self.speed = (self.downloaded - self.last_downloaded) / time_diff
                            self.last_downloaded = self.downloaded
                            self.last_update_time = current_time
                            self.speed_samples.append(self.speed)
                            
                        # Report progress (total downloaded = start_byte + downloaded)
                        if self.progress_callback:
                            self.progress_callback(self.start_byte + self.downloaded, self.speed)
                            
                        # Update database
                        if self.db_manager and self.db_id:
                            self.db_manager.update_download_progress(
                                self.db_id, self.start_byte + self.downloaded, 
                                self.total_bytes + self.start_byte, 
                                "paused" if self._pause_event.is_set() else "downloading",
                                self.speed
                            )
                            
                        # Break if download is complete
                        if self.downloaded >= self.total_bytes:
                            break
            
            if not self._stop_event.is_set():
                # Calculate average speed
                avg_speed = sum(self.speed_samples) / len(self.speed_samples) if self.speed_samples else 0
                self.complete_callback(avg_speed)
                
        except Exception as e:
            self.error_callback(str(e))
    
    def calculate_chunk_size(self):
        # Dynamic chunk sizing based on network speed
        if self.speed > 0:
            # Aim for chunks that take about 0.1 seconds to download
            dynamic_size = max(1024, min(65536, int(self.speed * 0.1)))
            return dynamic_size
        return DEFAULT_CHUNK_SIZE
    
    def stop(self):
        self._stop_event.set()
        
    def pause(self):
        self._pause_event.set()
        
    def resume(self):
        self._pause_event.clear()
        
    def is_paused(self):
        return self._pause_event.is_set()
        
    def is_stopped(self):
        return self._stop_event.is_set()


class DownloadManager:
    def __init__(self):
        self.downloads = {}
        self.config = self.load_config()
        self.db = DownloadDB()
        
    def load_config(self):
        default_config = {
            "save_path": os.path.join(os.path.expanduser("~"), "Downloads"),
            "max_connections": MAX_CONNECTIONS,
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "timeout": 30,
            "theme": "light",
            "proxy": None
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    return {**default_config, **json.load(f)}
        except:
            pass
            
        return default_config
        
    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except:
            pass
            
    def get_file_size(self, url, headers=None):
        try:
            response = requests.head(url, headers=headers, allow_redirects=True, 
                                   timeout=self.config["timeout"])
            response.raise_for_status()
            return int(response.headers.get('content-length', 0))
        except:
            return 0
            
    def create_download(self, url, file_name=None, progress_callback=None, 
                       complete_callback=None, error_callback=None):
        if not file_name:
            file_name = os.path.basename(urlparse(url).path) or "download"
            
        file_path = os.path.join(self.config["save_path"], file_name)
        temp_file_path = file_path + ".part"
        
        # Check for existing partial download
        start_byte = 0
        if os.path.exists(temp_file_path):
            start_byte = os.path.getsize(temp_file_path)
            
        file_size = self.get_file_size(url)
        
        # Headers
        headers = {'User-Agent': 'FDM/1.0'}
        if self.config["proxy"]:
            headers['Proxy'] = self.config["proxy"]
            
        # Add to database
        db_id = self.db.add_download(url, file_name, self.config["save_path"])
            
        # Create download thread
        thread = DownloadThread(
            url, temp_file_path, start_byte, file_size - 1,
            progress_callback, 
            lambda avg_speed: self.on_download_complete(url, temp_file_path, file_path, complete_callback, avg_speed),
            error_callback,
            headers,
            self.config["timeout"],
            db_id,
            self.db
        )
        
        self.downloads[url] = {
            "thread": thread,
            "file_path": file_path,
            "temp_path": temp_file_path,
            "size": file_size,
            "downloaded": start_byte,
            "speed": 0,
            "status": "paused" if start_byte > 0 else "queued",
            "start_time": time.time(),
            "db_id": db_id
        }
        
        # Update database
        self.db.update_download_progress(db_id, start_byte, file_size, "queued")
        
        return url
        
    def start_download(self, url):
        if url in self.downloads:
            download = self.downloads[url]
            if download["status"] in ["queued", "paused", "error"]:
                # If thread was stopped, create a new one
                if download["thread"].is_stopped() or not download["thread"].is_alive():
                    self.recreate_thread(url)
                
                download["status"] = "downloading"
                if not download["thread"].is_alive():
                    download["thread"].start()
                else:
                    download["thread"].resume()
                
                # Update database
                self.db.update_download_progress(download["db_id"], download["downloaded"], download["size"], "downloading")
    
    def recreate_thread(self, url):
        if url not in self.downloads:
            return
            
        download = self.downloads[url]
        temp_file_path = download["temp_path"]
        
        # Get current downloaded bytes
        current_downloaded = os.path.getsize(temp_file_path) if os.path.exists(temp_file_path) else 0
        
        # Headers
        headers = {'User-Agent': 'FDM/1.0'}
        if self.config["proxy"]:
            headers['Proxy'] = self.config["proxy"]
            
        # Create a new thread
        thread = DownloadThread(
            url, temp_file_path, current_downloaded, download["size"] - 1,
            lambda downloaded, speed: self.update_progress(url, downloaded, speed),
            lambda avg_speed: self.on_download_complete(url, temp_file_path, download["file_path"], None, avg_speed),
            lambda error: self.on_download_error(url, error),
            headers,
            self.config["timeout"],
            download["db_id"],
            self.db
        )
        
        download["thread"] = thread
        download["downloaded"] = current_downloaded
                
    def pause_download(self, url):
        if url in self.downloads and self.downloads[url]["status"] == "downloading":
            self.downloads[url]["status"] = "paused"
            self.downloads[url]["thread"].pause()
            
            # Update database
            download = self.downloads[url]
            self.db.update_download_progress(download["db_id"], download["downloaded"], download["size"], "paused")
            
    def resume_download(self, url):
        if url in self.downloads and self.downloads[url]["status"] == "paused":
            self.downloads[url]["status"] = "downloading"
            self.downloads[url]["thread"].resume()
            
            # Update database
            download = self.downloads[url]
            self.db.update_download_progress(download["db_id"], download["downloaded"], download["size"], "downloading")
            
    def toggle_pause_resume(self, url):
        if url in self.downloads:
            if self.downloads[url]["status"] == "downloading":
                self.pause_download(url)
                return "paused"
            elif self.downloads[url]["status"] == "paused":
                self.resume_download(url)
                return "resumed"
        return None
            
    def stop_download(self, url):
        if url in self.downloads:
            self.downloads[url]["status"] = "stopped"
            self.downloads[url]["thread"].stop()
            
            # Update database
            download = self.downloads[url]
            self.db.update_download_progress(download["db_id"], download["downloaded"], download["size"], "stopped")
            
    def remove_download(self, url):
        if url in self.downloads:
            if self.downloads[url]["status"] == "downloading":
                self.stop_download(url)
            del self.downloads[url]
            
    def on_download_complete(self, url, temp_path, final_path, complete_callback, avg_speed):
        if url in self.downloads:
            self.downloads[url]["status"] = "completed"
            self.downloads[url]["downloaded"] = self.downloads[url]["size"]
            
            # Rename temp file to final name
            try:
                if os.path.exists(temp_path):
                    os.rename(temp_path, final_path)
            except:
                pass
            
            # Update database
            download = self.downloads[url]
            self.db.complete_download(download["db_id"], avg_speed)
                
            if complete_callback:
                complete_callback(url)
                
    def update_progress(self, url, downloaded, speed):
        if url in self.downloads:
            self.downloads[url]["downloaded"] = downloaded
            self.downloads[url]["speed"] = speed
            
    def load_downloads_from_db(self):
        """Load active downloads from database on startup"""
        active_downloads = self.db.get_active_downloads()
        for download in active_downloads:
            db_id, url, filename, total_size, downloaded, status = download
            
            file_path = os.path.join(self.config["save_path"], filename)
            temp_file_path = file_path + ".part"
            
            # Headers
            headers = {'User-Agent': 'FDM/1.0'}
            if self.config["proxy"]:
                headers['Proxy'] = self.config["proxy"]
                
            # Create download thread
            thread = DownloadThread(
                url, temp_file_path, downloaded, total_size - 1,
                lambda downloaded, speed: self.update_progress(url, downloaded, speed),
                lambda avg_speed: self.on_download_complete(url, temp_file_path, file_path, None, avg_speed),
                lambda error: self.on_download_error(url, error),
                headers,
                self.config["timeout"],
                db_id,
                self.db
            )
            
            self.downloads[url] = {
                "thread": thread,
                "file_path": file_path,
                "temp_path": temp_file_path,
                "size": total_size,
                "downloaded": downloaded,
                "speed": 0,
                "status": status,
                "start_time": time.time(),
                "db_id": db_id
            }
            
            # Auto-resume downloads that were in progress
            if status == "downloading":
                # Start the download after a short delay to allow UI to initialize
                threading.Timer(1.0, lambda: self.start_download(url)).start()


class ModernDownloader:
    def __init__(self, root, silent_mode=False):
        self.root = root
        self.root.title("FDM - Free Download Manager")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)
        
        # Initialize download manager
        self.manager = DownloadManager()
        
        # Load downloads from database
        self.manager.load_downloads_from_db()
        
        # Setup styles and theme
        self.setup_styles()
        
        # Create UI
        self.create_ui()
        
        # Apply saved theme
        self.apply_theme(self.manager.config["theme"])
        
        # Setup system tray icon
        self.setup_tray_icon()
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Bind Enter key to add download
        self.url_entry.bind('<Return>', lambda event: self.add_download())
        
        # Bind Delete key to remove selected downloads
        self.tree.bind('<Delete>', lambda event: self.remove_selected_downloads())
        
        # Start in silent mode if requested
        self.silent_mode = silent_mode
        if self.silent_mode:
            self.root.withdraw()
        
        # Refresh UI periodically
        self.update_ui()
        
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Light theme colors
        self.light_bg = "#f0f0f0"
        self.light_fg = "#000000"
        self.light_accent = "#4CAF50"  # Green accent
        self.light_secondary = "#2196F3"  # Blue for secondary actions
        self.light_frame = "#ffffff"
        
        # Dark theme colors
        self.dark_bg = "#2d2d30"
        self.dark_fg = "#ffffff"
        self.dark_accent = "#4CAF50"  # Green accent
        self.dark_secondary = "#2196F3"  # Blue for secondary actions
        self.dark_frame = "#3e3e42"
        
    def apply_theme(self, theme_name):
        if theme_name == "dark":
            bg_color = self.dark_bg
            fg_color = self.dark_fg
            accent_color = self.dark_accent
            secondary_color = self.dark_secondary
            frame_color = self.dark_frame
            
            self.style.configure("TFrame", background=frame_color)
            self.style.configure("TLabel", background=frame_color, foreground=fg_color)
            self.style.configure("TButton", background=secondary_color, foreground=fg_color)
            self.style.configure("Accent.TButton", background=accent_color, foreground=fg_color)
            self.style.configure("TEntry", fieldbackground=frame_color, foreground=fg_color)
            self.style.configure("TProgressbar", background=accent_color)
            self.style.configure("Treeview", background=frame_color, foreground=fg_color, fieldbackground=frame_color)
            self.style.configure("Treeview.Heading", background=frame_color, foreground=fg_color)
            self.style.configure("TCheckbutton", background=frame_color, foreground=fg_color)
            
        else:  # light theme
            bg_color = self.light_bg
            fg_color = self.light_fg
            accent_color = self.light_accent
            secondary_color = self.light_secondary
            frame_color = self.light_frame
            
            self.style.configure("TFrame", background=frame_color)
            self.style.configure("TLabel", background=frame_color, foreground=fg_color)
            self.style.configure("TButton", background=secondary_color, foreground=fg_color)
            self.style.configure("Accent.TButton", background=accent_color, foreground=fg_color)
            self.style.configure("TEntry", fieldbackground=frame_color, foreground=fg_color)
            self.style.configure("TProgressbar", background=accent_color)
            self.style.configure("Treeview", background=frame_color, foreground=fg_color, fieldbackground=frame_color)
            self.style.configure("Treeview.Heading", background=frame_color, foreground=fg_color)
            self.style.configure("TCheckbutton", background=frame_color, foreground=fg_color)
        
        # Apply to root window
        self.root.configure(background=bg_color)
        
        # Update theme config
        self.manager.config["theme"] = theme_name
        self.manager.save_config()
        
    def setup_tray_icon(self):
        # Create a simple icon for the system tray
        self.tray_icon = None
        
        # Generate an image for the tray icon
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='white')
        dc = ImageDraw.Draw(image)
        dc.rectangle([width//2-20, height//2-20, width//2+20, height//2+20], fill='green')
        dc.text((width//2-10, height//2-5), "FDM", fill='white')
        
        # Convert to bytes
        bio = io.BytesIO()
        image.save(bio, format='PNG')
        bio.seek(0)
        
        # Create menu for the tray icon
        menu = pystray.Menu(
            pystray.MenuItem('Show', self.show_window),
            pystray.MenuItem('Exit', self.quit_application)
        )
        
        # Create the tray icon
        self.tray_icon = pystray.Icon('FDM', Image.open(bio), 'FDM Download Manager', menu)
        
    def show_window(self, icon, item):
        self.root.after(0, self.root.deiconify)
        
    def quit_application(self, icon, item):
        self.tray_icon.stop()
        self.root.destroy()
        
    def on_closing(self):
        # Hide the window instead of closing
        self.root.withdraw()
        
    def create_ui(self):
        # Create main paned window for resizable panels
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left frame for download list
        self.left_frame = ttk.Frame(self.main_pane, width=600)
        self.main_pane.add(self.left_frame, weight=3)
        
        # Right frame for details and controls
        self.right_frame = ttk.Frame(self.main_pane, width=300)
        self.main_pane.add(self.right_frame, weight=1)
        
        # Create URL entry frame
        url_frame = ttk.Frame(self.left_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(url_frame, text="URL:").pack(side=tk.LEFT, padx=(0, 5))
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=50)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.add_btn = ttk.Button(url_frame, text="Add Download", command=self.add_download, style="Accent.TButton")
        self.add_btn.pack(side=tk.RIGHT)
        
        # Create downloads list
        list_frame = ttk.Frame(self.left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("filename", "size", "progress", "status", "speed")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        
        # Define headings
        self.tree.heading("filename", text="Filename")
        self.tree.heading("size", text="Size")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("status", text="Status")
        self.tree.heading("speed", text="Speed")
        
        # Define columns
        self.tree.column("filename", width=200)
        self.tree.column("size", width=100)
        self.tree.column("progress", width=150)
        self.tree.column("status", width=100)
        self.tree.column("speed", width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure tags for status coloring
        self.tree.tag_configure('completed', foreground='green')
        self.tree.tag_configure('error', foreground='red')
        self.tree.tag_configure('downloading', foreground='blue')
        self.tree.tag_configure('paused', foreground='orange')
        self.tree.tag_configure('queued', foreground='gray')
        self.tree.tag_configure('stopped', foreground='darkred')
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        # Create control buttons frame
        control_frame = ttk.Frame(self.left_frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.start_btn = ttk.Button(control_frame, text="Start", command=self.start_selected_downloads, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.pause_btn = ttk.Button(control_frame, text="Pause", command=self.pause_selected_downloads)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self.stop_selected_downloads)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.remove_btn = ttk.Button(control_frame, text="Remove", command=self.remove_selected_downloads)
        self.remove_btn.pack(side=tk.LEFT)
        
        # Create details frame on the right
        details_frame = ttk.LabelFrame(self.right_frame, text="Download Details")
        details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create details text widget
        self.details_text = scrolledtext.ScrolledText(details_frame, height=15, width=35)
        self.details_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.details_text.config(state=tk.DISABLED)
        
        # Create settings button
        settings_frame = ttk.Frame(self.right_frame)
        settings_frame.pack(fill=tk.X)
        
        self.settings_btn = ttk.Button(settings_frame, text="Settings", command=self.open_settings)
        self.settings_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.theme_btn = ttk.Button(settings_frame, text="Toggle Theme", command=self.toggle_theme)
        self.theme_btn.pack(fill=tk.X)
        
        # Add credit label at the bottom center
        credit_frame = ttk.Frame(self.right_frame)
        credit_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        credit_label = ttk.Label(credit_frame, text="0xbytecode 🦅", font=("Arial", 8))
        credit_label.pack()
        
        # Initialize selection
        self.selected_urls = []
        
        # Load existing downloads from manager
        self.load_existing_downloads()
        
    def load_existing_downloads(self):
        """Load existing downloads from manager into the treeview"""
        for url, download in self.manager.downloads.items():
            size_str = self.format_size(download["size"]) if download["size"] > 0 else "Unknown"
            
            # Calculate progress percentage
            if download['size'] > 0:
                progress = (download['downloaded'] / download['size']) * 100
                progress_str = self.get_progress_bar(progress)
            else:
                progress_str = "Unknown"
                
            # Insert into treeview with appropriate tag
            self.tree.insert("", "end", iid=url, values=(
                os.path.basename(download["file_path"]), 
                size_str, 
                progress_str, 
                download["status"].capitalize(), 
                self.format_speed(download["speed"])
            ), tags=(download["status"],))
            
    def add_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL")
            return
            
        # Generate filename from URL
        file_name = os.path.basename(urlparse(url).path) or "download"
            
        # Add to download manager
        download_url = self.manager.create_download(
            url, 
            file_name,
            lambda downloaded, speed: self.manager.update_progress(url, downloaded, speed),
            lambda url: self.on_download_complete(url),
            lambda error: self.on_download_error(url, error)
        )
        
        # Add to treeview
        size = self.manager.downloads[download_url]["size"]
        size_str = self.format_size(size) if size > 0 else "Unknown"
        
        self.tree.insert("", "end", iid=download_url, values=(
            file_name, 
            size_str, 
            "0%", 
            "Queued", 
            "0 B/s"
        ), tags=("queued",))
        
        # Clear URL entry
        self.url_var.set("")
        
    def get_progress_bar(self, percentage):
        bar_length = 20
        filled_length = int(bar_length * percentage / 100)
        # Use green color for the completed part (using ANSI escape codes)
        bar = '[' + '\033[92m' + '=' * filled_length + '\033[0m' + '>' + ' ' * (bar_length - filled_length) + ']'
        return f"{bar} {percentage:.1f}%"
        
    def start_selected_downloads(self):
        for url in self.selected_urls:
            self.manager.start_download(url)
        self.update_pause_button_text()
            
    def pause_selected_downloads(self):
        for url in self.selected_urls:
            if url in self.manager.downloads and self.manager.downloads[url]["status"] == "downloading":
                self.manager.pause_download(url)
        self.update_pause_button_text()
            
    def stop_selected_downloads(self):
        for url in self.selected_urls:
            if url in self.manager.downloads:
                self.manager.stop_download(url)
        self.update_pause_button_text()
            
    def remove_selected_downloads(self):
        for url in self.selected_urls:
            if url in self.manager.downloads:
                self.manager.remove_download(url)
                self.tree.delete(url)
        self.selected_urls = []
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        self.details_text.config(state=tk.DISABLED)
            
    def update_pause_button_text(self):
        if self.selected_urls and all(url in self.manager.downloads for url in self.selected_urls):
            statuses = [self.manager.downloads[url]["status"] for url in self.selected_urls]
            if all(status == "downloading" for status in statuses):
                self.pause_btn.config(text="Pause")
            elif all(status == "paused" for status in statuses):
                self.pause_btn.config(text="Resume")
            else:
                self.pause_btn.config(text="Pause/Resume")
            
    def on_select(self, event):
        selection = self.tree.selection()
        if selection:
            self.selected_urls = selection
            self.update_details()
            self.update_pause_button_text()
            
    def update_details(self):
        if self.selected_urls and len(self.selected_urls) == 1:
            url = self.selected_urls[0]
            if url in self.manager.downloads:
                download = self.manager.downloads[url]
                
                self.details_text.config(state=tk.NORMAL)
                self.details_text.delete(1.0, tk.END)
                
                details = f"URL: {url}\n"
                details += f"Filename: {os.path.basename(download['file_path'])}\n"
                details += f"Size: {self.format_size(download['size'])}\n"
                details += f"Downloaded: {self.format_size(download['downloaded'])}\n"
                details += f"Status: {download['status']}\n"
                details += f"Speed: {self.format_speed(download['speed'])}\n"
                
                if download['status'] == 'completed':
                    elapsed = time.time() - download['start_time']
                    details += f"Time: {self.format_time(elapsed)}\n"
                elif download['status'] == 'downloading' and download['speed'] > 0:
                    remaining = download['size'] - download['downloaded']
                    if remaining > 0 and download['speed'] > 0:
                        eta = remaining / download['speed']
                        details += f"ETA: {self.format_time(eta)}\n"
                    
                self.details_text.insert(tk.END, details)
                self.details_text.config(state=tk.DISABLED)
        else:
            self.details_text.config(state=tk.NORMAL)
            self.details_text.delete(1.0, tk.END)
            self.details_text.insert(tk.END, f"{len(self.selected_urls)} downloads selected")
            self.details_text.config(state=tk.DISABLED)
            
    def on_download_complete(self, url):
        # Update treeview
        if self.tree.exists(url):
            download = self.manager.downloads[url]
            self.tree.set(url, "progress", self.get_progress_bar(100))
            self.tree.set(url, "status", "Completed")
            self.tree.set(url, "speed", "0 B/s")
            # Update tag for completed status
            self.tree.item(url, tags=('completed',))
            
        # Update details if this is the selected download
        if url in self.selected_urls:
            self.update_details()
            
    def on_download_error(self, url, error):
        if self.tree.exists(url):
            self.tree.set(url, "status", f"Error: {error[:20]}...")
            # Update tag for error status
            self.tree.item(url, tags=('error',))
            
        if url in self.selected_urls:
            self.update_details()
            
    def update_ui(self):
        # Update all downloads in the treeview
        for url in self.manager.downloads:
            download = self.manager.downloads[url]
            
            if self.tree.exists(url):
                # Calculate progress percentage
                if download['size'] > 0:
                    progress = (download['downloaded'] / download['size']) * 100
                    progress_str = self.get_progress_bar(progress)
                else:
                    progress_str = "Unknown"
                    
                # Update tree values
                self.tree.set(url, "progress", progress_str)
                self.tree.set(url, "status", download['status'].capitalize())
                self.tree.set(url, "speed", self.format_speed(download['speed']))
                
                # Update tag for status coloring
                self.tree.item(url, tags=(download['status'],))
                
                # Update size if it was unknown before
                if self.tree.set(url, "size") == "Unknown" and download['size'] > 0:
                    self.tree.set(url, "size", self.format_size(download['size']))
        
        # Update details if a download is selected
        if self.selected_urls:
            self.update_details()
            
        # Update pause button text
        self.update_pause_button_text()
        
        # Schedule next update
        self.root.after(1000, self.update_ui)
        
    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
            
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
        
    def format_speed(self, speed_bytes):
        return self.format_size(speed_bytes) + "/s"
        
    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        
    def open_settings(self):
        # Create settings window
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Download Settings")
        settings_window.geometry("500x400")
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # Apply theme to settings window
        if self.manager.config["theme"] == "dark":
            settings_window.configure(background=self.dark_bg)
        else:
            settings_window.configure(background=self.light_bg)
            
        # Create settings frame
        settings_frame = ttk.Frame(settings_window)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Save path setting
        ttk.Label(settings_frame, text="Save Path:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        path_frame = ttk.Frame(settings_frame)
        path_frame.grid(row=0, column=1, sticky=tk.EW, pady=(0, 5))
        path_frame.columnconfigure(0, weight=1)
        
        path_var = tk.StringVar(value=self.manager.config["save_path"])
        path_entry = ttk.Entry(path_frame, textvariable=path_var)
        path_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        
        def browse_path():
            path = filedialog.askdirectory(initialdir=path_var.get())
            if path:
                path_var.set(path)
                
        ttk.Button(path_frame, text="Browse", command=browse_path).grid(row=0, column=1)
        
        # Max connections setting
        ttk.Label(settings_frame, text="Max Connections:").grid(row=1, column=0, sticky=tk.W, pady=5)
        connections_var = tk.StringVar(value=str(self.manager.config["max_connections"]))
        connections_spin = ttk.Spinbox(settings_frame, from_=1, to=16, textvariable=connections_var, width=10)
        connections_spin.grid(row=1, column=1, sticky=tk.W, pady=5)

        # Chunk size setting
        ttk.Label(settings_frame, text="Chunk Size (bytes):").grid(row=2, column=0, sticky=tk.W, pady=5)
        chunk_var = tk.StringVar(value=str(self.manager.config["chunk_size"]))
        chunk_combo = ttk.Combobox(settings_frame, textvariable=chunk_var, values=[
            "1024", "2048", "4096", "8192", "16384", "32768"
        ], state="readonly", width=10)
        chunk_combo.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Timeout setting
        ttk.Label(settings_frame, text="Timeout (seconds):").grid(row=3, column=0, sticky=tk.W, pady=5)
        timeout_var = tk.StringVar(value=str(self.manager.config["timeout"]))
        timeout_spin = ttk.Spinbox(settings_frame, from_=5, to=120, textvariable=timeout_var, width=10)
        timeout_spin.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Proxy setting
        ttk.Label(settings_frame, text="Proxy (optional):").grid(row=4, column=0, sticky=tk.W, pady=5)
        proxy_var = tk.StringVar(value=self.manager.config["proxy"] or "")
        proxy_entry = ttk.Entry(settings_frame, textvariable=proxy_var)
        proxy_entry.grid(row=4, column=1, sticky=tk.EW, pady=5)
        
        # Theme setting
        ttk.Label(settings_frame, text="Theme:").grid(row=5, column=0, sticky=tk.W, pady=5)
        theme_var = tk.StringVar(value=self.manager.config["theme"])
        theme_combo = ttk.Combobox(settings_frame, textvariable=theme_var, 
                                  values=["light", "dark"], state="readonly", width=10)
        theme_combo.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(settings_frame)
        buttons_frame.grid(row=6, column=0, columnspan=2, pady=20)
        
        def save_settings():
            self.manager.config["save_path"] = path_var.get()
            self.manager.config["max_connections"] = int(connections_var.get())
            self.manager.config["chunk_size"] = int(chunk_var.get())
            self.manager.config["timeout"] = int(timeout_var.get())
            self.manager.config["proxy"] = proxy_var.get() or None
            self.manager.config["theme"] = theme_var.get()
            
            self.manager.save_config()
            self.apply_theme(theme_var.get())
            settings_window.destroy()
            
        ttk.Button(buttons_frame, text="Save", command=save_settings, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(buttons_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.LEFT)
        
        # Configure grid weights
        settings_frame.columnconfigure(1, weight=1)
        
    def toggle_theme(self):
        current_theme = self.manager.config["theme"]
        new_theme = "dark" if current_theme == "light" else "light"
        self.apply_theme(new_theme)


def parse_arguments():
    parser = argparse.ArgumentParser(description='Free Download Manager')
    parser.add_argument('--silent', action='store_true', help='Start the application in silent mode (minimized to tray)')
    return parser.parse_args()


# Creating TK Container
if __name__ == "__main__":
    args = parse_arguments()
    
    root = tk.Tk()
    app = ModernDownloader(root, silent_mode=args.silent)
    
    # Start the tray icon in a separate thread
    def run_tray_icon():
        app.tray_icon.run()
    
    tray_thread = threading.Thread(target=run_tray_icon, daemon=True)
    tray_thread.start()
    
    root.mainloop()
