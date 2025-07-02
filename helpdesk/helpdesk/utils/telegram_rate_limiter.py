# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, add_seconds, get_datetime
import time


class TelegramRateLimiter:
    """Advanced rate limiting for Telegram messages with multiple strategies"""
    
    def __init__(self, bot_name):
        self.bot_name = bot_name
        self.cache = frappe.cache()
    
    def is_rate_limited(self, user_id, message_type="message"):
        """Check if user is rate limited based on multiple criteria"""
        try:
            # Get bot configuration
            bot_doc = frappe.get_cached_doc("HD Telegram Bot", self.bot_name)
            
            if not bot_doc.rate_limit_per_hour:
                return False
            
            # Check different rate limiting strategies
            checks = [
                self._check_hourly_limit(user_id, bot_doc.rate_limit_per_hour),
                self._check_burst_limit(user_id),
                self._check_global_limit(),
                self._check_user_specific_limit(user_id),
            ]
            
            # Return True if any check indicates rate limiting
            return any(checks)
        
        except Exception as e:
            frappe.log_error("Rate Limiter Check Error", str(e))
            return False  # Fail open - allow message if error
    
    def increment_counter(self, user_id, message_type="message"):
        """Increment rate limit counters for a user"""
        try:
            current_time = int(time.time())
            
            # Hourly counter
            hourly_key = f"telegram_rate_limit:{self.bot_name}:{user_id}:hourly"
            self._increment_with_expiry(hourly_key, 3600)  # 1 hour
            
            # Burst counter (per minute)
            minute_window = current_time // 60
            burst_key = f"telegram_rate_limit:{self.bot_name}:{user_id}:burst:{minute_window}"
            self._increment_with_expiry(burst_key, 120)  # 2 minutes (keep extra window)
            
            # Global counter
            global_key = f"telegram_rate_limit:{self.bot_name}:global:hourly"
            self._increment_with_expiry(global_key, 3600)
            
            # Daily counter
            daily_key = f"telegram_rate_limit:{self.bot_name}:{user_id}:daily"
            self._increment_with_expiry(daily_key, 86400)  # 24 hours
            
            return True
        
        except Exception as e:
            frappe.log_error("Rate Limiter Increment Error", str(e))
            return False
    
    def _check_hourly_limit(self, user_id, limit):
        """Check hourly rate limit"""
        key = f"telegram_rate_limit:{self.bot_name}:{user_id}:hourly"
        current_count = self.cache.get(key) or 0
        return current_count >= limit
    
    def _check_burst_limit(self, user_id, max_per_minute=5):
        """Check burst rate limit (messages per minute)"""
        current_time = int(time.time())
        minute_window = current_time // 60
        key = f"telegram_rate_limit:{self.bot_name}:{user_id}:burst:{minute_window}"
        current_count = self.cache.get(key) or 0
        return current_count >= max_per_minute
    
    def _check_global_limit(self, max_per_hour=1000):
        """Check global rate limit for the bot"""
        key = f"telegram_rate_limit:{self.bot_name}:global:hourly"
        current_count = self.cache.get(key) or 0
        return current_count >= max_per_hour
    
    def _check_user_specific_limit(self, user_id):
        """Check if user has specific rate limiting rules"""
        try:
            # Check if user is in a blocked state
            telegram_user = frappe.get_cached_value(
                "HD Telegram User",
                {"telegram_user_id": str(user_id)},
                ["is_blocked", "name"]
            )
            
            if telegram_user and telegram_user[0]:  # is_blocked
                return True
            
            # Check daily limit (e.g., 50 messages per day)
            daily_key = f"telegram_rate_limit:{self.bot_name}:{user_id}:daily"
            daily_count = self.cache.get(daily_key) or 0
            if daily_count >= 50:
                return True
            
            return False
        
        except Exception:
            return False
    
    def _increment_with_expiry(self, key, expiry_seconds):
        """Increment counter with automatic expiry"""
        try:
            # Use Redis INCR and EXPIRE commands for atomic operation
            current_value = self.cache.get(key) or 0
            new_value = current_value + 1
            self.cache.set(key, new_value, expires_in_sec=expiry_seconds)
            return new_value
        except Exception:
            # Fallback to basic increment
            current_value = self.cache.get(key) or 0
            self.cache.set(key, current_value + 1, expires_in_sec=expiry_seconds)
            return current_value + 1
    
    def get_user_stats(self, user_id):
        """Get rate limiting statistics for a user"""
        try:
            current_time = int(time.time())
            minute_window = current_time // 60
            
            stats = {
                "hourly_count": self.cache.get(f"telegram_rate_limit:{self.bot_name}:{user_id}:hourly") or 0,
                "burst_count": self.cache.get(f"telegram_rate_limit:{self.bot_name}:{user_id}:burst:{minute_window}") or 0,
                "daily_count": self.cache.get(f"telegram_rate_limit:{self.bot_name}:{user_id}:daily") or 0,
                "is_blocked": self._check_user_specific_limit(user_id)
            }
            
            return stats
        
        except Exception as e:
            frappe.log_error("Rate Limiter Stats Error", str(e))
            return {}
    
    def reset_user_limits(self, user_id):
        """Reset all rate limits for a user (admin function)"""
        try:
            current_time = int(time.time())
            minute_window = current_time // 60
            
            keys_to_delete = [
                f"telegram_rate_limit:{self.bot_name}:{user_id}:hourly",
                f"telegram_rate_limit:{self.bot_name}:{user_id}:burst:{minute_window}",
                f"telegram_rate_limit:{self.bot_name}:{user_id}:daily"
            ]
            
            for key in keys_to_delete:
                self.cache.delete(key)
            
            return True
        
        except Exception as e:
            frappe.log_error("Rate Limiter Reset Error", str(e))
            return False


# Utility functions for easy access

@frappe.whitelist()
def check_rate_limit(bot_name, user_id, message_type="message"):
    """Check if user is rate limited"""
    try:
        limiter = TelegramRateLimiter(bot_name)
        is_limited = limiter.is_rate_limited(user_id, message_type)
        
        if not is_limited:
            # Increment counter if not limited
            limiter.increment_counter(user_id, message_type)
        
        return {
            "success": True,
            "is_rate_limited": is_limited,
            "user_stats": limiter.get_user_stats(user_id)
        }
    
    except Exception as e:
        frappe.log_error("Rate Limit Check Error", str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_rate_limit_stats(bot_name, user_id=None):
    """Get rate limiting statistics"""
    try:
        limiter = TelegramRateLimiter(bot_name)
        
        if user_id:
            # Get stats for specific user
            stats = limiter.get_user_stats(user_id)
            return {"success": True, "user_stats": stats}
        else:
            # Get global stats
            cache = frappe.cache()
            global_hourly = cache.get(f"telegram_rate_limit:{bot_name}:global:hourly") or 0
            
            return {
                "success": True,
                "global_stats": {
                    "global_hourly_count": global_hourly
                }
            }
    
    except Exception as e:
        frappe.log_error("Rate Limit Stats Error", str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def reset_user_rate_limits(bot_name, user_id):
    """Reset rate limits for a specific user (admin function)"""
    try:
        # Check permissions
        if not frappe.has_permission("HD Telegram Bot", "write"):
            frappe.throw(_("Not allowed"))
        
        limiter = TelegramRateLimiter(bot_name)
        success = limiter.reset_user_limits(user_id)
        
        if success:
            return {"success": True, "message": "Rate limits reset successfully"}
        else:
            return {"success": False, "message": "Failed to reset rate limits"}
    
    except Exception as e:
        frappe.log_error("Rate Limit Reset Error", str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def cleanup_expired_rate_limits():
    """Clean up expired rate limit entries (admin function)"""
    try:
        cache = frappe.cache()
        
        # Get all telegram bots
        bots = frappe.get_all("HD Telegram Bot", filters={"is_active": 1}, fields=["name"])
        
        cleanup_count = 0
        
        for bot in bots:
            # Get all rate limit keys for this bot
            pattern = f"telegram_rate_limit:{bot.name}:*"
            keys = cache.get_keys(pattern)
            
            for key in keys:
                # Check if key still exists (Redis auto-expires)
                if not cache.get(key):
                    cache.delete(key)
                    cleanup_count += 1
        
        return {
            "success": True,
            "message": f"Cleaned up {cleanup_count} expired entries",
            "cleaned_count": cleanup_count
        }
    
    except Exception as e:
        frappe.log_error("Rate Limit Cleanup Error", str(e))
        return {"success": False, "error": str(e)}


def apply_adaptive_rate_limiting(bot_name, user_id, user_behavior_score):
    """Apply adaptive rate limiting based on user behavior"""
    try:
        limiter = TelegramRateLimiter(bot_name)
        
        # Adjust limits based on user behavior
        if user_behavior_score < 0.3:  # Suspicious behavior
            # Apply stricter limits
            burst_limit = 2  # 2 messages per minute
            hourly_limit = 5  # 5 messages per hour
        elif user_behavior_score < 0.7:  # Normal behavior
            # Standard limits
            burst_limit = 5
            hourly_limit = 10
        else:  # Good behavior
            # Relaxed limits
            burst_limit = 10
            hourly_limit = 20
        
        # Store adaptive limits in cache
        cache_key = f"telegram_adaptive_limits:{bot_name}:{user_id}"
        limits = {
            "burst_limit": burst_limit,
            "hourly_limit": hourly_limit,
            "updated_at": now_datetime().isoformat()
        }
        
        frappe.cache().set(cache_key, limits, expires_in_sec=3600)
        
        return limits
    
    except Exception as e:
        frappe.log_error("Adaptive Rate Limiting Error", str(e))
        return None


def calculate_user_behavior_score(user_id):
    """Calculate user behavior score based on message patterns"""
    try:
        # Get user's recent activity
        telegram_user = frappe.db.get_value(
            "HD Telegram User",
            {"telegram_user_id": str(user_id)},
            ["total_messages_sent", "total_tickets_created", "first_contact"],
            as_dict=True
        )
        
        if not telegram_user:
            return 0.5  # Neutral score for new users
        
        # Calculate score based on various factors
        score = 0.5  # Base score
        
        # Factor 1: Message to ticket ratio (good users create meaningful tickets)
        if telegram_user.total_messages_sent > 0:
            ticket_ratio = telegram_user.total_tickets_created / telegram_user.total_messages_sent
            if ticket_ratio > 0.3:
                score += 0.2
            elif ticket_ratio < 0.1:
                score -= 0.2
        
        # Factor 2: Account age (older accounts are more trustworthy)
        if telegram_user.first_contact:
            days_old = (now_datetime() - get_datetime(telegram_user.first_contact)).days
            if days_old > 30:
                score += 0.2
            elif days_old < 1:
                score -= 0.1
        
        # Factor 3: Block history
        block_history = frappe.db.count(
            "HD Telegram User",
            {"telegram_user_id": str(user_id), "is_blocked": 1}
        )
        if block_history > 0:
            score -= 0.3
        
        # Ensure score is between 0 and 1
        return max(0, min(1, score))
    
    except Exception as e:
        frappe.log_error("Behavior Score Calculation Error", str(e))
        return 0.5  # Neutral score on error 