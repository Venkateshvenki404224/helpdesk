# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
import json
from frappe import _
from frappe.utils import cstr, get_url


class TelegramBotClient:
    """Telegram Bot API Client for sending messages and managing bot operations"""
    
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None):
        """Send text message to chat"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        """Send photo to chat"""
        try:
            url = f"{self.base_url}/sendPhoto"
            payload = {
                "chat_id": chat_id,
                "photo": photo
            }
            
            if caption:
                payload["caption"] = caption
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def send_document(self, chat_id, document, caption=None, reply_markup=None):
        """Send document to chat"""
        try:
            url = f"{self.base_url}/sendDocument"
            payload = {
                "chat_id": chat_id,
                "document": document
            }
            
            if caption:
                payload["caption"] = caption
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def get_me(self):
        """Get bot information"""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def set_webhook(self, webhook_url, secret_token=None):
        """Set webhook for the bot"""
        try:
            url = f"{self.base_url}/setWebhook"
            payload = {
                "url": webhook_url,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": True
            }
            
            if secret_token:
                payload["secret_token"] = secret_token
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def delete_webhook(self):
        """Delete webhook for the bot"""
        try:
            url = f"{self.base_url}/deleteWebhook"
            payload = {"drop_pending_updates": True}
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def get_webhook_info(self):
        """Get webhook information"""
        try:
            url = f"{self.base_url}/getWebhookInfo"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def send_chat_action(self, chat_id, action="typing"):
        """Send chat action (typing indicator)"""
        try:
            url = f"{self.base_url}/sendChatAction"
            payload = {
                "chat_id": chat_id,
                "action": action
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}


# Utility functions for easy access

@frappe.whitelist()
def get_bot_client(bot_name=None):
    """Get Telegram Bot Client for active bot or specific bot"""
    try:
        if bot_name:
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        else:
            # Get active bot
            from helpdesk.helpdesk.doctype.hd_telegram_bot.hd_telegram_bot import get_active_bot
            bot_data = get_active_bot()
            if not bot_data:
                return None
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_data.name)
        
        if not bot_doc.is_active:
            return None
        
        return TelegramBotClient(bot_doc.bot_token)
    
    except Exception as e:
        frappe.log_error("Bot Client Error", str(e))
        return None


@frappe.whitelist()
def send_ticket_notification(ticket_name, telegram_user_id, message_type="created"):
    """Send ticket notification to Telegram user"""
    try:
        # Get bot client
        client = get_bot_client()
        if not client:
            return {"success": False, "message": "No active bot found"}
        
        # Get ticket details
        ticket = frappe.get_doc("HD Ticket", ticket_name)
        
        # Format notification message
        if message_type == "created":
            message = f"🎫 <b>Ticket Created</b>\n\n"
            message += f"📝 <b>Subject:</b> {ticket.subject}\n"
            message += f"🆔 <b>Ticket ID:</b> {ticket.name}\n"
            message += f"🏷️ <b>Status:</b> {ticket.status}\n"
            message += f"⚡ <b>Priority:</b> {ticket.priority}\n\n"
            message += f"Our team will respond to your ticket soon. You can check the status anytime by typing /status"
        
        elif message_type == "updated":
            message = f"🔄 <b>Ticket Updated</b>\n\n"
            message += f"📝 <b>Subject:</b> {ticket.subject}\n"
            message += f"🆔 <b>Ticket ID:</b> {ticket.name}\n"
            message += f"🏷️ <b>Status:</b> {ticket.status}\n\n"
            message += f"There's an update on your ticket. Check your email or type /status for details."
        
        elif message_type == "resolved":
            message = f"✅ <b>Ticket Resolved</b>\n\n"
            message += f"📝 <b>Subject:</b> {ticket.subject}\n"
            message += f"🆔 <b>Ticket ID:</b> {ticket.name}\n\n"
            message += f"Your ticket has been resolved! If you need further assistance, just send us a new message."
        
        else:
            message = f"🔔 <b>Ticket Notification</b>\n\n"
            message += f"📝 <b>Subject:</b> {ticket.subject}\n"
            message += f"🆔 <b>Ticket ID:</b> {ticket.name}\n"
            message += f"🏷️ <b>Status:</b> {ticket.status}"
        
        # Send message
        result = client.send_message(telegram_user_id, message)
        
        if result.get("success"):
            return {"success": True, "message": "Notification sent"}
        else:
            frappe.log_error("Telegram Notification Failed", result.get("error"))
            return {"success": False, "message": result.get("error")}
    
    except Exception as e:
        frappe.log_error("Ticket Notification Error", str(e))
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def send_agent_reply_notification(communication_name):
    """Send notification when agent replies to ticket"""
    try:
        # Get communication details
        comm = frappe.get_doc("Communication", communication_name)
        ticket = frappe.get_doc("HD Ticket", comm.reference_name)
        
        # Find telegram user for this ticket
        telegram_user = frappe.db.get_value(
            "HD Telegram User",
            {"customer": ticket.customer},
            ["telegram_user_id", "notifications_enabled"],
            as_dict=True
        )
        
        if not telegram_user or not telegram_user.notifications_enabled:
            return {"success": False, "message": "User not found or notifications disabled"}
        
        # Get bot client
        client = get_bot_client()
        if not client:
            return {"success": False, "message": "No active bot found"}
        
        # Format reply message
        message = f"💬 <b>New Reply from Support</b>\n\n"
        message += f"🎫 <b>Ticket:</b> {ticket.subject}\n"
        message += f"🆔 <b>ID:</b> {ticket.name}\n\n"
        
        # Truncate content if too long
        content = comm.content or ""
        if len(content) > 500:
            content = content[:500] + "..."
        
        message += f"📝 <b>Message:</b>\n{content}\n\n"
        message += f"You can reply directly to this message to continue the conversation."
        
        # Send notification
        result = client.send_message(telegram_user.telegram_user_id, message)
        
        if result.get("success"):
            return {"success": True, "message": "Reply notification sent"}
        else:
            frappe.log_error("Reply Notification Failed", result.get("error"))
            return {"success": False, "message": result.get("error")}
    
    except Exception as e:
        frappe.log_error("Reply Notification Error", str(e))
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def create_inline_keyboard(buttons):
    """Create inline keyboard markup for Telegram"""
    try:
        keyboard = []
        
        for row in buttons:
            keyboard_row = []
            for button in row:
                keyboard_row.append({
                    "text": button.get("text"),
                    "callback_data": button.get("callback_data"),
                    "url": button.get("url")
                })
            keyboard.append(keyboard_row)
        
        return {
            "inline_keyboard": keyboard
        }
    
    except Exception as e:
        frappe.log_error("Inline Keyboard Creation Error", str(e))
        return None


@frappe.whitelist()
def test_bot_connectivity(bot_name):
    """Test bot connectivity and return bot information"""
    try:
        bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        client = TelegramBotClient(bot_doc.bot_token)
        
        result = client.get_me()
        
        if result.get("success"):
            bot_info = result.get("data", {}).get("result", {})
            return {
                "success": True,
                "message": "Bot connectivity test successful",
                "bot_info": {
                    "id": bot_info.get("id"),
                    "username": bot_info.get("username"),
                    "first_name": bot_info.get("first_name"),
                    "can_join_groups": bot_info.get("can_join_groups"),
                    "can_read_all_group_messages": bot_info.get("can_read_all_group_messages"),
                    "supports_inline_queries": bot_info.get("supports_inline_queries")
                }
            }
        else:
            return {
                "success": False,
                "message": "Bot connectivity test failed",
                "error": result.get("error")
            }
    
    except Exception as e:
        frappe.log_error("Bot Connectivity Test Error", str(e))
        return {
            "success": False,
            "message": "Test failed",
            "error": str(e)
        }


# Background job functions

def send_message_background(chat_id, text, bot_token, parse_mode="HTML", reply_markup=None):
    """Background job to send message"""
    try:
        client = TelegramBotClient(bot_token)
        result = client.send_message(chat_id, text, parse_mode, reply_markup)
        
        if not result.get("success"):
            frappe.log_error("Background Message Send Failed", result.get("error"))
    
    except Exception as e:
        frappe.log_error("Background Message Send Error", str(e))


def send_notification_background(telegram_user_id, message, bot_name=None):
    """Background job to send notification"""
    try:
        client = get_bot_client(bot_name)
        if not client:
            frappe.log_error("Notification Send Failed", "No active bot found")
            return
        
        result = client.send_message(telegram_user_id, message)
        
        if not result.get("success"):
            frappe.log_error("Background Notification Send Failed", result.get("error"))
    
    except Exception as e:
        frappe.log_error("Background Notification Send Error", str(e)) 