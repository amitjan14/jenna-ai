from main.src.engineering.tracing import timed_step
from pypdf import PdfReader
from pathlib import Path
import re
from main.src.utils import regex_constants as rx

BASE_DIR = Path(__file__).resolve().parent
INSTRUCTIONS_PATH = BASE_DIR / "../../instructions"

def normalize_key(key):
    if not isinstance(key, str):
        raise ValueError("Memory key must be text.")

    key = " ".join(key.casefold().split())

    if not key or len(key) > 80:
        raise ValueError("Use a memory key of 1–80 characters.")

    return key

@timed_step('Extract native PDF text')
def extract_pages(pdf_file):
    reader = PdfReader(pdf_file)

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page": page_number, "text": text})

    return pages


@timed_step('Split text into chunks')
def split_text(text, chunk_size=200, overlap=40):
    if (
            not isinstance(chunk_size, int)
            or not isinstance(overlap, int)
            or chunk_size <= 0
            or not 0 <= overlap < chunk_size
    ):
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size")

    words = list(re.finditer(rx.NONSPACE_WORD, text))
    chunks = []

    for start in range(0, len(words), chunk_size - overlap):
        end = min(start + chunk_size, len(words))
        chunk = text[words[start].start():words[end-1].end()]

        chunks.append(chunk)
        if end == len(words):
            break

    return chunks

def load_prompt(prompt_name: str, **kwargs) -> str:
    from main.src.utils.instructions import SHORT_PROMPTS, FOLDED_PROMPTS
    template = SHORT_PROMPTS.get(prompt_name)
    if template is None:
        prompt_path = INSTRUCTIONS_PATH / f"{prompt_name}.md"
        template = prompt_path.read_text(encoding="utf-8")
        if prompt_name in FOLDED_PROMPTS:
            template = " ".join(template.splitlines())
    return template.format(**kwargs) if kwargs else template

def make_result(
    answer,
    status,
    action,
    tools_used=None,
    results=None,
    support=None,
):
    return {
        "answer": answer,
        "status": status,
        "action": action,
        "tools_used": tools_used or [],
        "results": results or [],
        "support": support or [],
    }

