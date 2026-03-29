"""
Map tool for drawing bounding box on canvas
"""
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor
from .compat import CrossCursor, LeftButton, Key_Escape
from qgis.core import (
    Qgis,
    QgsRectangle,
    QgsGeometry,
    QgsPointXY
)
from qgis.gui import QgsMapTool, QgsRubberBand


class BBoxMapTool(QgsMapTool):
    """Map tool for selecting bounding box by drawing on canvas."""

    # Signal emitted when bbox is drawn
    bboxDrawn = pyqtSignal(QgsRectangle)

    def __init__(self, canvas):
        """Initialize the bbox map tool."""
        super().__init__(canvas)
        self.canvas = canvas
        self.start_point = None
        self.end_point = None
        self.rubber_band = None
        self.is_drawing = False

        # Create rubber band for visual feedback
        self._create_rubber_band()

        # Set cursor
        self.setCursor(CrossCursor)

    def _create_rubber_band(self):
        self.rubber_band = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        self.rubber_band.setColor(QColor(255, 0, 0, 50))
        self.rubber_band.setFillColor(QColor(255, 0, 0, 30))
        self.rubber_band.setWidth(2)

    def canvasPressEvent(self, event):
        if event.button() == LeftButton:
            # Start drawing
            self.start_point = self.toMapCoordinates(event.pos())
            self.end_point = self.start_point
            self.is_drawing = True
            self.rubber_band.reset(Qgis.GeometryType.Polygon)

    def canvasMoveEvent(self, event):
        if self.is_drawing and self.start_point:
            # Update end point
            self.end_point = self.toMapCoordinates(event.pos())

            # Create rectangle
            rect = QgsRectangle(self.start_point, self.end_point)

            # Update rubber band
            self._update_rubber_band(rect)

    def canvasReleaseEvent(self, event):
        if event.button() == LeftButton and self.is_drawing:
            # Finish drawing
            self.end_point = self.toMapCoordinates(event.pos())
            self.is_drawing = False

            # Create final rectangle
            rect = QgsRectangle(self.start_point, self.end_point)

            # Emit signal with bbox (rubber band stays visible until next draw)
            if not rect.isEmpty():
                self.bboxDrawn.emit(rect)

    def _update_rubber_band(self, rect):
        if rect.isEmpty():
            return

        self.rubber_band.reset(Qgis.GeometryType.Polygon)

        # Create rectangle geometry
        points = [
            QgsPointXY(rect.xMinimum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMaximum()),
            QgsPointXY(rect.xMinimum(), rect.yMaximum()),
            QgsPointXY(rect.xMinimum(), rect.yMinimum())
        ]

        self.rubber_band.setToGeometry(QgsGeometry.fromPolygonXY([points]), None)

    def keyPressEvent(self, event):
        if event.key() == Key_Escape:
            # Cancel drawing
            self.is_drawing = False
            self.rubber_band.reset(Qgis.GeometryType.Polygon)

    def deactivate(self):
        if self.rubber_band:
            self.rubber_band.reset(Qgis.GeometryType.Polygon)
            self.rubber_band.hide()
        self.is_drawing = False
        super().deactivate()

    def cleanup(self):
        if self.rubber_band:
            self.rubber_band.reset(Qgis.GeometryType.Polygon)
            self.canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None

    def activate(self):
        super().activate()
        if not self.rubber_band:
            self._create_rubber_band()
