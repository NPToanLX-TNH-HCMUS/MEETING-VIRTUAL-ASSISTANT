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

    def export_pdf(self, output_path):
        """Export current document content to a standard PDF file."""
        from pathlib import Path
        out = Path(output_path)
        content = ""
        if self._path and Path(self._path).exists():
            with open(self._path, encoding=ENCODING) as file:
                content = file.read()

        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font('Helvetica', size=11)
            for line in content.splitlines():
                clean_line = line.encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 6, text=clean_line)
            pdf.output(str(out))
            return out
        except Exception:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 50), content)
            doc.save(str(out))
            return out

    def export_to_pdf(self, output_path):
        return self.export_pdf(output_path)
