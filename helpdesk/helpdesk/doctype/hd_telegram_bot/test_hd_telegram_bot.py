# Copyright (c) 2024, Frappe Technologies and Contributors
# See license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase


class TestHDTelegramBot(FrappeTestCase):
    def setUp(self):
        """Set up test data"""
        pass
    
    def test_bot_token_validation(self):
        """Test bot token validation"""
        # Test valid token format
        result = frappe.get_doc("HD Telegram Bot").validate_bot_token()
        
        # Test invalid token format
        with self.assertRaises(frappe.ValidationError):
            bot = frappe.get_doc({
                "doctype": "HD Telegram Bot",
                "bot_name": "Test Bot",
                "bot_token": "invalid_token"
            })
            bot.validate_bot_token()
    
    def test_webhook_url_generation(self):
        """Test webhook URL generation"""
        bot = frappe.get_doc({
            "doctype": "HD Telegram Bot",
            "bot_name": "Test Bot",
            "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        })
        bot.set_webhook_url()
        
        self.assertIn("/api/method/helpdesk.www.telegram.webhook.handle_webhook", bot.webhook_url) 