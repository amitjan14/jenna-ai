"""Local PDF image reading and verification against saved original page pixels."""
import hashlib
import json
import re

import pymupdf
from jsonschema import validate, ValidationError

from main.src.engineering.runtime import checkpoint
from main.src.memory.document_memory import load_document_pdf
from main.src.tools.llm import get_client
from main.src.utils.common_utils import load_prompt
from main.src.utils.constants import PDF_VISION_MODEL
from main.src.utils.enums import PromptName, Role
from main.src.utils.schemas import PDF_VISUAL_VERIFY_SCHEMA
from main.src.utils import instructions, regex_constants as rx


def page_image(page, max_edge=2000):
    regions = [pymupdf.Rect(block[:4]) for block in page.get_text('blocks')
               if block[6] == 0 and block[4].strip()]
    regions += [pymupdf.Rect(item['bbox']) for item in page.get_image_info()]
    regions += [drawing['rect'] for drawing in page.get_drawings()]
    regions += [annotation.rect for annotation in page.annots() or []]
    clip = pymupdf.Rect()
    for region in regions:
        if page.rotation:
            # Extraction boxes use unrotated coordinates; pixmap clipping uses
            # the displayed page coordinates, including the PDF /Rotate value.
            region = region * page.rotation_matrix
        # Horizontal/vertical pen strokes have zero-height/width bounding boxes
        # but are visible evidence; do not discard them as empty rectangles.
        if region.width >= 0 and region.height >= 0 and (region.width or region.height):
            clip |= pymupdf.Rect(region.x0-.25, region.y0-.25, region.x1+.25, region.y1+.25)
    if clip.is_empty:
        clip = page.rect
    else:
        clip = pymupdf.Rect(clip.x0-12, clip.y0-12, clip.x1+12, clip.y1+12) & page.rect
    # Remove only empty page margins. This preserves all source regions while
    # giving small handwriting more pixels and avoiding large blank image inputs.
    scale = min(200 / 72, max_edge / max(clip.width, clip.height))
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False).tobytes('png')


def read_visual_page(page):
    checkpoint('reading_pdf_image', page=page.number + 1, model=PDF_VISION_MODEL)
    try:
        response = get_client(timeout=180).chat(
            model=PDF_VISION_MODEL, think=False,
            options={'temperature': 0, 'num_predict': 4096, 'num_ctx': 16384},
            messages=[{'role': Role.SYSTEM, 'content': load_prompt(PromptName.PDF_VISION)},
                      {'role': Role.USER, 'content': instructions.PDF_VISION_REQUEST,
                       'images': [page_image(page)]}],
        )
        if response.get('done_reason') == 'length':
            raise ValueError('Visual page reading was truncated; no partial transcription was indexed.')
        text = response['message']['content']
        if not isinstance(text, str) or len(text) > 24000:
            raise ValueError('Invalid or oversized visual transcription.')
    except (KeyError, TypeError) as error:
        raise ValueError('The local vision model returned an invalid PDF transcription. Please retry.') from error
    return {'text': text.strip(), 'has_uncertainty': bool(re.search(rx.VISUAL_UNCERTAINTY, text, re.I))}


def verify_visual_sources(results, support):
    pages = {}
    for item in support:
        source = results[item['source_id']]
        if source.get('vision_used'):
            key = (source['filename'], source['page'], source.get('content_hash'))
            pages.setdefault(key, []).append(item['quote'])
    for (filename, number, content_hash), quotes in pages.items():
        raw = load_document_pdf(filename)
        if not raw or not content_hash or hashlib.sha256(raw).hexdigest() != content_hash:
            return {'supported': False, 'reason': 'The original visual source changed or is unavailable. Search the document again.'}
        with pymupdf.open(stream=raw, filetype='pdf') as document:
            if type(number) is not int or not 1 <= number <= len(document):
                return {'supported': False, 'reason': 'The cited PDF page is unavailable.'}
            checkpoint('verifying_pdf_image', page=number, model=PDF_VISION_MODEL)
            response = get_client(timeout=180).chat(
                model=PDF_VISION_MODEL, think=False, format=PDF_VISUAL_VERIFY_SCHEMA,
                options={'temperature': 0, 'num_predict': 512, 'num_ctx': 16384},
                messages=[{'role': Role.SYSTEM, 'content': load_prompt(PromptName.PDF_VISUAL_VERIFY)},
                          {'role': Role.USER, 'content': json.dumps({'quotations': list(dict.fromkeys(quotes))}),
                           'images': [page_image(document[number - 1])]}],
            )
        try:
            verdict = json.loads(response['message']['content'])
            validate(verdict, PDF_VISUAL_VERIFY_SCHEMA)
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
            return {'supported': False, 'reason': 'Invalid visual verification response.'}
        if not verdict['supported']:
            return verdict
    return {'supported': True, 'reason': ''}
