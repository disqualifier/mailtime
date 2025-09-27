import logging
import sys
import os
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

log = logging.getLogger('MailClient')


def load_svg_icon(name: str, size: int = 16, color: str = "#000000") -> QIcon:
    """Load FontAwesome SVG icon and return as QIcon"""
    try:
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
            svg_path = base_path / "fontawesome_icons" / f"{name}.svg"
        else:
            base_path = Path(__file__).parent
            svg_path = base_path / "assets" / "fontawesome_icons" / f"{name}.svg"

        if svg_path.exists():
            try:
                with open(svg_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read()

                if color != "#000000":
                    if 'fill=' not in svg_content:
                        svg_content = svg_content.replace('<path d=', f'<path fill="{color}" d=')
                    else:
                        svg_content = svg_content.replace('fill="currentColor"', f'fill="{color}"')

                renderer = QSvgRenderer()
                if renderer.load(svg_content.encode('utf-8')):
                    pixmap = QPixmap(size, size)
                    pixmap.fill(Qt.GlobalColor.transparent)

                    painter = QPainter(pixmap)
                    if painter.isActive():
                        renderer.render(painter)
                        painter.end()
                        return QIcon(pixmap)
                    else:
                        log.warning(f"Could not create painter for icon {name}")
                else:
                    log.warning(f"Could not load SVG content for icon {name}")
            except Exception as e:
                log.error(f"Error reading SVG file {svg_path}: {e}")
        else:
            log.warning(f"SVG icon not found: {svg_path}")

        return QIcon()
    except Exception as e:
        log.error(f"Error loading SVG icon {name}: {e}")
        return QIcon()


def get_resource_path(filename: str) -> Path:
    """Get path to bundled resource file for PyInstaller compatibility"""
    try:
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
            return base_path / filename
        else:
            base_path = Path(__file__).parent
            return base_path / "assets" / filename
    except Exception as e:
        log.error(f"Error getting resource path for {filename}: {e}")
        return Path(filename)


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