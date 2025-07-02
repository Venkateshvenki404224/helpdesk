# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, add_minutes, get_datetime


def process_pending_messages():
    """Cron job to process pending Telegram messages"""
    try:
        # Get pending messages (not processed for more than 5 minutes)
        five_minutes_ago = add_minutes(now_datetime(), -5)
        
        pending_messages = frappe.get_all(
            "HD Telegram Message",
            filters={
                "is_processed": 0,
                "processing_status": ["in", ["Pending", "Failed"]],
                "received_on": ["<=", five_minutes_ago]
            },
            fields=["name", "processing_status", "error_message"],
            limit=50
        )
        
        if not pending_messages:
            return
        
        frappe.logger().info(f"Processing {len(pending_messages)} pending Telegram messages")
        
        processed_count = 0
        failed_count = 0
        
        for message_data in pending_messages:
            try:
                message_doc = frappe.get_doc("HD Telegram Message", message_data.name)
                
                # Skip if already being processed
                if message_doc.processing_status == "Processing":
                    continue
                
                # Retry failed messages (max 3 attempts)
                if message_data.processing_status == "Failed":
                    failure_count = get_message_failure_count(message_data.name)
                    if failure_count >= 3:
                        continue  # Skip messages that have failed 3+ times
                
                # Process the message
                result = message_doc.process_message()
                
                if result.get("success"):
                    processed_count += 1
                else:
                    failed_count += 1
                    frappe.log_error(
                        f"Message Processing Failed: {message_data.name}",
                        result.get("message", "Unknown error")
                    )
            
            except Exception as e:
                failed_count += 1
                frappe.log_error(f"Message Processing Error: {message_data.name}", str(e))
        
        if processed_count > 0 or failed_count > 0:
            frappe.logger().info(
                f"Telegram message processing completed: "
                f"{processed_count} processed, {failed_count} failed"
            )
    
    except Exception as e:
        frappe.log_error("Telegram Queue Processing Error", str(e))


def cleanup_old_rate_limits():
    """Clean up old rate limit entries from cache"""
    try:
        # Get all Telegram bots
        bots = frappe.get_all("HD Telegram Bot", filters={"is_active": 1}, fields=["name"])
        
        # Get cache instance
        cache = frappe.cache()
        
        # Pattern to match rate limit keys
        cleanup_count = 0
        
        for bot in bots:
            # Get keys matching the pattern
            pattern = f"telegram_rate_limit:{bot.name}:*"
            keys = cache.get_keys(pattern)
            
            for key in keys:
                # Check if key is expired (Redis should handle this automatically)
                # But we can force cleanup of any remaining keys
                if not cache.get(key):
                    cache.delete(key)
                    cleanup_count += 1
        
        if cleanup_count > 0:
            frappe.logger().info(f"Cleaned up {cleanup_count} expired rate limit entries")
    
    except Exception as e:
        frappe.log_error("Rate Limit Cleanup Error", str(e))


def get_message_failure_count(message_name):
    """Get the number of times a message has failed processing"""
    try:
        # Count error logs for this message
        failure_count = frappe.db.count(
            "Error Log",
            filters={
                "title": ["like", f"%{message_name}%"],
                "creation": [">=", add_minutes(now_datetime(), -60)]  # Last hour
            }
        )
        return failure_count
    except:
        return 0


@frappe.whitelist()
def reprocess_failed_messages(hours=24):
    """Manually reprocess failed messages from the last N hours"""
    try:
        hours_ago = add_minutes(now_datetime(), -int(hours) * 60)
        
        failed_messages = frappe.get_all(
            "HD Telegram Message",
            filters={
                "processing_status": "Failed",
                "received_on": [">=", hours_ago]
            },
            fields=["name"],
            limit=100
        )
        
        if not failed_messages:
            return {"success": True, "message": "No failed messages found"}
        
        reprocessed_count = 0
        still_failed_count = 0
        
        for message_data in failed_messages:
            try:
                message_doc = frappe.get_doc("HD Telegram Message", message_data.name)
                result = message_doc.reprocess_message()
                
                if result.get("success"):
                    reprocessed_count += 1
                else:
                    still_failed_count += 1
            
            except Exception as e:
                still_failed_count += 1
                frappe.log_error(f"Manual Reprocessing Error: {message_data.name}", str(e))
        
        return {
            "success": True,
            "message": f"Reprocessed {reprocessed_count} messages, {still_failed_count} still failed",
            "reprocessed": reprocessed_count,
            "failed": still_failed_count
        }
    
    except Exception as e:
        frappe.log_error("Manual Reprocessing Error", str(e))
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_queue_status():
    """Get status of Telegram message processing queue"""
    try:
        # Get queue statistics
        pending_count = frappe.db.count(
            "HD Telegram Message",
            filters={"processing_status": "Pending"}
        )
        
        processing_count = frappe.db.count(
            "HD Telegram Message",
            filters={"processing_status": "Processing"}
        )
        
        failed_count = frappe.db.count(
            "HD Telegram Message",
            filters={
                "processing_status": "Failed",
                "received_on": [">=", add_minutes(now_datetime(), -60)]  # Last hour
            }
        )
        
        completed_today = frappe.db.count(
            "HD Telegram Message",
            filters={
                "processing_status": "Completed",
                "processed_on": [">=", frappe.utils.today()]
            }
        )
        
        # Get recent failures
        recent_failures = frappe.get_all(
            "HD Telegram Message",
            filters={
                "processing_status": "Failed",
                "received_on": [">=", add_minutes(now_datetime(), -30)]  # Last 30 minutes
            },
            fields=["name", "error_message", "received_on", "telegram_user"],
            order_by="received_on desc",
            limit=10
        )
        
        return {
            "success": True,
            "queue_status": {
                "pending": pending_count,
                "processing": processing_count,
                "failed_last_hour": failed_count,
                "completed_today": completed_today
            },
            "recent_failures": recent_failures
        }
    
    except Exception as e:
        frappe.log_error("Queue Status Error", str(e))
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def retry_stuck_messages():
    """Retry messages that are stuck in 'Processing' status"""
    try:
        # Find messages stuck in processing for more than 10 minutes
        ten_minutes_ago = add_minutes(now_datetime(), -10)
        
        stuck_messages = frappe.get_all(
            "HD Telegram Message",
            filters={
                "processing_status": "Processing",
                "modified": ["<=", ten_minutes_ago]
            },
            fields=["name"],
            limit=50
        )
        
        if not stuck_messages:
            return {"success": True, "message": "No stuck messages found"}
        
        retried_count = 0
        
        for message_data in stuck_messages:
            try:
                message_doc = frappe.get_doc("HD Telegram Message", message_data.name)
                
                # Reset status to pending
                message_doc.processing_status = "Pending"
                message_doc.error_message = "Retrying stuck message"
                message_doc.save()
                
                retried_count += 1
            
            except Exception as e:
                frappe.log_error(f"Stuck Message Retry Error: {message_data.name}", str(e))
        
        return {
            "success": True,
            "message": f"Reset {retried_count} stuck messages to pending",
            "retried": retried_count
        }
    
    except Exception as e:
        frappe.log_error("Stuck Message Retry Error", str(e))
        return {"success": False, "message": str(e)}


def enqueue_telegram_message_processing(message_name, priority="default"):
    """Enqueue a Telegram message for background processing"""
    try:
        frappe.enqueue(
            "helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message.process_message_background",
            message_name=message_name,
            queue=priority,
            timeout=300,
            is_async=True
        )
        return True
    except Exception as e:
        frappe.log_error("Message Queue Enqueue Error", str(e))
        return False


def enqueue_telegram_notification(telegram_user_id, message, bot_name=None, priority="short"):
    """Enqueue a Telegram notification for background sending"""
    try:
        frappe.enqueue(
            "helpdesk.helpdesk.utils.telegram_client.send_notification_background",
            telegram_user_id=telegram_user_id,
            message=message,
            bot_name=bot_name,
            queue=priority,
            timeout=60,
            is_async=True
        )
        return True
    except Exception as e:
        frappe.log_error("Notification Queue Enqueue Error", str(e))
        return False 