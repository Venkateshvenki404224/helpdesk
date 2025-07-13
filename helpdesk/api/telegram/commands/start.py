# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime
from typing import Dict, Any



def handle_start(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /start command: Register a Telegram user and send confirmation.
    Args:
        params: Dictionary containing at least 'user_data' and 'bot_doc'.
    Returns:
        Dict with registration result and response message.
    """
    try:
        user_data = params.get("user_data", {})
        bot_doc = params.get("bot_doc")

        # Extract relevant fields from user_data
        telegram_user_id = user_data.get("id")
        username = user_data.get("username", "")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        language_code = user_data.get("language_code", "")
        is_bot = int(user_data.get("is_bot", 0))
        is_premium = int(user_data.get("is_premium", 0))
        preferred_language = user_data.get("preferred_language", language_code)

        # Create or update the Telegram user
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
        telegram_user = get_or_create_telegram_user(user_data)
        telegram_user.update_last_contact()

        # Try to use registration template
        try:
            template_doc = frappe.get_doc("HD Bot Response Template", "registration_success")
            if template_doc.is_active:
                # Prepare context for template
                user_name = f"{first_name} {last_name}".strip() or username or f"User {telegram_user_id}"
                context = {
                    "user_name": user_name,
                    "bot_name": bot_doc.bot_name if bot_doc else "Support Bot",
                    "telegram_user_id": telegram_user_id,
                    "registration_time": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
                    "company_name": bot_doc.company_name if bot_doc else "Our Company",
                    "response_time": "2-4 hours",
                    "support_hours": "24/7"
                }
                
                # Render template
                result = template_doc.render(context)
                if result.get("content"):
                    return {
                        "success": True,
                        "message": result.get("content"),
                        "parse_mode": result.get("parse_mode", "HTML"),
                        "telegram_user_id": telegram_user_id,
                        "template_used": "registration_success"
                    }
        except frappe.DoesNotExistError:
            pass  # Fall back to default message
        
        # Fallback to default registration message
        message = (
            f"👋 Hello, <b>{first_name or username or telegram_user_id}</b>!\n\n"
            f"You have been successfully registered with <b>{bot_doc.bot_name if bot_doc else 'Support Bot'}</b>.\n"
            f"Your account is now active.\n\n"
            f"Type /help to see available commands or start interacting with the bot!"
        )

        return {
            "success": True,
            "message": message,
            "parse_mode": "HTML",
            "telegram_user_id": telegram_user_id,
        }

    except Exception as e:
        frappe.log_error(f"Register command failed: {str(e)}")
        return {
            "success": False,
            "message": f"❌ Registration failed: {str(e)}",
        } 