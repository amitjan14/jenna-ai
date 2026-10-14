"""Regression cases reproduced during the project review."""
import hashlib
import io
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from main.src.memory import memory_service
from main.src.memory.chat_memory import create_chat, save_message, list_chats, clear_chat_history, load_messages


class ChatRecencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(memory_service, 'DB_PATH', Path(self.temp.name)/'memory.sqlite3')
        self.db.start()

    def tearDown(self):
        self.db.stop()
        self.temp.cleanup()

    def test_activity_reorders_existing_chats_with_real_timestamps(self):
        older, newer = create_chat(), create_chat()
        with patch('main.src.memory.chat_memory.datetime') as clock:
            clock.now.return_value = datetime(2040, 1, 1, 12, 0, 0, 100, tzinfo=timezone.utc)
            save_message(newer, {'role':'user', 'content':'Second chat'})
            clock.now.return_value = datetime(2040, 1, 1, 12, 0, 0, 200, tzinfo=timezone.utc)
            save_message(older, {'role':'user', 'content':'Latest activity'})
        self.assertEqual([row['id'] for row in list_chats()], [older, newer])
        with memory_service.database() as db:
            values = db.execute('SELECT updated_at FROM chats').fetchall()
        for (value,) in values:
            self.assertEqual(datetime.fromisoformat(value).year, 2040)

    def test_clearing_chat_updates_recency_and_removes_messages(self):
        older, newer = create_chat(), create_chat()
        save_message(older, {'role':'user', 'content':'Remove this'})
        with patch('main.src.memory.chat_memory.datetime') as clock:
            clock.now.return_value = datetime(2040, 1, 1, tzinfo=timezone.utc)
            clear_chat_history(older)
        self.assertEqual(list_chats()[0], {'id':older, 'title':'New chat'})
        self.assertEqual(load_messages(older), [])

    def test_legacy_literal_timestamps_recover_from_messages_or_creation(self):
        populated, empty = create_chat(), create_chat()
        save_message(populated, {'role':'user', 'content':'Preserve this'})
        with sqlite3.connect(memory_service.DB_PATH) as db:
            db.execute('UPDATE chat_messages SET created_at=? WHERE chat_id=?', ('2020-02-03 04:05:06', populated))
            db.execute('UPDATE chats SET created_at=? WHERE id=?', ('2019-01-01 00:00:00', empty))
            db.execute('UPDATE chats SET updated_at=?', ("strftime('%Y-%m-%d %H:%M:%f', 'now')",))
        with memory_service.database() as db:
            times = dict(db.execute('SELECT id, updated_at FROM chats'))
        self.assertEqual(times[populated], '2020-02-03 04:05:06')
        self.assertEqual(times[empty], '2019-01-01 00:00:00')
        self.assertEqual(load_messages(populated)[0]['content'], 'Preserve this')


class IndexRollbackTests(unittest.TestCase):
    def setUp(self):
        import chromadb
        from main.src.rag import document_store
        self.store = document_store
        self.temp = tempfile.TemporaryDirectory()
        self.client = chromadb.PersistentClient(path=str(Path(self.temp.name)/'index'))
        self.collection = self.client.get_or_create_collection('review-regression')
        self.proxy = Mock(wraps=self.collection)
        self.patches = [patch.object(self.store, 'collection', self.proxy),
                        patch.object(self.store, 'MAX_BATCH_SIZE', 1),
                        patch.dict('os.environ', {'JENNA_PDF_PARSER':'pypdf'}),
                        patch.object(self.store, 'extract_pages', return_value=[{'page':1, 'text':'replacement '*450}]),
                        patch.object(self.store, 'create_embeddings', side_effect=lambda texts:[[1.,0.] for _ in texts]),
                        patch.object(memory_service, 'DB_PATH', Path(self.temp.name)/'memory.sqlite3')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def seed(self, overlap=False):
        if overlap:
            prefix = hashlib.sha256(b'same.pdf').hexdigest()+':'+hashlib.sha256(b'new-pdf').hexdigest()
            ids = [prefix+':0', prefix+':1']
        else:
            ids = ['original-0', 'original-1']
        self.collection.upsert(ids=ids, documents=['original zero', 'original one'],
                               embeddings=[[0.,1.],[0.,1.]],
                               metadatas=[{'filename':'same.pdf', 'page':1, 'chunk_index':i} for i in range(2)])
        return self.snapshot()

    def snapshot(self):
        data = self.collection.get(include=['documents','metadatas','embeddings'])
        return {key:(text,meta,tuple(vector)) for key,text,meta,vector in
                zip(data['ids'], data['documents'], data['metadatas'], data['embeddings'])}

    def fail_second_batch(self):
        calls = 0
        def upsert(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Synthetic batch failure')
            return self.collection.upsert(**kwargs)
        self.proxy.upsert.side_effect = upsert

    def test_failed_replacement_restores_all_previous_chunks_in_bounded_batches(self):
        self.seed()
        self.collection.upsert(ids=['unrelated'], documents=['Keep this other PDF'],
                               embeddings=[[0.,1.]], metadatas=[{'filename':'other.pdf'}])
        original = self.snapshot()
        self.fail_second_batch()
        with self.assertRaisesRegex(RuntimeError, 'Synthetic batch failure'):
            self.store.add_document(io.BytesIO(b'new-pdf'), 'same.pdf')
        self.assertEqual(self.snapshot(), original)
        self.assertTrue(all(len(call.kwargs['ids'])<=1 for call in self.proxy.upsert.call_args_list))

    def test_failed_first_upload_leaves_no_partial_chunks(self):
        self.fail_second_batch()
        with self.assertRaises(RuntimeError):
            self.store.add_document(io.BytesIO(b'new-pdf'), 'same.pdf')
        self.assertEqual(self.collection.count(), 0)

    def test_failed_replacement_restores_overwritten_ids_and_embeddings(self):
        original = self.seed(overlap=True)
        self.fail_second_batch()
        with self.assertRaises(RuntimeError):
            self.store.add_document(io.BytesIO(b'new-pdf'), 'same.pdf')
        self.assertEqual(self.snapshot(), original)

    def test_failed_obsolete_cleanup_restores_previous_revision(self):
        original = self.seed()
        def remove(**kwargs):
            if 'ids' in kwargs:
                # Simulate a partially successful deletion before the error.
                self.collection.delete(ids=kwargs['ids'][:1])
                raise RuntimeError('Synthetic cleanup failure')
            return self.collection.delete(**kwargs)
        self.proxy.delete.side_effect = remove
        with self.assertRaisesRegex(RuntimeError, 'Synthetic cleanup failure'):
            self.store.add_document(io.BytesIO(b'new-pdf'), 'same.pdf')
        self.assertEqual(self.snapshot(), original)

    def test_failed_pdf_storage_restores_index_and_preserves_saved_pdf(self):
        from main.src.memory.document_memory import save_document, load_document_pdf
        original = self.seed()
        save_document('same.pdf', 'old-hash', b'old-pdf', 2)
        with patch.object(self.store, 'save_document', side_effect=RuntimeError('Synthetic SQLite failure')):
            with self.assertRaisesRegex(RuntimeError, 'Synthetic SQLite failure'):
                self.store.index_and_store_document(b'new-pdf', 'same.pdf')
        self.assertEqual(self.snapshot(), original)
        self.assertEqual(load_document_pdf('same.pdf'), b'old-pdf')

    def test_successful_replacement_updates_index_and_saved_pdf(self):
        from main.src.memory.document_memory import load_document_pdf
        self.seed()
        result = self.store.index_and_store_document(b'new-pdf', 'same.pdf')
        self.assertEqual(result['chunk_count'], 3)
        self.assertEqual(self.collection.count(), 3)
        self.assertNotIn('original-0', self.snapshot())
        self.assertEqual(load_document_pdf('same.pdf'), b'new-pdf')


class UploadDeletionTests(unittest.TestCase):
    def test_delete_clears_selection_and_explicit_reselection_can_upload_again(self):
        from streamlit.testing.v1 import AppTest
        catalog = {}
        selection = {'key':'pdf_uploader_0'}
        uploaded = io.BytesIO(b'synthetic pdf')
        uploaded.name = 'review.pdf'
        def uploader(*args, key, **kwargs):
            return [uploaded] if key == selection['key'] else []
        def index(data, name):
            catalog[name] = {'chunk_count':1}
            return {'status':'indexed', 'chunk_count':1}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(memory_service, 'DB_PATH', Path(temp)/'memory.sqlite3'), \
             patch('streamlit.file_uploader', side_effect=uploader), \
             patch('main.src.rag.document_store.index_and_store_document', side_effect=index) as upload, \
             patch('main.src.rag.document_store.delete_document', side_effect=lambda name:catalog.pop(name)), \
             patch('main.src.memory.document_memory.load_document_records', side_effect=lambda:dict(catalog)), \
             patch('main.src.memory.document_memory.load_document_pdf', return_value=b''):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[2]/'main/src/app.py'), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(upload.call_count, 1)
            app.button(key='remove_review.pdf').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(catalog, {})
            app.run()
            self.assertEqual(upload.call_count, 1)
            selection['key'] = f"pdf_uploader_{app.session_state.pdf_uploader_version}"
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(upload.call_count, 2)
            self.assertIn('review.pdf', catalog)


if __name__ == '__main__':
    unittest.main()
