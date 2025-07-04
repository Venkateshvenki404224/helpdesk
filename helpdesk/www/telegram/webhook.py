# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import hmac
import hashlib
import frappe
from frappe import _
from frappe.utils import cstr

# Setup logging for webhook debugging
frappe.utils.logger.set_log_level("DEBUG")
logger = frappe.logger("api", allow_site=True, file_count=50)


def get_context(context):
    """Set no cache for webhook endpoints"""
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_webhook():
    """Main webhook handler for Telegram updates"""
    try:
        logger.info("=== TELEGRAM WEBHOOK CALLED ===")
        
        # Get request data
        data = frappe.request.get_data()
        headers = frappe.request.headers
        
        logger.debug(f"Request headers: {dict(headers)}")
        logger.debug(f"Request data size: {len(data)} bytes")
        
        # Validate request
        logger.info("Validating webhook request...")
        validation_result = validate_webhook_request(data, headers)
        
        if not validation_result.get("success"):
            logger.error(f"Webhook validation failed: {validation_result.get('message')}")
            frappe.response.status_code = 401
            return {"error": validation_result.get("message")}
        
        logger.info(f"Webhook validation successful for bot: {validation_result.get('bot_doc').bot_name}")
        
        # Parse JSON data
        try:
            update_data = json.loads(data.decode('utf-8'))
            logger.debug(f"Parsed update data: {json.dumps(update_data, indent=2)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {str(e)}")
            frappe.response.status_code = 400
            return {"error": "Invalid JSON data"}
        
        # Process the update
        bot_doc = validation_result.get("bot_doc")
        logger.info(f"Processing update for bot: {bot_doc.bot_name}")
        result = process_telegram_update(update_data, bot_doc)
        
        if result.get("success"):
            logger.info(f"Webhook processing successful: {result.get('message', 'OK')}")
            frappe.response.status_code = 200
            return {"message": "OK"}
        else:
            logger.warning(f"Webhook processing failed: {result.get('message')}")
            frappe.response.status_code = 200  # Always return 200 to Telegram
            frappe.log_error("Webhook Processing Failed", result.get("message"))
            return {"message": "OK"}
    
    except Exception as e:
        logger.error(f"Webhook handler exception: {str(e)}", exc_info=True)
        frappe.log_error("Webhook Handler Error", str(e))
        frappe.response.status_code = 200  # Always return 200 to Telegram
        return {"message": "OK"}


def validate_webhook_request(data, headers):
    """Validate incoming webhook request security"""
    try:
        logger.debug("Validating webhook request...")
        
        # Get secret token from header
        secret_token = headers.get('X-Telegram-Bot-Api-Secret-Token')
        logger.debug(f"Secret token present: {bool(secret_token)}")
        
        if not secret_token:
            logger.error("Missing secret token in webhook request")
            return {"success": False, "message": "Missing secret token"}
        
        # Find bot with matching secret
        logger.debug("Looking up bot by secret token...")
        bot_name = frappe.db.get_value(
            "HD Telegram Bot",
            {"webhook_secret": secret_token, "is_active": 1},
            "name"
        )
        
        if not bot_name:
            logger.error("Invalid or inactive secret token")
            return {"success": False, "message": "Invalid secret token"}
        
        logger.debug(f"Found bot: {bot_name}")
        
        # Get bot document
        bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        logger.info(f"Webhook validation successful for bot: {bot_doc.bot_name}")
        
        # Additional IP validation could be added here
        # Telegram webhook IPs: https://core.telegram.org/bots/webhooks#the-short-version
        
        return {
            "success": True,
            "bot_doc": bot_doc
        }
    
    except Exception as e:
        logger.error(f"Webhook validation exception: {str(e)}", exc_info=True)
        frappe.log_error("Webhook Validation Error", str(e))
        return {"success": False, "message": "Validation error"}


def process_telegram_update(update_data, bot_doc):
    """Process incoming Telegram update"""
    try:
        logger.info("--- Processing Telegram Update ---")
        
        # Determine update type
        update_type = None
        if "message" in update_data:
            update_type = "message"
        elif "callback_query" in update_data:
            update_type = "callback_query"
        elif "edited_message" in update_data:
            update_type = "edited_message"
        else:
            update_type = "unknown"
        
        logger.info(f"Update type: {update_type}")
        
        # Check rate limiting
        logger.debug("Checking rate limiting...")
        if not check_rate_limiting(update_data, bot_doc):
            logger.warning("Rate limit exceeded for user")
            return {"success": False, "message": "Rate limit exceeded"}
        
        logger.debug("Rate limiting check passed")
        
        # Handle different update types
        if update_type == "message":
            logger.info("Processing message update")
            return process_message(update_data, bot_doc)
        elif update_type == "callback_query":
            logger.info("Processing callback query update")
            return process_callback_query(update_data, bot_doc)
        elif update_type == "edited_message":
            logger.info("Processing edited message update")
            return process_edited_message(update_data, bot_doc)
        else:
            # Log unknown update type for debugging
            logger.warning(f"Unknown update type: {update_type}")
            frappe.log_error("Unknown Update Type", json.dumps(update_data))
            return {"success": True, "message": "Update type not handled"}
    
    except Exception as e:
        logger.error(f"Update processing exception: {str(e)}", exc_info=True)
        frappe.log_error("Update Processing Error", str(e))
        return {"success": False, "message": str(e)}


def process_message(update_data, bot_doc):
    """Process incoming message"""
    try:
        message = update_data.get("message", {})
        user_data = message.get("from", {})
        message_text = message.get("text", "")
        user_id = user_data.get("id")
        chat_id = message.get("chat", {}).get("id")
        
        logger.info(f"Processing message from user {user_id} in chat {chat_id}")
        logger.debug(f"Message text: '{message_text[:100]}{'...' if len(message_text) > 100 else ''}'")
        
        # Update bot statistics
        logger.debug("Updating bot message count...")
        bot_doc.increment_message_count()
        
        # Handle bot commands first
        if message_text.startswith("/"):
            logger.info(f"Detected bot command: {message_text.split()[0]}")
            return handle_bot_command(message, bot_doc)
        
        logger.info("Processing regular message for ticket creation...")
        
        # Process regular message as potential ticket
        from helpdesk.helpdesk.utils.ticket_creator import create_ticket_from_telegram_message
        
        # Pass just the message data for ticket creation
        logger.debug("Calling ticket creator...")
        result = create_ticket_from_telegram_message(message)
        
        logger.info(f"Ticket creation result: {result.get('success')}")
        
        if result.get("success"):
            ticket_id = result.get("ticket")
            logger.info(f"✅ Ticket {ticket_id} created successfully")
            
            # Send confirmation if enabled
            if bot_doc.auto_acknowledge:
                logger.debug("Sending ticket confirmation...")
                send_ticket_confirmation(message, result, bot_doc)
            else:
                logger.debug("Auto-acknowledge disabled, skipping confirmation")
        else:
            # Handle errors
            error_type = result.get("error", "unknown")
            error_message = result.get("message", "Unknown error")
            logger.warning(f"❌ Ticket creation failed: {error_type} - {error_message}")
            
            if error_type == "verification_required":
                logger.info("Sending verification message...")
                send_verification_message(message, bot_doc)
            elif error_type == "blocked_user":
                logger.info("User is blocked, not sending any response")
                # Don't send anything to blocked users
                pass
            else:
                logger.info("Sending generic error message...")
                # Send generic error message
                send_error_message(message, result, bot_doc)
        
        return result
    
    except Exception as e:
        logger.error(f"Message processing exception: {str(e)}", exc_info=True)
        frappe.log_error("Message Processing Error", str(e))
        return {"success": False, "message": str(e)}


def process_callback_query(update_data, bot_doc):
    """Process callback query (inline keyboard responses)"""
    try:
        callback_query = update_data.get("callback_query", {})
        callback_data = callback_query.get("data", "")
        
        # Handle different callback types
        if callback_data.startswith("status_"):
            return handle_status_query(callback_query, bot_doc)
        elif callback_data.startswith("ticket_"):
            return handle_ticket_query(callback_query, bot_doc)
        
        return {"success": True, "message": "Callback handled"}
    
    except Exception as e:
        frappe.log_error("Callback Query Processing Error", str(e))
        return {"success": False, "message": str(e)}


def process_edited_message(update_data, bot_doc):
    """Process edited message"""
    try:
        # For now, we'll just log edited messages
        # In the future, we might want to update the original ticket
        frappe.log_error("Message Edited", json.dumps(update_data))
        return {"success": True, "message": "Edit logged"}
    
    except Exception as e:
        frappe.log_error("Edited Message Processing Error", str(e))
        return {"success": False, "message": str(e)}


def handle_bot_command(message, bot_doc):
    """Handle bot commands using the new command handler"""
    try:
        # Import command handler
        from helpdesk.helpdesk.utils.command_handler import handle_telegram_command
        
        # Process command using the enhanced handler
        result = handle_telegram_command(message)
        
        if result.get("success"):
            chat_id = message.get("chat", {}).get("id")
            response_text = result.get("message", "Command processed successfully.")
            parse_mode = result.get("parse_mode", None)
            
            # Send response
            send_message(chat_id, response_text, bot_doc, parse_mode=parse_mode)
            
            return {"success": True, "message": "Command handled"}
        else:
            # Handle command errors
            chat_id = message.get("chat", {}).get("id")
            error_message = result.get("message", "Sorry, an error occurred while processing your command.")
            send_message(chat_id, error_message, bot_doc)
            
            return result
    
    except Exception as e:
        frappe.log_error("Command Handler Error", str(e))
        
        # Send fallback response
        chat_id = message.get("chat", {}).get("id")
        if chat_id:
            fallback_text = "Sorry, I couldn't process your command. Please try again later."
            send_message(chat_id, fallback_text, bot_doc)
        
        return {"success": False, "message": str(e)}


def handle_status_command(message, bot_doc):
    """Handle /status command to show ticket status"""
    try:
        user_data = message.get("from", {})
        chat_id = message.get("chat", {}).get("id")
        telegram_user_id = cstr(user_data.get("id"))
        
        # Get user's tickets
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_user_tickets
        tickets = get_user_tickets(telegram_user_id)
        
        if not tickets:
            send_message(chat_id, "You don't have any tickets yet.", bot_doc)
        else:
            status_text = "Your tickets:\n\n"
            for ticket in tickets[:5]:  # Show last 5 tickets
                status_text += f"🎫 {ticket['name']}\n"
                status_text += f"📝 {ticket['subject']}\n"
                status_text += f"🏷️ Status: {ticket['status']}\n"
                status_text += f"⏰ Created: {ticket['creation'].strftime('%Y-%m-%d %H:%M')}\n\n"
            
            if len(tickets) > 5:
                status_text += f"... and {len(tickets) - 5} more tickets."
            
            send_message(chat_id, status_text, bot_doc)
        
        return {"success": True, "message": "Status command handled"}
    
    except Exception as e:
        frappe.log_error("Status Command Error", str(e))
        return {"success": False, "message": str(e)}


def handle_tickets_command(message, bot_doc):
    """Handle /tickets command to show detailed ticket list"""
    # Similar to status but with more detail
    return handle_status_command(message, bot_doc)


def handle_status_query(callback_query, bot_doc):
    """Handle status callback queries"""
    # Implementation for callback query handling
    return {"success": True, "message": "Status query handled"}


def handle_ticket_query(callback_query, bot_doc):
    """Handle ticket callback queries"""
    # Implementation for ticket callback query handling
    return {"success": True, "message": "Ticket query handled"}


def check_rate_limiting(update_data, bot_doc):
    """Check if user is rate limited"""
    try:
        message = update_data.get("message", {})
        user_data = message.get("from", {})
        user_id = user_data.get("id")
        
        if not user_id:
            return True  # Allow if no user ID
        
        return not bot_doc.is_rate_limited(user_id)
    
    except Exception:
        return True  # Allow on error


def send_acknowledgment(message, bot_doc):
    """Send acknowledgment message to user"""
    try:
        chat_id = message.get("chat", {}).get("id")
        ack_text = "Thank you for your message! A support ticket has been created and our team will get back to you soon."
        
        # Send in background to avoid blocking webhook response
        frappe.enqueue(
            "helpdesk.www.telegram.webhook.send_message_background",
            chat_id=chat_id,
            text=ack_text,
            bot_token=bot_doc.bot_token,
            queue="short",
            timeout=60
        )
    
    except Exception as e:
        frappe.log_error("Acknowledgment Send Error", str(e))


def send_message(chat_id, text, bot_doc, parse_mode=None):
    """Send message to Telegram chat"""
    try:
        logger.info(f"Sending message to chat {chat_id}")
        logger.debug(f"Message content: '{text[:100]}{'...' if len(text) > 100 else ''}'")
        logger.debug(f"Parse mode: {parse_mode}")
        
        # Send in background to avoid blocking
        frappe.enqueue(
            "helpdesk.www.telegram.webhook.send_message_background",
            chat_id=chat_id,
            text=text,
            bot_token=bot_doc.bot_token,
            parse_mode=parse_mode,
            queue="short",
            timeout=60
        )
        
        logger.debug("Message queued for background sending")
    
    except Exception as e:
        logger.error(f"Message send error: {str(e)}", exc_info=True)
        frappe.log_error("Message Send Error", str(e))


def send_ticket_confirmation(message, ticket_result, bot_doc):
    """Send ticket creation confirmation"""
    try:
        chat_id = message.get("chat", {}).get("id")
        ticket_id = ticket_result.get("ticket")
        
        confirmation_text = f"✅ Ticket Created!\n\n"
        confirmation_text += f"🎫 **Ticket:** {ticket_id}\n"
        confirmation_text += f"📝 **Subject:** {ticket_result.get('subject', 'N/A')}\n"
        confirmation_text += f"⚡ **Priority:** {ticket_result.get('priority', 'Medium')}\n\n"
        confirmation_text += f"Our team will review your request and respond soon.\n\n"
        confirmation_text += f"To check status: `/status {ticket_id}`"
        
        send_message(chat_id, confirmation_text, bot_doc, parse_mode="Markdown")
        
    except Exception as e:
        frappe.log_error("Confirmation Send Error", str(e))


def send_verification_message(message, bot_doc):
    """Send verification required message"""
    try:
        chat_id = message.get("chat", {}).get("id")
        
        verification_text = "⚠️ **Verification Required**\n\n"
        verification_text += "To create tickets, please verify your account first.\n\n"
        verification_text += "Use `/verify` to start the verification process."
        
        send_message(chat_id, verification_text, bot_doc, parse_mode="Markdown")
        
    except Exception as e:
        frappe.log_error("Verification Message Send Error", str(e))


def send_error_message(message, error_result, bot_doc):
    """Send generic error message"""
    try:
        chat_id = message.get("chat", {}).get("id")
        
        error_text = "❌ **Unable to Process Message**\n\n"
        error_text += "Sorry, I couldn't create a ticket from your message. "
        error_text += "Please try again or contact support directly.\n\n"
        error_text += "Use `/help` for available commands."
        
        send_message(chat_id, error_text, bot_doc, parse_mode="Markdown")
        
    except Exception as e:
        frappe.log_error("Error Message Send Error", str(e))


def send_message_background(chat_id, text, bot_token, parse_mode=None):
    """Background job to send message to Telegram"""
    try:
        import requests
        
        logger.info(f"📤 Background job: Sending message to chat {chat_id}")
        
        url = f"https://api.telegram.org/bot{bot_token[:10]}****/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode or "HTML"
        }
        
        logger.debug(f"Telegram API URL: {url}")
        logger.debug(f"Payload: {payload}")
        
        # Use full token for actual request
        full_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(full_url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Message sent successfully to chat {chat_id}")
        else:
            logger.error(f"❌ Failed to send message to chat {chat_id}: HTTP {response.status_code}")
            logger.error(f"Response: {response.text}")
            frappe.log_error("Telegram Send Message Failed", response.text)
    
    except Exception as e:
        logger.error(f"Background message send exception: {str(e)}", exc_info=True)
        frappe.log_error("Background Message Send Error", str(e))


def get_help_text(bot_doc):
    """Get help text for the bot"""
    help_text = "🤖 Helpdesk Bot Commands:\n\n"
    help_text += "/start - Start conversation\n"
    help_text += "/help - Show this help message\n"
    
    if bot_doc.enable_status_commands:
        help_text += "/status - Check your ticket status\n"
        help_text += "/tickets - List your tickets\n"
    
    help_text += "\n💬 Just send me a message to create a support ticket!"
    
    return help_text 