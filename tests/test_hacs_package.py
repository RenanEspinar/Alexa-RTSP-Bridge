"""Checks that the HACS adapter and browser wizard are packaged together."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / 'custom_components' / 'alexa_rtsp_bridge'


class HACSStructureTests(unittest.TestCase):
    def test_required_metadata(self):
        manifest = json.loads((COMPONENT / 'manifest.json').read_text())
        self.assertEqual(manifest['domain'], 'alexa_rtsp_bridge')
        self.assertTrue(manifest['config_flow'])
        for k in ('documentation', 'issue_tracker', 'codeowners', 'name', 'version'):
            self.assertTrue(manifest.get(k), k)
        self.assertTrue((ROOT / 'hacs.json').is_file())
        self.assertTrue((COMPONENT / 'translations' / 'es.json').is_file())
        self.assertTrue((COMPONENT / 'translations' / 'en.json').is_file())

    def test_setup_flow_exists(self):
        source = (COMPONENT / 'config_flow.py').read_text()
        self.assertIn('async_step_user', source)
        self.assertIn('async_set_unique_id', source)
        self.assertIn('/api/state', source)

    def test_wizard_guide_link_is_published(self):
        root = Path(__file__).resolve().parent.parent
        js = (root / 'alexa_bridge/promax/static/app.js').read_text(encoding='utf-8')
        self.assertIn('docs/GUIA_COMPLETA_ES.md', js)
        self.assertTrue((root / 'docs/GUIA_COMPLETA_ES.md').is_file())

    def test_wizard_step_and_no_public_admin(self):
        h = (ROOT / 'alexa_bridge' / 'promax' / 'static' / 'index.html').read_text()
        j = (ROOT / 'alexa_bridge' / 'promax' / 'static' / 'app.js').read_text()
        compose = (ROOT / 'compose.pro.yml').read_text()
        self.assertIn('id="setup-wizard"', h)
        self.assertIn('id="setup-open"', h)
        for step in ('Welcome to Alexa RTSP Bridge Pro', 'Add your cameras',
                     'Verify your first stream', 'Connect Alexa when you are ready'):
            self.assertIn(step, j)
        self.assertIn('127.0.0.1:', compose)
        self.assertIn('UI_PORT', compose)
        self.assertIn('HLS_PORT', compose)


if __name__ == '__main__':
    unittest.main()
