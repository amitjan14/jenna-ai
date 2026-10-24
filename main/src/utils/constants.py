from main.src.utils.enums import ChunkingStrategy, PdfParser
import os

JENNA_MEMORY = os.getenv("JENNA_MEMORY_PATH", "jenna_memory")
JENNA_DOCUMENTS_PATH = "jenna_documents"
JENNA_DOCUMENT_CONFIGURATION = { "hnsw": { "space": "cosine" } }
CHUNKING_STRATEGY = os.getenv('JENNA_CHUNKING_STRATEGY',ChunkingStrategy.WORDS)
if CHUNKING_STRATEGY not in {ChunkingStrategy.WORDS,ChunkingStrategy.SECTIONS}:raise ValueError('Unknown chunking strategy')
DOCUMENT_CHUNKING_VERSION = 'sections-200-overlap-20-v2-lines' if CHUNKING_STRATEGY==ChunkingStrategy.SECTIONS else "words-200-overlap-40-v3-lines"
EMBEDDING_MODEL = os.getenv("JENNA_EMBEDDING_MODEL", "nomic-embed-text")
DEFAULT_CHAT_MODEL = "qwen3.5:9b"
DEFAULT_MCP_CONTEXT_TOKENS = 16384
CHAT_MODEL = os.getenv("JENNA_CHAT_MODEL", DEFAULT_CHAT_MODEL)
PDF_VISION_MODEL = os.getenv('JENNA_VISION_MODEL', CHAT_MODEL)
PDF_VISION_MODE = os.getenv('JENNA_PDF_VISION', 'auto').lower()
if PDF_VISION_MODE not in {'auto', 'always', 'off'}:
    raise ValueError('JENNA_PDF_VISION must be auto, always or off')
DOCUMENT_PARSER_VERSION = (f'layout-visual-v5:{PDF_VISION_MODE}:{PDF_VISION_MODEL}:ocr={os.getenv("JENNA_OCR", "true").lower()}'
                           if os.getenv('JENNA_PDF_PARSER',PdfParser.LAYOUT)==PdfParser.LAYOUT else 'pypdf-v1')
ROUTER_MODEL = os.getenv("JENNA_ROUTER_MODEL", CHAT_MODEL)
RERANKER_MODEL = os.getenv("JENNA_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
CANDIDATE_K = int(os.getenv("JENNA_CANDIDATE_K", "40"))
CONTEXT_K = int(os.getenv("JENNA_CONTEXT_K", "8"))
if CANDIDATE_K < 1 or not 1 <= CONTEXT_K <= CANDIDATE_K:
    raise ValueError("Require candidate_k >= context_k >= 1")
