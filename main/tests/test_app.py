import os
import tempfile
import unittest
from pathlib import Path


TEMP = tempfile.TemporaryDirectory(prefix="jenna-app-test-")
os.environ.setdefault("JENNA_MEMORY_PATH", TEMP.name)


class AppSmokeTests(unittest.TestCase):
    def test_initial_page_renders(self):
        # unittest's core suite has already configured an isolated memory path.
        from streamlit.testing.v1 import AppTest
        path=Path(__file__).resolve().parents[2]/'main/src/app.py'
        app=AppTest.from_file(str(path),default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.title[0].value,'Jenna AI')
        self.assertEqual(app.selectbox(key='source_mode').value,'Auto')
        self.assertEqual(app.selectbox(key='mcp_connection').value,'auto')
        app.selectbox(key='mcp_connection').set_value('openai').run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(app.selectbox(key='source_mode').disabled)
        self.assertEqual(app.checkbox[0].value,False)

    def test_saved_preferences_can_be_edited_and_forgotten(self):
        from streamlit.testing.v1 import AppTest
        from main.src.memory.note_memory import remember_note,note_details,forget_note
        remember_note('ui_test_language','Python',provenance={'source':'explicit_user_request'})
        try:
            app=AppTest.from_file(str(Path(__file__).resolve().parents[2]/'main/src/app.py'),default_timeout=30).run()
            app.selectbox(key='preference_edit_key').set_value('ui_test_language').run()
            next(t for t in app.text_area if t.label=='Saved value').set_value('Rust')
            next(b for b in app.button if b.label=='Save preference edit').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(note_details('ui_test_language')['value'],'Rust')
            self.assertEqual(note_details('ui_test_language')['provenance']['source'],'ui_edit')
            next(b for b in app.button if b.label=='Forget preference').click().run()
            self.assertIsNone(note_details('ui_test_language'))
        finally:forget_note('ui_test_language')


if __name__=='__main__':unittest.main()
