ENCODING = "utf-8"


class Document:
    """The file being edited. Knows nothing about the GUI so it can be reused and tested alone."""

    def __init__(self):
        self._path = None

    @property
    def path(self):
        return self._path

    @property
    def has_path(self):
        return self._path is not None

    def load(self, path):
        with open(path, encoding=ENCODING) as file:
            text = file.read()
        self._path = path
        return text

    def save(self, text, path=None):
        # Falling back to the stored path lets "Save" overwrite without asking again
        path = path or self._path
        with open(path, "w", encoding=ENCODING) as file:
            file.write(text)
        self._path = path
