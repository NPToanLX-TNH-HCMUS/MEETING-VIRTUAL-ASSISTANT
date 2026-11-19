import sys
from pathlib import Path

# Add project root to sys.path so 'src' can be imported when running script directly
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backend.document.markdown_converter import MarkDownConverter
from src.backend.text_chunking.semantic import SemanticChunker

INPUT_FILE = Path(__file__).resolve().parents[1] / "test_files" / "Agenda_3_trang.pdf"
OUTPUT_FILE = Path(__file__).resolve().parents[1] / "test_files" / "Agenda_3_trang.md"

Converter = MarkDownConverter()
chunker = SemanticChunker()

INPUT_FILE = Converter.convert(INPUT_FILE, OUTPUT_FILE)
text = chunker.read_file(INPUT_FILE)
chunks = chunker.chunk([text])

for i, chunk in enumerate(chunks):
    print(f"--- Chunk {i + 1} ---")
    print(chunk)
