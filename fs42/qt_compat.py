"""Internal Qt binding compatibility for appliance and desktop runtimes.

FieldStation42 historically uses PySide6.  Some supported Linux distributions
ship a native PyQt6/QtWebEngine stack instead.  Prefer a *complete* PySide6
stack, including WebEngine and QtQuick; fall back as one unit to PyQt6 rather
than mixing bindings in one process.
"""
from __future__ import annotations

QT_BACKEND = "pyside6"
try:
    from PySide6.QtCore import QUrl, QTimer, Qt as _Qt, QPointF, QSharedMemory, QRect
    from PySide6.QtGui import QPixmap, QColor, QPaintEvent, QPainter, QFont, QFontMetrics, QLinearGradient, QPen, QFontDatabase
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
except ImportError:
    QT_BACKEND = "pyqt6"
    from PyQt6.QtCore import QUrl, QTimer, Qt as _Qt, QPointF, QSharedMemory, QRect
    from PyQt6.QtGui import QPixmap, QColor, QPaintEvent, QPainter, QFont, QFontMetrics, QLinearGradient, QPen, QFontDatabase
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow
    from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings


class _QtCompat:
    """Expose only the legacy aliases FieldStation42's Qt surfaces consume."""

    FramelessWindowHint = getattr(_Qt, "FramelessWindowHint", _Qt.WindowType.FramelessWindowHint)
    WindowStaysOnTopHint = getattr(_Qt, "WindowStaysOnTopHint", _Qt.WindowType.WindowStaysOnTopHint)
    Tool = getattr(_Qt, "Tool", _Qt.WindowType.Tool)
    WA_TranslucentBackground = getattr(_Qt, "WA_TranslucentBackground", _Qt.WidgetAttribute.WA_TranslucentBackground)
    WA_NoSystemBackground = getattr(_Qt, "WA_NoSystemBackground", _Qt.WidgetAttribute.WA_NoSystemBackground)
    BlankCursor = getattr(_Qt, "BlankCursor", _Qt.CursorShape.BlankCursor)
    NoPen = getattr(_Qt, "NoPen", _Qt.PenStyle.NoPen)
    AlignLeft = getattr(_Qt, "AlignLeft", _Qt.AlignmentFlag.AlignLeft)
    AlignVCenter = getattr(_Qt, "AlignVCenter", _Qt.AlignmentFlag.AlignVCenter)
    SmoothTransformation = getattr(_Qt, "SmoothTransformation", _Qt.TransformationMode.SmoothTransformation)
    black = getattr(_Qt, "black", _Qt.GlobalColor.black)
    transparent = getattr(_Qt, "transparent", _Qt.GlobalColor.transparent)


Qt = _QtCompat()
QFONT_BOLD = getattr(QFont, "Bold", QFont.Weight.Bold)
QFONT_NORMAL = getattr(QFont, "Normal", QFont.Weight.Normal)
QPAINTER_ANTIALIASING = getattr(QPainter, "Antialiasing", QPainter.RenderHint.Antialiasing)
QPAINTER_TEXT_ANTIALIASING = getattr(QPainter, "TextAntialiasing", QPainter.RenderHint.TextAntialiasing)
