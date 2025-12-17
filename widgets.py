from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt


class ChatBubble(QWidget):
    """自定义聊天气泡组件"""
    def __init__(self, role, text, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(10, 8, 10, 8)

        self.icon_label = QLabel("🔰")
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("""
            background-color: #e2e8f0; border-radius: 18px; color: #1e293b; font-weight: bold;
            font-family: "Microsoft YaHei", "SimSun", sans-serif; 
            font-size: 16px;
        """)

        self.msg_label = QLabel(text)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.msg_label.setStyleSheet("""
            QLabel {
                padding: 12px 18px;
                border-radius: 8px;
                font-size: 15px;
                line-height: 1.5;
                background-color: #f1f5f9;
                color: #333333;
                font-family: "Microsoft YaHei", "SimSun", sans-serif;
            }
        """)

        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.msg_label)
        self.setLayout(self.layout)

    def sizeHint(self):
        return self.layout.sizeHint()