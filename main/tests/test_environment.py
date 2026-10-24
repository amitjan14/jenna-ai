import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from main.src.utils.environment import tavily_api_key


class LocalWebKeyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.file = Path(self.directory.name) / '.env'
        self.path = patch('main.src.utils.environment.LOCAL_ENV_FILE', self.file)
        self.path.start()
        self.env = patch.dict(os.environ)
        self.env.start()
        os.environ.pop('TAVILY_API_KEY', None)

    def tearDown(self):
        self.env.stop()
        self.path.stop()
        self.directory.cleanup()

    def test_missing_file_reports_unconfigured(self):
        self.assertEqual(tavily_api_key(), '')

    def test_literal_file_key_survives_repeated_reads_without_export(self):
        self.file.write_text('# local config\nTAVILY_API_KEY="test-only"\nOTHER_SETTING=untouched\n')
        self.assertEqual(tavily_api_key(), 'test-only')
        self.assertEqual(tavily_api_key(), 'test-only')
        self.assertNotIn('TAVILY_API_KEY', os.environ)

    def test_exported_value_or_explicit_empty_overrides_local_file(self):
        self.file.write_text('TAVILY_API_KEY=file-value\n')
        os.environ['TAVILY_API_KEY'] = 'environment-value'
        self.assertEqual(tavily_api_key(), 'environment-value')
        os.environ['TAVILY_API_KEY'] = ''
        self.assertEqual(tavily_api_key(), '')

    def test_file_refresh_and_shell_expressions_are_literal(self):
        self.file.write_text("export TAVILY_API_KEY='first-value'\n")
        self.assertEqual(tavily_api_key(), 'first-value')
        self.file.write_text('TAVILY_API_KEY=$(this-is-not-executed)\n')
        self.assertEqual(tavily_api_key(), '$(this-is-not-executed)')
