# Free Fast Download Manager (ffdm cross-platform)

A powerful, multi-threaded download manager with both Tkinter and PySide6 GUI interfaces.

## Features

- Multi-threaded downloads
- Resume capability
- Database storage
- Cross-platform compatibility
- Multiple GUI options (Tkinter/Qt)
- System tray integration
- Light/dark themes
- Multi-language support

## Installation

```bash
pip install requests pystray pillow pyside6
```

## Usage

### Tkinter Version (default)
```bash
python fdm.py
```

### Qt Version (recommended)
```bash
python fdm_qt.py
```

### Command Line Options
```bash
# Start minimized to system tray
python fdm.py --silent

# Enable debug logging
python fdm.py --debug
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F1 | Show help |
| F2 | Add new download |
| F5 | Refresh download list |
| Ctrl+N | Add new download |
| Ctrl+S | Start selected downloads |
| Ctrl+P | Pause selected downloads |
| Delete | Remove selected downloads |
| Ctrl+, | Open settings |

## Configuration

The application uses an SQLite database (`downloads.db`) to store:
- Download history and status
- Application settings
- Download statistics
- Session information

## Troubleshooting

Common issues and solutions:

1. **Database transaction errors** - Fixed in current version
2. **Tray icon not showing** - Add `fdm.png` to application directory
3. **Download errors** - Check connection and URL validity
4. **Slow downloads** - Adjust chunk size and thread settings

Logs are saved to `fdm.log` for debugging.

## License

MIT License

## Credits

Developed by 0xbytecode 🦅 | deepseek-coder | me

---

**Note**: Please respect copyright laws when downloading content.
