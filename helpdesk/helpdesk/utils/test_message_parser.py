#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for Telegram Message Parser

This module contains comprehensive tests for the TelegramMessageParser class,
covering all message types and parsing scenarios.
"""

import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.helpdesk.utils.message_parser import TelegramMessageParser, parse_telegram_message, extract_message_subject


class TestTelegramMessageParser(FrappeTestCase):
    """Test cases for TelegramMessageParser."""
    
    def setUp(self):
        """Set up test environment."""
        self.parser = TelegramMessageParser()
        
        # Mock bot settings
        self.mock_settings = {
            'max_file_size': 10 * 1024 * 1024,  # 10MB
            'allowed_file_types': ['.jpg', '.png', '.pdf', '.doc'],
            'enable_url_preview': True,
            'sanitize_html': True,
            'extract_entities': True,
        }
    
    @patch('helpdesk.helpdesk.utils.message_parser.frappe.get_single')
    def test_parser_settings(self, mock_get_single):
        """Test parser settings loading."""
        # Mock settings
        mock_bot = MagicMock()
        mock_bot.max_file_size = 5
        mock_bot.allowed_file_types = '.jpg,.png,.pdf'
        mock_bot.enable_url_preview = 1
        mock_bot.sanitize_html = 1
        mock_bot.extract_entities = 1
        mock_get_single.return_value = mock_bot
        
        parser = TelegramMessageParser()
        settings = parser._get_parser_settings()
        
        self.assertEqual(settings['max_file_size'], 5 * 1024 * 1024)
        self.assertEqual(settings['allowed_file_types'], ['.jpg', '.png', '.pdf'])
        self.assertTrue(settings['enable_url_preview'])
    
    def test_text_message_parsing(self):
        """Test parsing of text messages."""
        message_data = {
            'message_id': 123,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': 'Hello! I need help with my account.',
            'entities': [
                {'type': 'bold', 'offset': 0, 'length': 6}
            ]
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'text')
        self.assertEqual(result['text_content']['raw_text'], 'Hello! I need help with my account.')
        self.assertIn('<b>Hello!</b>', result['text_content']['formatted_text'])
        self.assertEqual(len(result['validation_errors']), 0)
    
    def test_photo_message_parsing(self):
        """Test parsing of photo messages."""
        message_data = {
            'message_id': 124,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'photo': [
                {'file_id': 'photo1', 'width': 320, 'height': 240, 'file_size': 15000},
                {'file_id': 'photo2', 'width': 1280, 'height': 960, 'file_size': 85000}
            ],
            'caption': 'This is my problem screenshot'
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'photo')
        self.assertEqual(result['media_content']['file_id'], 'photo2')  # Highest resolution
        self.assertEqual(result['text_content']['raw_text'], 'This is my problem screenshot')
        self.assertEqual(len(result['attachments']), 1)
        self.assertEqual(result['attachments'][0]['type'], 'image')
    
    def test_document_message_parsing(self):
        """Test parsing of document messages."""
        message_data = {
            'message_id': 125,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'document': {
                'file_id': 'doc123',
                'file_unique_id': 'unique_doc123',
                'file_name': 'error_report.pdf',
                'mime_type': 'application/pdf',
                'file_size': 524288
            },
            'caption': 'Error report from yesterday'
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'document')
        self.assertEqual(result['media_content']['file_name'], 'error_report.pdf')
        self.assertEqual(result['media_content']['mime_type'], 'application/pdf')
        self.assertEqual(len(result['attachments']), 1)
        self.assertEqual(result['attachments'][0]['filename'], 'error_report.pdf')
    
    def test_voice_message_parsing(self):
        """Test parsing of voice messages."""
        message_data = {
            'message_id': 126,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'voice': {
                'file_id': 'voice123',
                'file_unique_id': 'unique_voice123',
                'duration': 15,
                'mime_type': 'audio/ogg',
                'file_size': 32768
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'voice')
        self.assertEqual(result['media_content']['duration'], 15)
        self.assertEqual(len(result['attachments']), 1)
        self.assertEqual(result['attachments'][0]['type'], 'audio')
    
    def test_sticker_message_parsing(self):
        """Test parsing of sticker messages."""
        message_data = {
            'message_id': 127,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'sticker': {
                'file_id': 'sticker123',
                'file_unique_id': 'unique_sticker123',
                'width': 512,
                'height': 512,
                'is_animated': False,
                'emoji': '😀',
                'set_name': 'test_stickers',
                'file_size': 45000
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'sticker')
        self.assertEqual(result['media_content']['emoji'], '😀')
        self.assertIn('😀', result['text_content']['raw_text'])
        self.assertIn('sticker', result['text_content']['raw_text'])
    
    def test_location_message_parsing(self):
        """Test parsing of location messages."""
        message_data = {
            'message_id': 128,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'location': {
                'latitude': 37.7749,
                'longitude': -122.4194
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'location')
        self.assertEqual(result['media_content']['latitude'], 37.7749)
        self.assertEqual(result['media_content']['longitude'], -122.4194)
        self.assertIn('📍 Location', result['text_content']['raw_text'])
    
    def test_contact_message_parsing(self):
        """Test parsing of contact messages."""
        message_data = {
            'message_id': 129,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'contact': {
                'phone_number': '+1234567890',
                'first_name': 'John',
                'last_name': 'Doe',
                'user_id': 12345
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['message_type'], 'contact')
        self.assertEqual(result['media_content']['phone_number'], '+1234567890')
        self.assertEqual(result['media_content']['first_name'], 'John')
        self.assertIn('👤 Contact: John Doe', result['text_content']['raw_text'])
    
    def test_url_extraction(self):
        """Test URL extraction from text messages."""
        message_data = {
            'message_id': 130,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': 'Please check https://example.com and http://test.org for more info.',
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertIn('urls', result['metadata'])
        self.assertEqual(len(result['metadata']['urls']), 2)
        self.assertIn('https://example.com', result['metadata']['urls'])
        self.assertIn('http://test.org', result['metadata']['urls'])
    
    def test_entity_extraction(self):
        """Test entity extraction (emails, phones) from text."""
        message_data = {
            'message_id': 131,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': 'Contact me at john@example.com or call +1-555-123-4567',
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        self.assertIn('emails', result['entities'])
        self.assertIn('phones', result['entities'])
        self.assertIn('john@example.com', result['entities']['emails'])
    
    def test_file_size_validation(self):
        """Test file size validation."""
        # Create large file message
        message_data = {
            'message_id': 132,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'document': {
                'file_id': 'large_doc',
                'file_name': 'large_file.pdf',
                'file_size': 50 * 1024 * 1024  # 50MB (larger than 10MB limit)
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('File too large' in error for error in result['validation_errors']))
    
    def test_text_length_validation(self):
        """Test text length validation."""
        long_text = 'a' * 5000  # Longer than Telegram's 4096 limit
        message_data = {
            'message_id': 133,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': long_text,
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Message too long' in error for error in result['validation_errors']))
    
    def test_unsupported_message_type(self):
        """Test handling of unsupported message types."""
        message_data = {
            'message_id': 134,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'poll': {
                'id': 'poll123',
                'question': 'What is your favorite color?',
                'options': [{'text': 'Red', 'voter_count': 0}]
            }
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])  # Still valid, just unsupported
        self.assertEqual(result['message_type'], 'poll')
        self.assertIn('[Unsupported message type]', result['text_content']['raw_text'])
    
    def test_missing_required_fields(self):
        """Test validation of required fields."""
        message_data = {
            'text': 'Hello world'
            # Missing message_id, chat, from
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertFalse(result['is_valid'])
        self.assertTrue(any('Missing required field' in error for error in result['validation_errors']))
    
    def test_subject_extraction(self):
        """Test ticket subject extraction."""
        # Test normal text
        parsed_message = {
            'text_content': {
                'raw_text': 'I have a problem with my login.\nIt keeps saying invalid password.'
            }
        }
        subject = TelegramMessageParser.extract_ticket_subject(parsed_message)
        self.assertEqual(subject, 'I have a problem with my login.')
        
        # Test long text
        long_text = 'This is a very long message that exceeds the maximum length for a subject line and should be truncated properly'
        parsed_message = {
            'text_content': {
                'raw_text': long_text
            }
        }
        subject = TelegramMessageParser.extract_ticket_subject(parsed_message, max_length=50)
        self.assertTrue(len(subject) <= 50)
        self.assertTrue(subject.endswith('...'))
        
        # Test empty text
        parsed_message = {
            'message_type': 'photo'
        }
        subject = TelegramMessageParser.extract_ticket_subject(parsed_message)
        self.assertEqual(subject, 'New photo from Telegram')
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        message_data = {
            'message_id': 135,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': 'Test message',
        }
        
        with patch('helpdesk.helpdesk.utils.message_parser.frappe.get_single') as mock_get_single:
            mock_bot = MagicMock()
            mock_bot.max_file_size = 10
            mock_bot.allowed_file_types = ''
            mock_bot.enable_url_preview = 1
            mock_bot.sanitize_html = 1
            mock_bot.extract_entities = 1
            mock_get_single.return_value = mock_bot
            
            # Test parse_telegram_message function
            result = parse_telegram_message(message_data)
            self.assertTrue(result['is_valid'])
            self.assertEqual(result['message_type'], 'text')
            
            # Test extract_message_subject function
            subject = extract_message_subject(message_data)
            self.assertEqual(subject, 'Test message')
    
    def test_html_sanitization(self):
        """Test HTML sanitization in messages."""
        message_data = {
            'message_id': 136,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': '<script>alert("xss")</script>Hello & goodbye',
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        sanitized_text = result['text_content']['raw_text']
        self.assertNotIn('<script>', sanitized_text)
        self.assertIn('&amp;', sanitized_text)  # HTML escaped
    
    def test_entity_formatting(self):
        """Test entity formatting in text."""
        message_data = {
            'message_id': 137,
            'chat': {'id': 456},
            'from': {'id': 789},
            'date': 1640995200,
            'text': 'Hello world',
            'entities': [
                {'type': 'bold', 'offset': 0, 'length': 5},
                {'type': 'italic', 'offset': 6, 'length': 5}
            ]
        }
        
        with patch.object(self.parser, '_get_parser_settings', return_value=self.mock_settings):
            result = self.parser.parse_message(message_data)
        
        self.assertTrue(result['is_valid'])
        formatted_text = result['text_content']['formatted_text']
        self.assertIn('<b>Hello</b>', formatted_text)
        self.assertIn('<i>world</i>', formatted_text)


if __name__ == '__main__':
    unittest.main() 