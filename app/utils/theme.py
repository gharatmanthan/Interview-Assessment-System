"""
Central theme definitions for the app.
Palette:
    Sidebar / dark surface : #102A43
    App background         : #F3F7F5
  Card surface           : #FFFFFF
    Primary accent         : #0F766E  (teal - trust and focus)
    Secondary accent       : #E76F51  (coral - action and attention)
  Warning / flag         : #F59E0B  (amber - bias/integrity flags)
  Danger                 : #EF4444
  Text primary           : #1B1F2A
  Text muted             : #6B7280
"""

COLORS = {
    "sidebar": "#102A43",
    "sidebar_hover": "#183B56",
    "sidebar_active": "#0F766E",
    "bg": "#F3F7F5",
    "card": "#FFFFFF",
    "primary": "#0F766E",
    "primary_dark": "#0B5F59",
    "secondary": "#E76F51",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text": "#102A43",
    "text_muted": "#627D98",
    "border": "#D9E2EC",
}

STYLESHEET = f"""
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: 'Aptos';
    font-size: 13px;
}}

QMainWindow, QWidget#LoginPage {{
    background-color: {COLORS['bg']};
}}

QWidget#Sidebar {{
    background-color: {COLORS['sidebar']};
}}

QLabel#BrandTitle {{
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
}}

QLabel#BrandSubtitle {{
    color: #8A90A6;
    font-size: 11px;
}}

QPushButton#NavButton {{
    background-color: transparent;
    color: #C7CBDA;
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    font-size: 13px;
}}

QPushButton#NavButton:hover {{
    background-color: {COLORS['sidebar_hover']};
    color: #FFFFFF;
}}

QPushButton#NavButtonActive {{
    background-color: {COLORS['sidebar_active']};
    color: #FFFFFF;
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
}}

QLineEdit, QTextEdit, QSpinBox, QListWidget {{
    background-color: #FFFFFF;
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
    padding: 9px 11px;
    selection-background-color: {COLORS['primary']};
}}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QListWidget:focus {{
    border: 2px solid {COLORS['primary']};
    padding: 8px 10px;
}}

QListWidget::item {{
    padding: 10px;
    border-bottom: 1px solid #EEF2F1;
}}

QListWidget::item:selected {{
    background-color: #DDF3EF;
    color: {COLORS['text']};
    border-left: 3px solid {COLORS['primary']};
}}

QPushButton {{
    min-height: 18px;
}}

QLabel#PageTitle {{
    font-size: 25px;
    font-weight: 700;
    color: {COLORS['text']};
}}

QLabel#PageSubtitle {{
    font-size: 13px;
    color: {COLORS['text_muted']};
}}

QWidget#Card {{
    background-color: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}

QGroupBox {{
    background-color: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    margin-top: 10px;
    padding: 18px 14px 14px 14px;
    font-weight: 700;
    color: {COLORS['text']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    background-color: {COLORS['bg']};
}}

QPushButton#PrimaryButton {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    border-radius: 7px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {COLORS['primary_dark']};
}}

QPushButton#SecondaryButton {{
    background-color: transparent;
    color: {COLORS['primary']};
    border: 1px solid #9CCBC5;
    border-radius: 7px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton#SecondaryButton:hover {{
    background-color: #E6F4F1;
}}

QPushButton:disabled {{
    background-color: #D9E2EC;
    color: #829AB1;
}}

QTextEdit {{
    line-height: 1.4em;
}}

QLabel#Badge-flagged {{
    background-color: #FEF3C7;
    color: #92400E;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#Badge-clear {{
    background-color: #D1FAE5;
    color: #065F46;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QScrollArea {{
    border: none;
}}
"""
