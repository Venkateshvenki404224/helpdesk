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
        logger.error(f"Webhook handler exception: {str(e)}")
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
        logger.error(f"Webhook validation exception: {str(e)}")
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
        logger.error(f"Update processing exception: {str(e)}")
        frappe.log_error("Update Processing Error", str(e))
        return {"success": False, "message": str(e)}


def process_message(update_data, bot_doc):
    """Process incoming message using new command processing system"""
    try:
        message = update_data.get("message", {})
        user_data = message.get("from", {})
        message_text = message.get("text", "")
        user_id = user_data.get("id")
        chat_id = message.get("chat", {}).get("id")
        
        logger.info(f"🔄 Processing message from user {user_id} in chat {chat_id}")
        logger.debug(f"Message text: '{message_text[:100]}{'...' if len(message_text) > 100 else ''}'")
        
        # Update bot statistics
        logger.debug("Updating bot message count...")
        bot_doc.increment_message_count()
        
        # Use new Command Processing System
        logger.info("🚀 Using new Command Processing System...")
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
            
            logger.debug("✅ Command processing utilities imported successfully")
            
            # Initialize processors
            command_processor = TelegramCommandProcessor(bot_doc)
            response_manager = BotResponseManager(bot_doc)
            
            # Process message through command processor
            logger.debug(f"Processing message through command processor...")
            result = command_processor.process_message(message, user_data)
            logger.debug(f"Command processor returned: {result}")
            
            # Handle the result
            if result.get("success"):
                # Get response from response manager
                response_data = result.get("response_data", {})
                template_name = response_data.get("template_name")
                context = response_data.get("context", {})
                
                if template_name:
                    logger.debug(f"Rendering template: {template_name}")
                    response_message = response_manager.render_template(template_name, context)
                    
                    if response_message:
                        logger.debug(f"📤 Sending response: '{response_message[:100]}{'...' if len(response_message) > 100 else ''}'")
                        send_message(chat_id, response_message, bot_doc, parse_mode="Markdown")
                else:
                    # Direct response message
                    response_message = result.get("response_message")
                    if response_message:
                        logger.debug(f"\U0001F4E4 Sending direct response: '{response_message[:100]}{'...' if len(response_message) > 100 else ''}'")
                        send_message(chat_id, response_message, bot_doc, parse_mode="Markdown")
                    elif result.get("message"):
                        logger.debug(f"\U0001F4E4 Sending fallback message: '{result.get('message')[:100]}{'...' if len(result.get('message')) > 100 else ''}'")
                        send_message(chat_id, result.get("message"), bot_doc, parse_mode="Markdown")
                
                # Handle special cases
                if result.get("ticket_created"):
                    ticket_id = result.get("ticket_id")
                    logger.info(f"✅ Ticket {ticket_id} created through command flow")
                
                if result.get("welcome_sent"):
                    logger.info(f"👋 Welcome message sent to new user")
                    
            else:
                # Handle command processing errors
                error_type = result.get("error", "unknown")
                error_message = result.get("message", "Unknown error")
                logger.warning(f"❌ Command processing failed: {error_type} - {error_message}")
                
                # Send error response using response manager
                error_response = response_manager.render_template("error_general", {
                    "error_message": error_message
                })
                
                if error_response:
                    send_message(chat_id, error_response, bot_doc, parse_mode="Markdown")
                else:
                    # Fallback error message
                    fallback_message = "❌ Sorry, I couldn't process your message. Please try again or type /help for available commands."
                    send_message(chat_id, fallback_message, bot_doc)
            
        except Exception as e:
            logger.error(f"❌ Error in command processing system: {str(e)}")
            
            # Fallback to legacy system if available
            logger.info("🔄 Falling back to legacy processing...")
            try:
                from helpdesk.helpdesk.utils.interactive_flow_handler import handle_interactive_message
                result = handle_interactive_message(message, bot_doc)
                
                if result.get("success"):
                    response_message = result.get("response_message")
                    if response_message:
                        send_message(chat_id, response_message, bot_doc, parse_mode="Markdown")
                else:
                    # Emergency fallback
                    fallback_message = "Sorry, I'm having trouble processing your message. Please try again or contact support."
                    send_message(chat_id, fallback_message, bot_doc)
                
            except Exception as fallback_error:
                logger.error(f"❌ Legacy fallback also failed: {str(fallback_error)}")
                
                # Final emergency response
                emergency_message = "Sorry, there was an error processing your message. Please try again later."
                send_message(chat_id, emergency_message, bot_doc)
                
                result = {"success": False, "message": str(e)}
        
        return result
    
    except Exception as e:
        logger.error(f"Message processing exception: {str(e)}")
        frappe.log_error("Message Processing Error", str(e))
        
        # Emergency fallback
        try:
            message = update_data.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            if chat_id:
                emergency_message = "Sorry, there was an error processing your message. Please try again."
                send_message(chat_id, emergency_message, bot_doc)
        except:
            pass  # Don't let secondary errors break the flow
        
        return {"success": False, "message": str(e)}


def process_callback_query(update_data, bot_doc):
    """Process callback query (inline keyboard responses)"""
    try:
        callback_query = update_data.get("callback_query", {})
        callback_data = callback_query.get("data", "")
        
        logger.info(f"Processing callback query: {callback_data}")
        
        # Use command processor for callback queries too
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
            
            command_processor = TelegramCommandProcessor(bot_doc)
            response_manager = BotResponseManager(bot_doc)
            
            # Process callback query
            result = command_processor.process_callback_query(callback_query)
            
            if result.get("success"):
                # Send response if provided
                response_data = result.get("response_data", {})
                template_name = response_data.get("template_name")
                context = response_data.get("context", {})
                
                if template_name:
                    response_message = response_manager.render_template(template_name, context)
                    if response_message:
                        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
                        send_message(chat_id, response_message, bot_doc, parse_mode="Markdown")
                
                # Answer callback query
                answer_callback_query(callback_query.get("id"), result.get("callback_answer", ""))
                
            return result
            
        except Exception as e:
            logger.error(f"Callback query processing error: {str(e)}")
            
            # Answer callback query with error
            answer_callback_query(callback_query.get("id"), "Error processing request")
            
            return {"success": False, "message": str(e)}
    
    except Exception as e:
        frappe.log_error("Callback Query Processing Error", str(e))
        return {"success": False, "message": str(e)}


def process_edited_message(update_data, bot_doc):
    """Process edited message"""
    try:
        # For now, we'll just log edited messages
        # In the future, we might want to update the original ticket
        logger.info("Edited message received - logging for future processing")
        frappe.log_error("Message Edited", json.dumps(update_data, indent=2))
        return {"success": True, "message": "Edit logged"}
    
    except Exception as e:
        frappe.log_error("Edited Message Processing Error", str(e))
        return {"success": False, "message": str(e)}


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
        logger.error(f"Message send error: {str(e)}")
        frappe.log_error("Message Send Error", str(e))


def answer_callback_query(callback_query_id, text=""):
    """Answer callback query to remove loading state"""
    try:
        logger.debug(f"Answering callback query: {callback_query_id}")
        
        # This would be implemented with the Telegram API
        # For now, just log it
        logger.info(f"Callback query answered: {text}")
        
    except Exception as e:
        logger.error(f"Callback query answer error: {str(e)}")
        frappe.log_error("Callback Query Answer Error", str(e))


def send_message_background(chat_id, text, bot_token, parse_mode=None):
    """Background job to send message to Telegram"""
    try:
        import requests
        
        logger.info(f"📤 Background job: Sending message to chat {chat_id}")
        
        url = f"https://api.telegram.org/bot{bot_token[:10]}****/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode or "Markdown"
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
        logger.error(f"Background message send exception: {str(e)}")
        frappe.log_error("Background Message Send Error", str(e)) 