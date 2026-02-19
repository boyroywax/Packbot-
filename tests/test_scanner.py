"""Unit tests for scanner and TCG API modules."""

import sys
import os
import types
import unittest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Stub out heavy optional dependencies so tests work without them installed
# ---------------------------------------------------------------------------
for stub in ('cv2', 'numpy', 'imagehash'):
    if stub not in sys.modules:
        sys.modules[stub] = types.ModuleType(stub)

# Stub PIL
if 'PIL' not in sys.modules:
    pil = types.ModuleType('PIL')
    pil.Image = MagicMock()
    sys.modules['PIL'] = pil
    sys.modules['PIL.Image'] = pil.Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import scanner
import tcg_api


class TestParseSetNumber(unittest.TestCase):
    def test_slash_format(self):
        result = scanner.parse_set_number("base1/4")
        self.assertEqual(result, ("base1", "4"))

    def test_hash_format(self):
        result = scanner.parse_set_number("SVI #001")
        self.assertEqual(result, ("SVI", "001"))

    def test_no_match(self):
        result = scanner.parse_set_number("just a pokemon name")
        self.assertIsNone(result)

    def test_embedded_in_text(self):
        result = scanner.parse_set_number("Card base1/4 Charizard Scarlet & Violet")
        self.assertIsNotNone(result)
        self.assertEqual(result, ("base1", "4"))


class TestScanFromText(unittest.TestCase):
    @patch('scanner.lookup_by_set_number')
    def test_finds_by_set_number_pattern(self, mock_lookup):
        mock_lookup.return_value = {"id": "base1-4", "name": "Charizard"}
        result = scanner.scan_from_text("base1/4")
        self.assertEqual(result['card']['id'], 'base1-4')
        self.assertEqual(result['method'], 'text_set_number')
        self.assertAlmostEqual(result['confidence'], 0.9)

    @patch('scanner.lookup_by_name')
    @patch('scanner.parse_set_number')
    def test_falls_back_to_name_search(self, mock_parse, mock_name):
        mock_parse.return_value = None
        mock_name.return_value = [{"id": "xy1-1", "name": "Venusaur"}]
        result = scanner.scan_from_text("Venusaur")
        self.assertEqual(result['card']['name'], 'Venusaur')
        self.assertEqual(result['method'], 'text_name_search')

    @patch('scanner.lookup_by_name')
    @patch('scanner.parse_set_number')
    def test_no_match_returns_none(self, mock_parse, mock_name):
        mock_parse.return_value = None
        mock_name.return_value = []
        result = scanner.scan_from_text("xyzzy")
        self.assertIsNone(result['card'])
        self.assertEqual(result['method'], 'none')


class TestScanFromImage(unittest.TestCase):
    @patch('scanner.lookup_by_set_number')
    def test_exact_set_number_lookup(self, mock_lookup):
        mock_lookup.return_value = {"id": "swsh1-1", "name": "Cottonee"}
        result = scanner.scan_from_image("", set_code="swsh1", card_number="1")
        self.assertEqual(result['method'], 'set_number')
        self.assertEqual(result['confidence'], 1.0)

    @patch('scanner.lookup_by_name')
    def test_name_search_fallback(self, mock_name):
        mock_name.return_value = [
            {"id": "base1-6", "name": "Blastoise"},
            {"id": "base2-6", "name": "Blastoise"},
        ]
        result = scanner.scan_from_image("", pokemon_name="Blastoise")
        self.assertEqual(result['method'], 'name_search')
        self.assertEqual(result['card']['id'], 'base1-6')
        self.assertEqual(len(result['candidates']), 1)

    def test_no_hints_returns_none(self):
        result = scanner.scan_from_image("")
        self.assertIsNone(result['card'])
        self.assertEqual(result['method'], 'none')


class TestTcgApiHelpers(unittest.TestCase):
    @patch('tcg_api.requests.get')
    def test_search_cards_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "base1-4"}], "totalCount": 1}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = tcg_api.search_cards('name:Charizard')
        self.assertEqual(len(result['data']), 1)

    @patch('tcg_api.requests.get')
    def test_search_cards_network_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("timeout")
        result = tcg_api.search_cards('name:Pikachu')
        self.assertIn('error', result)
        self.assertEqual(result['data'], [])

    @patch('tcg_api.requests.get')
    def test_get_card_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        result = tcg_api.get_card('nonexistent-99')
        self.assertIsNone(result)

    @patch('tcg_api.requests.get')
    def test_search_by_name(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "sm1-1", "name": "Rowlet"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        cards = tcg_api.search_by_name("Rowlet")
        self.assertEqual(cards[0]['name'], 'Rowlet')


if __name__ == '__main__':
    unittest.main()
