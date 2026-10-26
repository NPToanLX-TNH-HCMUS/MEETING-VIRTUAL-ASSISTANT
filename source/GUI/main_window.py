import tkinter as tk
from tkinter import filedialog

from document.document import Document
from GUI.config import *

FILE_TYPES = [("Text", "*.txt"), ("Markdown", "*.md")]
DEFAULT_EXTENSION = ".txt"


class MainWindow(tk.Tk):
    def __init__(self, path=None):
        super().__init__()
        window_config = WindowConfig()
        self.title(window_config.title)
        self.geometry(window_config.size)

        self._document = Document()
        self._make_buttons()
        self._make_editor()

        if path:
            self._show_file(path)

    def _make_buttons(self):
        toolbar = tk.Frame(self)
        toolbar.pack()
        buttons = [
            (open_button, self._open_file),
            (save_button, self._save_file),
            (save_as_button, self._save_file_as),
        ]
        for button_config, command in buttons:
            tk.Button(toolbar,
                      text=button_config.text,
                      bg=button_config.bg,
                      padx=button_config.padx,
                      pady=button_config.pady,
                      command=command).pack(side="left")

    def _make_editor(self):
        editor_config = EditorConfig()
        self._editor = tk.Text(self, font=editor_config.font, wrap=editor_config.wrap)
        self._editor.pack(fill="both", expand=True)

    def _get_text(self):
        # "end-1c" drops the newline tkinter always appends, so saving doesn't grow the file
        return self._editor.get("1.0", "end-1c")

    def _show_file(self, path):
        text = self._document.load(path)
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", text)

    def _open_file(self):
        path = filedialog.askopenfilename(filetypes=FILE_TYPES)
        if path:
            self._show_file(path)

    def _save_file(self):
        if self._document.has_path:
            self._document.save(self._get_text())
        else:
            self._save_file_as()

    def _save_file_as(self):
        path = filedialog.asksaveasfilename(filetypes=FILE_TYPES,
                                            defaultextension=DEFAULT_EXTENSION)
        if path:
            self._document.save(self._get_text(), path)
