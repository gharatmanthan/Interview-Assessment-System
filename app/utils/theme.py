"""Application-wide visual language for InterviewIQ."""

COLORS = {
    "ink": "#172033", "muted": "#667085", "paper": "#F6F8FC",
    "surface": "#FFFFFF", "line": "#E3E8F2", "nav": "#101828",
    "nav_hover": "#1D2939", "primary": "#4F46E5", "primary_dark": "#4338CA",
    "teal": "#0F766E", "danger": "#B42318",
}

STYLESHEET = f"""
* {{ font-family: 'Segoe UI', 'Aptos', sans-serif; font-size: 13px; }}
QWidget {{ background: {COLORS['paper']}; color: {COLORS['ink']}; }}
QMainWindow {{ background: {COLORS['paper']}; }}
QLabel {{ background: transparent; }}

QWidget#Sidebar {{ background: {COLORS['nav']}; }}
QLabel#BrandTitle {{ color: #FFFFFF; font-size: 22px; font-weight: 700; letter-spacing: 0.2px; }}
QLabel#BrandSubtitle {{ color: #98A2B3; font-size: 11px; }}
QLabel#RoleBadge {{ color: #D9E4FF; background: #1D2939; border: 1px solid #344054; border-radius: 8px; padding: 9px 10px; font-size: 12px; font-weight: 600; }}
QPushButton#NavButton, QPushButton#NavButtonActive {{ text-align: left; border: 0; border-radius: 8px; padding: 11px 12px; font-size: 13px; }}
QPushButton#NavButton {{ color: #C5CEDB; background: transparent; }}
QPushButton#NavButton:hover {{ color: #FFFFFF; background: {COLORS['nav_hover']}; }}
QPushButton#NavButtonActive {{ color: #FFFFFF; background: #3730A3; font-weight: 700; }}

QLabel#PageTitle {{ color: {COLORS['ink']}; font-size: 28px; font-weight: 700; letter-spacing: -0.4px; }}
QLabel#PageSubtitle {{ color: {COLORS['muted']}; font-size: 13px; }}
QWidget#Card, QWidget#StatCard, QGroupBox {{ background: {COLORS['surface']}; border: 1px solid {COLORS['line']}; border-radius: 12px; }}
QGroupBox {{ margin-top: 13px; padding: 22px 16px 16px 16px; font-size: 13px; font-weight: 700; color: #344054; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; background: #FFFFFF; }}

QLineEdit, QTextEdit, QSpinBox, QListWidget {{ background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 8px; padding: 10px 11px; selection-background-color: #E0E7FF; selection-color: {COLORS['ink']}; }}
QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QListWidget:hover {{ border-color: #AAB4C5; }}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QListWidget:focus {{ border: 2px solid #818CF8; padding: 9px 10px; }}
QLineEdit::placeholder, QTextEdit::placeholder {{ color: #98A2B3; }}
QTextEdit {{ line-height: 1.45; }}
QListWidget::item {{ border: 0; border-bottom: 1px solid #EEF2F6; padding: 11px 10px; }}
QListWidget::item:hover {{ background: #F5F7FF; }}
QListWidget::item:selected {{ background: #EEF2FF; color: #3730A3; border-left: 3px solid {COLORS['primary']}; font-weight: 600; }}

QPushButton {{ border-radius: 8px; padding: 10px 16px; font-weight: 600; }}
QPushButton#PrimaryButton, QPushButton#ApproveButton {{ background: {COLORS['primary']}; color: #FFFFFF; border: 1px solid {COLORS['primary']}; }}
QPushButton#PrimaryButton:hover, QPushButton#ApproveButton:hover {{ background: {COLORS['primary_dark']}; border-color: {COLORS['primary_dark']}; }}
QPushButton#PrimaryButton:pressed, QPushButton#ApproveButton:pressed {{ background: #3730A3; }}
QPushButton#SecondaryButton, QPushButton#SkipButton {{ background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; }}
QPushButton#SecondaryButton:hover, QPushButton#SkipButton:hover {{ background: #F8FAFC; border-color: #98A2B3; }}
QPushButton:disabled {{ background: #EAECF0; color: #98A2B3; border-color: #EAECF0; }}

QWidget#LoginPage {{ background: #101828; }}
QWidget#LoginPanel {{ background: #FFFFFF; border: 1px solid #EAECF0; border-radius: 16px; }}
QLabel#LoginKicker {{ color: {COLORS['primary']}; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }}
QLabel#LoginTitle {{ color: {COLORS['ink']}; font-size: 30px; font-weight: 700; letter-spacing: -0.5px; }}
QLabel#LoginCopy {{ color: {COLORS['muted']}; font-size: 13px; }}
QLabel#LoginMark {{ color: #FFFFFF; background: {COLORS['primary']}; border-radius: 12px; padding: 10px 14px; font-size: 25px; font-weight: 800; }}
QLabel#LoginBrand {{ color: #FFFFFF; font-size: 26px; font-weight: 700; }}
QLabel#LoginBrandCopy {{ color: #B8C3D3; font-size: 14px; line-height: 1.45; }}
QLabel#LoginStatus {{ color: {COLORS['muted']}; padding: 4px 0; }}
QPushButton#RoleButton {{ color: {COLORS['muted']}; background: #F8FAFC; border: 1px solid #E4E7EC; border-radius: 8px; padding: 10px; font-weight: 600; }}
QPushButton#RoleButton:checked {{ color: #3730A3; background: #EEF2FF; border-color: #818CF8; }}

QLabel#StatValue {{ font-size: 30px; font-weight: 700; color: {COLORS['primary']}; }}
QWidget#StatCard {{ border-top: 3px solid #818CF8; }}
QLabel#Badge-flagged, QLabel#StatusPending {{ background: #FFF7E6; color: #9A6700; border: 1px solid #FCE7B2; border-radius: 999px; padding: 4px 9px; font-weight: 600; }}
QLabel#Badge-clear, QLabel#StatusPass {{ background: #ECFDF3; color: #067647; border: 1px solid #ABEFC6; border-radius: 999px; padding: 4px 9px; font-weight: 600; }}
QLabel#StatusFail {{ background: #FEF3F2; color: {COLORS['danger']}; border: 1px solid #FECDCA; border-radius: 999px; padding: 4px 9px; font-weight: 600; }}
QLabel#CategoryTag {{ color: #4338CA; background: #EEF2FF; border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 700; }}
QLabel#StepperDone, QLabel#StepperActive, QLabel#StepperPending {{ border-radius: 999px; padding: 7px 12px; font-weight: 700; }}
QLabel#StepperDone {{ color: #067647; background: #ECFDF3; }}
QLabel#StepperActive {{ color: #3730A3; background: #EEF2FF; }}
QLabel#StepperPending {{ color: #667085; background: #F2F4F7; }}
QWidget#PendingQuestionPanel {{ background: #FFF9EB; border: 1px solid #F7D483; border-radius: 12px; }}
QLabel#PendingQuestionText {{ color: #7A4B00; font-size: 15px; font-weight: 600; }}
QLabel#WaitingLabel {{ color: {COLORS['muted']}; font-style: italic; }}

QSlider::groove:horizontal {{ height: 5px; background: #E4E7EC; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {COLORS['primary']}; border: 2px solid #FFFFFF; width: 16px; height: 16px; margin: -6px 0; border-radius: 9px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: #C8D0DC; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #98A2B3; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollArea {{ border: 0; background: transparent; }}
QToolTip {{ background: #101828; color: #FFFFFF; border: 0; padding: 7px; border-radius: 5px; }}
"""
