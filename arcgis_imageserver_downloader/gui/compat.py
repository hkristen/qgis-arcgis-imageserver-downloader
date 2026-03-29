"""Qt5/Qt6 enum compatibility shims."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QHeaderView, QDialogButtonBox, QDialog,
    QSizePolicy, QFrame,
)

try:
    # Qt6 scoped enums
    RightDockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea
    CrossCursor = Qt.CursorShape.CrossCursor
    LeftButton = Qt.MouseButton.LeftButton
    Key_Escape = Qt.Key.Key_Escape
    UserRole = Qt.ItemDataRole.UserRole
    AscendingOrder = Qt.SortOrder.AscendingOrder
    SelectRows = QAbstractItemView.SelectionBehavior.SelectRows
    SingleSelection = QAbstractItemView.SelectionMode.SingleSelection
    NoEditTriggers = QAbstractItemView.EditTrigger.NoEditTriggers
    HeaderStretch = QHeaderView.ResizeMode.Stretch
    ResizeToContents = QHeaderView.ResizeMode.ResizeToContents
    HeaderFixed = QHeaderView.ResizeMode.Fixed
    DialogOk = QDialogButtonBox.StandardButton.Ok
    DialogCancel = QDialogButtonBox.StandardButton.Cancel
    DialogAccepted = QDialog.DialogCode.Accepted
    SizePolicyPreferred = QSizePolicy.Policy.Preferred
    SizePolicyExpanding = QSizePolicy.Policy.Expanding
    FrameNoFrame = QFrame.Shape.NoFrame
except AttributeError:
    # Qt5 unscoped enums
    RightDockWidgetArea = Qt.RightDockWidgetArea
    CrossCursor = Qt.CrossCursor
    LeftButton = Qt.LeftButton
    Key_Escape = Qt.Key_Escape
    UserRole = Qt.UserRole
    AscendingOrder = Qt.AscendingOrder
    SelectRows = QAbstractItemView.SelectRows
    SingleSelection = QAbstractItemView.SingleSelection
    NoEditTriggers = QAbstractItemView.NoEditTriggers
    HeaderStretch = QHeaderView.Stretch
    ResizeToContents = QHeaderView.ResizeToContents
    HeaderFixed = QHeaderView.Fixed
    DialogOk = QDialogButtonBox.Ok
    DialogCancel = QDialogButtonBox.Cancel
    DialogAccepted = QDialog.Accepted
    SizePolicyPreferred = QSizePolicy.Preferred
    SizePolicyExpanding = QSizePolicy.Expanding
    FrameNoFrame = QFrame.NoFrame
