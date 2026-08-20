"""
Central theme definitions for the app.
Palette:
  Sidebar / dark surface : #1B1F2A
  App background         : #F4F5F8
  Card surface           : #FFFFFF
  Primary accent         : #5B5FEF  (indigo - trust, "AI")
  Secondary accent       : #14B8A6  (teal - success / integrity-clear)
  Warning / flag         : #F59E0B  (amber - bias/integrity flags)
  Danger                 : #EF4444
  Text primary           : #1B1F2A
  Text muted             : #6B7280
"""

COLORS = {
    "sidebar": "#1B1F2A",
    "sidebar_hover": "#262B3A",
    "sidebar_active": "#5B5FEF",
    "bg": "#F4F5F8",
    "card": "#FFFFFF",
    "primary": "#5B5FEF",
    "primary_dark": "#4548C9",
    "secondary": "#14B8A6",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text": "#1B1F2A",
    "text_muted": "#6B7280",
    "border": "#E5E7EB",
}

STYLESHEET = f"""
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: 'Segoe UI';
    font-size: 13px;
}}

QWidget#Sidebar {{
    background-color: {COLORS['sidebar']};
}}

QLabel#BrandTitle {{
    color: #FFFFFF;
    font-size: 16px;
    font-weight: 600;
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

QLabel#PageTitle {{
    font-size: 22px;
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
    border-radius: 12px;
}}

QPushButton#PrimaryButton {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    border-radius: 8px;
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
    border: 1px solid {COLORS['primary']};
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton#SecondaryButton:hover {{
    background-color: #EEF0FF;
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
