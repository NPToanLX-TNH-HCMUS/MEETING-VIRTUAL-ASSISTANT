from dataclasses import dataclass


@dataclass
class WindowConfig:
    title: str = "Meeting Virtual Assistant"
    size: str = "800x600"


@dataclass
class ButtonConfig:
    text: str
    bg: str = "#e0e0e0"
    padx: int = 12
    pady: int = 6


@dataclass
class EditorConfig:
    font: tuple = ("Menlo", 13)
    wrap: str = "word"

#Text editor
open_button = ButtonConfig(text="Open", bg="#cfe3ff")
save_button = ButtonConfig(text="Save", bg="#9be58f")
save_as_button = ButtonConfig(text="Save As", bg="#f5e44c")

#Audio handler
record_button = ButtonConfig(text="Record", bg="#ff9b9b")
stop_button = ButtonConfig(text="Stop", bg="#f5e44c")
play_button = ButtonConfig(text="Play", bg="#9be58f")
