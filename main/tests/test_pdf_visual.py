"""PDF visual extraction and original-pixel verification contracts."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pymupdf
from PIL import Image, ImageDraw

from main.src.rag import pdf_vision, search_utils


def image_pdf(native=False):
    image = Image.new('RGB', (900, 400), 'white')
    ImageDraw.Draw(image).text((40, 40), 'Meeting at 10 AM', fill='black')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with pymupdf.open() as document:
        page = document.new_page()
        if native:
            page.insert_text((40, 40), 'COMPUTERIZED NOTES')
        page.insert_image(pymupdf.Rect(40, 90, 550, 320), stream=stream.getvalue())
        return document.tobytes()


class VisualExtractionTests(unittest.TestCase):
    def test_chunking_preserves_handwritten_field_boundaries(self):
        from main.src.utils.common_utils import split_text
        source = 'Lab notes\nSample count: 36\nLearning rate: 0.04\nOwner: Mira Patel'
        self.assertEqual(split_text(source), [source])
        chunks = split_text(source, chunk_size=6, overlap=2)
        self.assertTrue(any('\n' in chunk for chunk in chunks))
        self.assertEqual(chunks[0].split()[-2:], chunks[1].split()[:2])

    def test_counts_inside_notes_are_not_document_inventory(self):
        from main.src.agent.agent_utils import is_document_inventory_request
        for question in ['From handwritten_notes.pdf, what is the sample count?',
                         'How many trees does the model use in my PDF?',
                         'List programming languages in my uploaded PDF.']:
            with self.subTest(question=question):
                self.assertFalse(is_document_inventory_request(question))
        for question in ['List my uploaded documents.', 'How many PDFs do I have?',
                         'Count the indexed files.', 'What documents have I uploaded?']:
            with self.subTest(question=question):
                self.assertTrue(is_document_inventory_request(question))

    def test_typed_notes_keep_native_fast_path(self):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), 'Typed notes: Python and Java.')
            raw = document.tobytes()
        with patch.object(search_utils, 'read_visual_page') as vision:
            pages = search_utils.layout_pages(io.BytesIO(raw))
        vision.assert_not_called()
        self.assertIn('Python and Java', pages[0]['text'])
        self.assertFalse(pages[0]['vision'])

    def test_native_text_underlines_do_not_force_visual_reading(self):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), 'Typed notes with underlined headings.')
            for y in [60, 100, 140, 180]:
                page.draw_line((40, y), (500, y))
            raw = document.tobytes()
        with patch.object(search_utils, 'read_visual_page') as vision:
            self.assertFalse(search_utils.layout_pages(io.BytesIO(raw))[0]['vision'])
        vision.assert_not_called()

    def test_diagram_outside_table_is_not_skipped(self):
        with pymupdf.open() as document:
            page = document.new_page()
            for y in [60, 100, 140]:
                page.draw_line((40, y), (300, y))
            for x in [40, 170, 300]:
                page.draw_line((x, 60), (x, 140))
            for x, y, value in [(50, 85, 'Name'), (180, 85, 'Value'), (50, 125, 'Cap'), (180, 125, '35')]:
                page.insert_text((x, y), value)
            for x in [40, 220, 400]:
                page.draw_rect(pymupdf.Rect(x, 300, x+120, 360))
            raw = document.tobytes()
        with patch.object(search_utils, 'read_visual_page', return_value={
                'text': 'Diagram: Sensor connects to Processor and Display.', 'has_uncertainty': False}) as vision:
            page = search_utils.layout_pages(io.BytesIO(raw))[0]
        self.assertGreater(page['table_count'], 0)
        self.assertTrue(page['vision'])
        vision.assert_called_once()

    def test_mixed_typed_page_does_not_skip_its_image(self):
        with patch.object(search_utils, 'read_visual_page', return_value={
                'text': 'Handwritten note: Meeting at 10 AM.', 'has_uncertainty': False}) as vision:
            pages = search_utils.layout_pages(io.BytesIO(image_pdf(native=True)))
        vision.assert_called_once()
        self.assertIn('COMPUTERIZED NOTES', pages[0]['text'])
        self.assertIn('10 AM', pages[0]['text'])
        self.assertEqual(pages[0]['extraction_method'], 'native+vision')

    def test_ocr_retains_readable_lines_omitted_by_visual_transcription(self):
        from evaluation.run_visual_documents import make_document
        with patch.object(search_utils, 'read_visual_page', return_value={
                'text': 'MACHINE LEARNING NOTES', 'has_uncertainty': False}):
            page = search_utils.layout_pages(io.BytesIO(make_document('printed_scan.pdf')))[0]
        self.assertIn('87', page['text'])
        self.assertIn('120', page['text'])
        self.assertTrue(page['vision'])

    def test_image_only_notes_use_vision(self):
        with patch.object(search_utils, 'read_visual_page', return_value={
                'text': 'Meeting at 10 AM.', 'has_uncertainty': False}):
            page = search_utils.layout_pages(io.BytesIO(image_pdf()))[0]
        self.assertTrue(page['ocr'])
        self.assertTrue(page['vision'])
        self.assertEqual(page['extraction_method'], 'vision')

    def test_handwritten_ink_annotation_triggers_vision_on_typed_page(self):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), 'Typed notes')
            page.add_ink_annot([[(50, 100), (70, 120), (90, 100)]])
            raw = document.tobytes()
        with patch.object(search_utils, 'read_visual_page', return_value={
                'text': '[illegible]', 'has_uncertainty': True}) as vision:
            page = search_utils.layout_pages(io.BytesIO(raw))[0]
        vision.assert_called_once()
        self.assertTrue(page['visual_uncertainty'])

    def test_blank_page_does_not_invent_visual_content(self):
        with pymupdf.open() as document:
            document.new_page()
            raw = document.tobytes()
        with patch.object(search_utils, 'read_visual_page') as vision:
            self.assertEqual(search_utils.layout_pages(io.BytesIO(raw)), [])
        vision.assert_not_called()

    def test_page_render_crops_blank_margins_without_losing_typed_or_image_regions(self):
        with pymupdf.open(stream=image_pdf(native=True), filetype='pdf') as document:
            rendered = Image.open(io.BytesIO(pdf_vision.page_image(document[0])))
        # The full A4-like page would be 2000px tall. Both the typed heading
        # and screenshot remain inside the combined content bounds.
        self.assertLess(rendered.height, 1600)
        self.assertGreater(rendered.width, 1300)

    def test_page_render_preserves_thin_pen_strokes_outside_text_bounds(self):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((250, 60), 'Notes')
            page.draw_line((40, 120), (550, 120))
            rendered = Image.open(io.BytesIO(pdf_vision.page_image(page)))
        self.assertGreater(rendered.width, 1400)

    def test_pdf_rotation_metadata_preserves_all_image_bounds(self):
        sizes = {}
        with pymupdf.open(stream=image_pdf(), filetype='pdf') as document:
            page = document[0]
            for angle in [0, 90, 180, 270]:
                page.set_rotation(angle)
                rendered = Image.open(io.BytesIO(pdf_vision.page_image(page))).convert('L')
                sizes[angle] = rendered.size
                self.assertLess(rendered.getextrema()[0], 20)
        for angle in [90, 180, 270]:
            expected = sizes[0][::-1] if angle in {90, 270} else sizes[0]
            self.assertLessEqual(abs(sizes[angle][0]-expected[0]), 2)
            self.assertLessEqual(abs(sizes[angle][1]-expected[1]), 2)

    def test_focused_views_include_embedded_image_without_losing_page_context(self):
        with pymupdf.open(stream=image_pdf(native=True), filetype='pdf') as document:
            images = pdf_vision.visual_page_images(document[0])
        self.assertEqual(len(images), 2)
        full, detail = [Image.open(io.BytesIO(raw)) for raw in images]
        self.assertLess(detail.height, full.height)
        self.assertGreater(detail.width / detail.height, 2)

    def test_image_only_page_does_not_duplicate_image_inputs(self):
        with pymupdf.open(stream=image_pdf(), filetype='pdf') as document:
            self.assertEqual(len(pdf_vision.visual_page_images(document[0])), 1)

    def test_focused_views_respect_rotation_and_bound_image_count(self):
        with pymupdf.open(stream=image_pdf(native=True), filetype='pdf') as document:
            page = document[0]
            normal = Image.open(io.BytesIO(pdf_vision.visual_page_images(page)[1])).size
            page.set_rotation(90)
            rotated = Image.open(io.BytesIO(pdf_vision.visual_page_images(page)[1])).size
            self.assertLessEqual(abs(normal[0] - rotated[1]), 2)
            self.assertLessEqual(abs(normal[1] - rotated[0]), 2)
            self.assertEqual(len(pdf_vision.visual_page_images(page, max_details=0)), 1)

    def test_small_logos_do_not_add_focused_views(self):
        with pymupdf.open(stream=image_pdf(), filetype='pdf') as source, pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), 'Native text with small logo')
            page.insert_image(pymupdf.Rect(40, 80, 80, 100),
                              stream=source.extract_image(source[0].get_images()[0][0])['image'])
            self.assertEqual(len(pdf_vision.visual_page_images(page)), 1)

    def test_ocr_opt_out_is_respected(self):
        with patch.object(search_utils, 'read_visual_page') as vision:
            pages = search_utils.layout_pages(io.BytesIO(image_pdf(native=True)), ocr=False)
        vision.assert_not_called()
        self.assertIn('COMPUTERIZED NOTES', pages[0]['text'])
        self.assertFalse(pages[0]['ocr'])

    def test_visual_reading_rejects_truncated_or_malformed_output(self):
        client = Mock()
        with pymupdf.open(stream=image_pdf(), filetype='pdf') as document:
            for response in [
                {'message': {'content': '{}'}, 'done_reason': 'length'},
                {'message': {'content': None}},
                {'message': {'content': ['not a transcription']}},
            ]:
                client.chat.return_value = response
                with self.subTest(response=response), patch.object(pdf_vision, 'get_client', return_value=client):
                    with self.assertRaises(ValueError):
                        pdf_vision.read_visual_page(document[0])

    def test_visual_reading_sends_actual_image_and_keeps_uncertainty(self):
        client = Mock()
        client.chat.return_value = {'message': {'content': 'Budget: [illegible]\nVisual observations: A connects to B.'}}
        with pymupdf.open(stream=image_pdf(), filetype='pdf') as document, \
             patch.object(pdf_vision, 'get_client', return_value=client):
            result = pdf_vision.read_visual_page(document[0])
        self.assertTrue(result['has_uncertainty'])
        self.assertIn('[illegible]', result['text'])
        self.assertTrue(client.chat.call_args.kwargs['messages'][-1]['images'][0].startswith(b'\x89PNG'))


class VisualVerificationTests(unittest.TestCase):
    def setUp(self):
        self.raw = image_pdf()
        self.source = {'filename': 'notes.pdf', 'page': 1, 'vision_used': True,
                       'content_hash': hashlib.sha256(self.raw).hexdigest(), 'text': 'Meeting at 10 AM.'}
        self.support = [{'source_id': 0, 'quote': 'Meeting at 10 AM.'}]

    def test_original_pixels_are_checked_once_per_page(self):
        client = Mock()
        client.chat.return_value = {'message': {'content': json.dumps({'supported': True, 'reason': 'Visible'})}}
        with patch.object(pdf_vision, 'load_document_pdf', return_value=self.raw), \
             patch.object(pdf_vision, 'get_client', return_value=client):
            verdict = pdf_vision.verify_visual_sources([self.source], self.support * 2)
        self.assertTrue(verdict['supported'])
        client.chat.assert_called_once()
        message = client.chat.call_args.kwargs['messages'][-1]
        self.assertEqual(json.loads(message['content'])['quotations'], ['Meeting at 10 AM.'])
        self.assertTrue(message['images'][0].startswith(b'\x89PNG'))

    def test_visual_verifier_gets_same_focused_views_for_mixed_page(self):
        raw = image_pdf(native=True)
        source = {**self.source, 'content_hash': hashlib.sha256(raw).hexdigest()}
        client = Mock()
        client.chat.return_value = {'message': {'content': json.dumps({'supported': True, 'reason': 'Visible'})}}
        with patch.object(pdf_vision, 'load_document_pdf', return_value=raw), \
             patch.object(pdf_vision, 'get_client', return_value=client):
            verdict = pdf_vision.verify_visual_sources([source], self.support)
        self.assertTrue(verdict['supported'])
        self.assertEqual(len(client.chat.call_args.kwargs['messages'][-1]['images']), 2)

    def test_changed_original_pdf_is_not_accepted(self):
        with patch.object(pdf_vision, 'load_document_pdf', return_value=b'different PDF'), \
             patch.object(pdf_vision, 'get_client') as client:
            verdict = pdf_vision.verify_visual_sources([self.source], self.support)
        self.assertFalse(verdict['supported'])
        client.assert_not_called()

    def test_visual_verifier_refusal_or_bad_json_blocks_answer(self):
        for response in [{'message': {'content': 'bad JSON'}},
                         {'message': {'content': json.dumps({'supported': False, 'reason': 'Digit is illegible'})}}]:
            client = Mock()
            client.chat.return_value = response
            with self.subTest(response=response), \
                 patch.object(pdf_vision, 'load_document_pdf', return_value=self.raw), \
                 patch.object(pdf_vision, 'get_client', return_value=client):
                self.assertFalse(pdf_vision.verify_visual_sources([self.source], self.support)['supported'])

    def test_native_text_does_not_require_image_verification(self):
        source = {**self.source, 'vision_used': False}
        with patch.object(pdf_vision, 'load_document_pdf') as read:
            self.assertTrue(pdf_vision.verify_visual_sources([source], self.support)['supported'])
        read.assert_not_called()

    def test_visual_provenance_survives_rank_fusion(self):
        candidate = {**self.source, 'chunk_index': 0, 'similarity': .9}
        result = search_utils.reciprocal_rank_fusion([[candidate], [candidate]])[0]
        self.assertTrue(result['vision_used'])
        self.assertEqual(result['content_hash'], self.source['content_hash'])


class VisualIndexTests(unittest.TestCase):
    def test_uncertainty_and_visual_provenance_survive_index_and_retrieval(self):
        import chromadb
        from main.src.rag import document_store as store
        from main.src.memory import memory_service
        with tempfile.TemporaryDirectory() as folder:
            collection = chromadb.PersistentClient(path=str(Path(folder)/'vectors')).get_or_create_collection('visual-test')
            with patch.object(store, 'collection', collection), \
                 patch.object(store, 'create_embeddings', side_effect=lambda chunks: [[1., 0.] for _ in chunks]), \
                 patch.object(store, 'create_embedding', return_value=[1., 0.]), \
                 patch.object(memory_service, 'DB_PATH', Path(folder)/'memory.sqlite3'), \
                 patch.object(search_utils, 'read_visual_page', return_value={'text': 'Meeting: [illegible]', 'has_uncertainty': True}):
                result = store.index_and_store_document(image_pdf(), 'notes.pdf')
                self.assertEqual(result['uncertain_pages'], [1])
                chunks = store.search_documents('Meeting', threshold=-1, rerank=False, hybrid=True)
                self.assertTrue(chunks[0]['vision_used'])
                self.assertTrue(chunks[0]['visual_uncertainty'])
                self.assertEqual(chunks[0]['extraction_method'], 'vision')


class VisualContentTests(unittest.TestCase):
    def source(self, **changes):
        return {'filename': 'notes.pdf', 'page': 2, 'chunk_index': 0,
                'vision_used': True, 'extraction_method': 'vision',
                'text': 'Please bring sketchbooks.\nClass starts at 9 AM.\nRIVER_SKY'
                        '\n\nAdditional OCR reading (verify against the original image):\ngarbage',
                **changes}

    def test_named_image_content_copies_body_and_excludes_unverified_ocr(self):
        from main.src.rag.rag_service import visual_content_passage
        source = self.source()
        support = visual_content_passage("what does river sky image's data", [source])
        self.assertIn('sketchbooks', support[0]['quote'])
        self.assertIn('9 AM', support[0]['quote'])
        self.assertNotIn('garbage', support[0]['quote'])
        self.assertIn(support[0]['quote'], source['text'])

    def test_label_question_or_unknown_handle_does_not_read_whole_page(self):
        from main.src.rag.rag_service import visual_content_passage
        for question in ['What does the signature say?', 'What is cloud light image content?']:
            self.assertIsNone(visual_content_passage(question, [self.source()]))

    def test_named_writer_message_uses_body_not_only_signature(self):
        from main.src.rag.rag_service import visual_content_passage
        support = visual_content_passage('What does river sky say in notes.pdf?', [self.source()])
        self.assertIn('Please bring sketchbooks.', support[0]['quote'])

    def test_verified_transcription_is_returned_without_fact_selection(self):
        from main.src.rag import rag_service as rag
        with patch.object(rag, 'verify_document_answer', return_value={
                'supported': True, 'complete': True, 'reason': ''}) as verify, \
             patch.object(rag.get_client(), 'chat') as select:
            result = rag.generate_document_answer('What does river sky say?', [self.source()])
        verify.assert_called_once()
        select.assert_not_called()
        self.assertTrue(result['verbatim_transcription'])
        self.assertIn('sketchbooks', result['answer'])

    def test_ambiguous_long_uncertain_or_partial_pages_use_normal_selection(self):
        from main.src.rag.rag_service import visual_content_passage
        question = 'What is river sky image content?'
        for sources in [[self.source(), self.source(page=3)],
                        [self.source(text=('word ' * 200) + 'RIVER_SKY')],
                        [self.source(chunk_index=1)],
                        [self.source(visual_uncertainty=True)]]:
            self.assertIsNone(visual_content_passage(question, sources))

    def test_readable_transcription_still_requires_verification(self):
        from main.src.rag import rag_service as rag
        refusal = {'message': {'content': json.dumps({'parts': [
            {'part_id': 0, 'answerable': False, 'support': []}]})}}
        with patch.object(rag, 'verify_document_answer', return_value={
                'supported': False, 'complete': False, 'reason': 'Image does not support text.'}) as verify, \
             patch.object(rag.get_client(), 'chat', return_value=refusal):
            result = rag.generate_document_answer('What is river sky image content?', [self.source()])
        verify.assert_called_once()
        self.assertFalse(result['answerable'])


if __name__ == '__main__':
    unittest.main()
