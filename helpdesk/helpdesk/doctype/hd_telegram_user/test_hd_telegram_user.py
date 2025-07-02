# Copyright (c) 2024, Frappe Technologies and Contributors
# See license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase


class TestHDTelegramUser(FrappeTestCase):
    def setUp(self):
        """Set up test data"""
        pass
    
    def test_telegram_user_creation(self):
        """Test Telegram user creation"""
        user_data = {
            "id": "123456789",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "language_code": "en"
        }
        
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
        user_doc = get_or_create_telegram_user(user_data)
        
        self.assertEqual(user_doc.telegram_user_id, "123456789")
        self.assertEqual(user_doc.username, "testuser")
        self.assertEqual(user_doc.first_name, "Test")
    
    def test_user_id_validation(self):
        """Test Telegram user ID validation"""
        with self.assertRaises(frappe.ValidationError):
            user_doc = frappe.get_doc({
                "doctype": "HD Telegram User",
                "telegram_user_id": "invalid_id"
            })
            user_doc.save() 