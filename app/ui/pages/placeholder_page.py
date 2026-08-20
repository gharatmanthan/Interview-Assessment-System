from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class PlaceholderPage(QWidget):
    def __init__(self, title, subtitle, body_text):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(16)

        header = QLabel(title)
        header.setObjectName("PageTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        layout.addWidget(header)
        layout.addWidget(sub)

        card = QLabel(body_text)
        card.setObjectName("Card")
        card.setWordWrap(True)
        card.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        card.setStyleSheet("padding: 24px; color: #6B7280; font-size: 13px;")
        layout.addWidget(card, stretch=1)
