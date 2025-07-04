# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
import time
import traceback
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, List, Optional, Union
import unittest
from unittest.mock import Mock, patch


class TelegramBotTester:
    """
    Comprehensive testing utility for Telegram bot system.
    Tests command processing, response templates, routing, and integration scenarios.
    """
    
    def __init__(self, bot_name: str = None):
        """
        Initialize the tester
        
        Args:
            bot_name: Name of the bot to test
        """
        self.bot_name = bot_name
        self.bot_doc = None
        self.test_results = []
        self.performance_metrics = {}
        
        # Initialize bot document
        if bot_name:
            try:
                self.bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
            except frappe.DoesNotExistError:
                frappe.throw(_("Bot '{0}' not found").format(bot_name))
    
    def run_comprehensive_tests(self) -> Dict[str, Any]:
        """
        Run comprehensive test suite
        
        Returns:
            Dict containing all test results
        """
        test_suites = [
            ("Command Processing Tests", self.test_command_processing),
            ("Response Template Tests", self.test_response_templates),
            ("Command Router Tests", self.test_command_router),
            ("Welcome Message Tests", self.test_welcome_messages),
            ("Permission System Tests", self.test_permission_system),
            ("Error Handling Tests", self.test_error_handling),
            ("Performance Tests", self.test_performance),
            ("Integration Tests", self.test_integration_flow)
        ]
        
        overall_start_time = time.time()
        
        for suite_name, test_function in test_suites:
            try:
                self._log_test_start(suite_name)
                suite_start_time = time.time()
                
                result = test_function()
                
                suite_end_time = time.time()
                execution_time = suite_end_time - suite_start_time
                
                self._log_test_result(suite_name, result, execution_time)
                
            except Exception as e:
                self._log_test_error(suite_name, str(e), traceback.format_exc())
        
        overall_end_time = time.time()
        total_execution_time = overall_end_time - overall_start_time
        
        return {
            "success": True,
            "bot_name": self.bot_name,
            "test_results": self.test_results,
            "performance_metrics": self.performance_metrics,
            "total_execution_time": total_execution_time,
            "timestamp": now_datetime().isoformat(),
            "summary": self._generate_test_summary()
        }
    
    def test_command_processing(self) -> Dict[str, Any]:
        """Test command processing functionality"""
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            
            processor = TelegramCommandProcessor(self.bot_doc)
            test_cases = self._get_command_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    result = processor.process_message(
                        test_case["message_data"],
                        test_case["user_data"]
                    )
                    
                    execution_time = time.time() - start_time
                    
                    test_result = {
                        "test_case": test_case["name"],
                        "success": result.get("success", False),
                        "execution_time": execution_time,
                        "result": result,
                        "expected": test_case.get("expected", {})
                    }
                    
                    # Validate result against expected values
                    if test_case.get("expected"):
                        test_result["validation"] = self._validate_result(result, test_case["expected"])
                    
                    results.append(test_result)
                    
                except Exception as e:
                    results.append({
                        "test_case": test_case["name"],
                        "success": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Command Processing Tests",
                "results": results,
                "passed": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Command Processing Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_response_templates(self) -> Dict[str, Any]:
        """Test response template system"""
        try:
            from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
            
            response_manager = BotResponseManager(self.bot_doc)
            test_cases = self._get_template_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    result = response_manager.render_template(
                        test_case["template_name"],
                        test_case["context"]
                    )
                    
                    execution_time = time.time() - start_time
                    
                    results.append({
                        "test_case": test_case["name"],
                        "template_name": test_case["template_name"],
                        "success": result.get("success", False),
                        "execution_time": execution_time,
                        "result": result
                    })
                    
                except Exception as e:
                    results.append({
                        "test_case": test_case["name"],
                        "template_name": test_case["template_name"],
                        "success": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Response Template Tests",
                "results": results,
                "passed": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Response Template Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_command_router(self) -> Dict[str, Any]:
        """Test command router functionality"""
        try:
            from helpdesk.helpdesk.utils.command_router import CommandRouter
            
            router = CommandRouter(self.bot_doc)
            test_cases = self._get_router_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    result = router.route_message(
                        test_case["message_data"],
                        test_case["user_data"]
                    )
                    
                    execution_time = time.time() - start_time
                    
                    results.append({
                        "test_case": test_case["name"],
                        "success": result.get("success", False),
                        "execution_time": execution_time,
                        "result": result
                    })
                    
                except Exception as e:
                    results.append({
                        "test_case": test_case["name"],
                        "success": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            # Test router statistics
            stats = router.get_route_stats()
            
            return {
                "success": True,
                "test_name": "Command Router Tests",
                "results": results,
                "router_stats": stats,
                "passed": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Command Router Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_welcome_messages(self) -> Dict[str, Any]:
        """Test welcome message functionality"""
        try:
            from helpdesk.helpdesk.utils.welcome_message_handler import WelcomeMessageHandler
            
            welcome_handler = WelcomeMessageHandler(self.bot_doc)
            test_cases = self._get_welcome_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    result = welcome_handler.handle_welcome_message(
                        test_case["user_data"],
                        test_case.get("message_data")
                    )
                    
                    execution_time = time.time() - start_time
                    
                    results.append({
                        "test_case": test_case["name"],
                        "success": result.get("success", False),
                        "execution_time": execution_time,
                        "is_new_user": result.get("is_new_user"),
                        "welcome_sent": result.get("welcome_sent"),
                        "result": result
                    })
                    
                except Exception as e:
                    results.append({
                        "test_case": test_case["name"],
                        "success": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Welcome Message Tests",
                "results": results,
                "passed": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Welcome Message Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_permission_system(self) -> Dict[str, Any]:
        """Test permission and access level system"""
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            
            processor = TelegramCommandProcessor(self.bot_doc)
            test_cases = self._get_permission_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    # Test command with different access levels
                    result = processor.process_message(
                        test_case["message_data"],
                        test_case["user_data"]
                    )
                    
                    execution_time = time.time() - start_time
                    expected_success = test_case.get("should_succeed", True)
                    actual_success = result.get("success", False)
                    
                    test_passed = (expected_success == actual_success)
                    
                    results.append({
                        "test_case": test_case["name"],
                        "test_passed": test_passed,
                        "expected_success": expected_success,
                        "actual_success": actual_success,
                        "execution_time": execution_time,
                        "user_access_level": test_case["user_data"].get("access_level"),
                        "result": result
                    })
                    
                except Exception as e:
                    results.append({
                        "test_case": test_case["name"],
                        "test_passed": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Permission System Tests",
                "results": results,
                "passed": len([r for r in results if r.get("test_passed")]),
                "failed": len([r for r in results if not r.get("test_passed")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Permission System Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_error_handling(self) -> Dict[str, Any]:
        """Test error handling and recovery"""
        try:
            test_cases = self._get_error_test_cases()
            results = []
            
            for test_case in test_cases:
                start_time = time.time()
                
                try:
                    # Simulate various error conditions
                    result = self._simulate_error_condition(test_case)
                    
                    execution_time = time.time() - start_time
                    
                    # Check if error was handled gracefully
                    graceful_handling = (
                        result.get("success") is False and
                        result.get("message") and
                        "error_type" in result
                    )
                    
                    results.append({
                        "test_case": test_case["name"],
                        "error_condition": test_case["condition"],
                        "graceful_handling": graceful_handling,
                        "execution_time": execution_time,
                        "result": result
                    })
                    
                except Exception as e:
                    # Even exceptions should be handled gracefully
                    results.append({
                        "test_case": test_case["name"],
                        "error_condition": test_case["condition"],
                        "graceful_handling": False,
                        "unhandled_exception": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Error Handling Tests",
                "results": results,
                "passed": len([r for r in results if r.get("graceful_handling")]),
                "failed": len([r for r in results if not r.get("graceful_handling")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Error Handling Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_performance(self) -> Dict[str, Any]:
        """Test performance and response times"""
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            
            processor = TelegramCommandProcessor(self.bot_doc)
            
            # Performance test scenarios
            scenarios = [
                {
                    "name": "Simple Command Processing",
                    "iterations": 100,
                    "message_data": {"text": "/help"},
                    "user_data": {"id": "test_user", "first_name": "Test"}
                },
                {
                    "name": "Complex Command with Arguments",
                    "iterations": 50,
                    "message_data": {"text": "/status ticket-123 detailed"},
                    "user_data": {"id": "test_user", "first_name": "Test"}
                },
                {
                    "name": "Template Rendering",
                    "iterations": 100,
                    "message_data": {"text": "/start"},
                    "user_data": {"id": "new_user", "first_name": "New"}
                }
            ]
            
            performance_results = []
            
            for scenario in scenarios:
                times = []
                
                for i in range(scenario["iterations"]):
                    start_time = time.time()
                    
                    try:
                        result = processor.process_message(
                            scenario["message_data"],
                            scenario["user_data"]
                        )
                        execution_time = time.time() - start_time
                        times.append(execution_time)
                        
                    except Exception as e:
                        # Count failed iterations
                        times.append(float('inf'))
                
                # Calculate statistics
                valid_times = [t for t in times if t != float('inf')]
                
                if valid_times:
                    avg_time = sum(valid_times) / len(valid_times)
                    min_time = min(valid_times)
                    max_time = max(valid_times)
                    
                    performance_results.append({
                        "scenario": scenario["name"],
                        "iterations": scenario["iterations"],
                        "successful_iterations": len(valid_times),
                        "average_time": avg_time,
                        "min_time": min_time,
                        "max_time": max_time,
                        "success_rate": len(valid_times) / scenario["iterations"] * 100
                    })
            
            # Store performance metrics
            self.performance_metrics.update({
                "command_processing": performance_results
            })
            
            return {
                "success": True,
                "test_name": "Performance Tests",
                "results": performance_results,
                "overall_metrics": self._calculate_overall_metrics(performance_results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Performance Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def test_integration_flow(self) -> Dict[str, Any]:
        """Test complete integration flow from webhook to response"""
        try:
            # Simulate complete webhook processing
            test_scenarios = [
                {
                    "name": "New User Start Command Flow",
                    "webhook_data": {
                        "message": {
                            "message_id": 123,
                            "from": {
                                "id": 999999,
                                "first_name": "Integration",
                                "username": "test_user"
                            },
                            "chat": {"id": 999999},
                            "text": "/start",
                            "date": int(time.time())
                        }
                    }
                },
                {
                    "name": "Help Command Flow",
                    "webhook_data": {
                        "message": {
                            "message_id": 124,
                            "from": {
                                "id": 999999,
                                "first_name": "Integration",
                                "username": "test_user"
                            },
                            "chat": {"id": 999999},
                            "text": "/help",
                            "date": int(time.time())
                        }
                    }
                },
                {
                    "name": "Non-Command Message Flow",
                    "webhook_data": {
                        "message": {
                            "message_id": 125,
                            "from": {
                                "id": 999999,
                                "first_name": "Integration",
                                "username": "test_user"
                            },
                            "chat": {"id": 999999},
                            "text": "I need help with my account",
                            "date": int(time.time())
                        }
                    }
                }
            ]
            
            results = []
            
            for scenario in test_scenarios:
                start_time = time.time()
                
                try:
                    # Simulate webhook processing
                    result = self._simulate_webhook_processing(scenario["webhook_data"])
                    
                    execution_time = time.time() - start_time
                    
                    results.append({
                        "scenario": scenario["name"],
                        "success": result.get("success", False),
                        "execution_time": execution_time,
                        "result": result
                    })
                    
                except Exception as e:
                    results.append({
                        "scenario": scenario["name"],
                        "success": False,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    })
            
            return {
                "success": True,
                "test_name": "Integration Flow Tests",
                "results": results,
                "passed": len([r for r in results if r.get("success")]),
                "failed": len([r for r in results if not r.get("success")]),
                "total": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "test_name": "Integration Flow Tests",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def _get_command_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for command processing"""
        return [
            {
                "name": "Start Command",
                "message_data": {"text": "/start"},
                "user_data": {"id": "test_user_1", "first_name": "Test"},
                "expected": {"success": True}
            },
            {
                "name": "Help Command",
                "message_data": {"text": "/help"},
                "user_data": {"id": "test_user_2", "first_name": "Test"},
                "expected": {"success": True}
            },
            {
                "name": "Status Command with Arguments",
                "message_data": {"text": "/status ticket-123"},
                "user_data": {"id": "test_user_3", "first_name": "Test"},
                "expected": {"success": True}
            },
            {
                "name": "Unknown Command",
                "message_data": {"text": "/unknown_command"},
                "user_data": {"id": "test_user_4", "first_name": "Test"},
                "expected": {"success": False}
            },
            {
                "name": "Non-Command Message",
                "message_data": {"text": "Hello, I need help"},
                "user_data": {"id": "test_user_5", "first_name": "Test"},
                "expected": {"success": True}
            }
        ]
    
    def _get_template_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for template rendering"""
        return [
            {
                "name": "Welcome Message Template",
                "template_name": "welcome_message",
                "context": {
                    "user_name": "Test User",
                    "bot_name": "Test Bot"
                }
            },
            {
                "name": "Help Message Template",
                "template_name": "help_message",
                "context": {
                    "bot_name": "Test Bot",
                    "commands_list": "/start - Get started\n/help - Show help"
                }
            },
            {
                "name": "Error Message Template",
                "template_name": "error_general",
                "context": {
                    "error_message": "Test error message"
                }
            }
        ]
    
    def _get_router_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for command router"""
        return [
            {
                "name": "Route Start Command",
                "message_data": {"text": "/start"},
                "user_data": {"id": "router_test_1", "first_name": "Test"}
            },
            {
                "name": "Route Help Command",
                "message_data": {"text": "/help"},
                "user_data": {"id": "router_test_2", "first_name": "Test"}
            },
            {
                "name": "Route Non-Command",
                "message_data": {"text": "I need assistance"},
                "user_data": {"id": "router_test_3", "first_name": "Test"}
            }
        ]
    
    def _get_welcome_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for welcome messages"""
        return [
            {
                "name": "New User Welcome",
                "user_data": {"id": "welcome_new_user", "first_name": "New"}
            },
            {
                "name": "Returning User Welcome",
                "user_data": {"id": "welcome_existing_user", "first_name": "Existing"}
            }
        ]
    
    def _get_permission_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for permission system"""
        return [
            {
                "name": "Public Command - Public User",
                "message_data": {"text": "/help"},
                "user_data": {"id": "perm_test_1", "access_level": "Public"},
                "should_succeed": True
            },
            {
                "name": "Admin Command - Public User",
                "message_data": {"text": "/admin_command"},
                "user_data": {"id": "perm_test_2", "access_level": "Public"},
                "should_succeed": False
            },
            {
                "name": "Admin Command - Admin User",
                "message_data": {"text": "/admin_command"},
                "user_data": {"id": "perm_test_3", "access_level": "Admin"},
                "should_succeed": True
            }
        ]
    
    def _get_error_test_cases(self) -> List[Dict[str, Any]]:
        """Get test cases for error handling"""
        return [
            {
                "name": "Invalid Message Data",
                "condition": "invalid_message_data"
            },
            {
                "name": "Missing User Data",
                "condition": "missing_user_data"
            },
            {
                "name": "Template Not Found",
                "condition": "template_not_found"
            },
            {
                "name": "Function Import Error",
                "condition": "function_import_error"
            }
        ]
    
    def _simulate_error_condition(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate various error conditions"""
        condition = test_case["condition"]
        
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            processor = TelegramCommandProcessor(self.bot_doc)
            
            if condition == "invalid_message_data":
                return processor.process_message(None, {"id": "test"})
            elif condition == "missing_user_data":
                return processor.process_message({"text": "/help"}, None)
            elif condition == "template_not_found":
                from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
                response_manager = BotResponseManager(self.bot_doc)
                return response_manager.render_template("non_existent_template", {})
            elif condition == "function_import_error":
                # Try to execute a command with invalid function path
                return processor.process_message(
                    {"text": "/invalid_function_command"},
                    {"id": "test"}
                )
            
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "error_type": "exception"
            }
        
        return {
            "success": False,
            "message": "Unknown error condition",
            "error_type": "unknown"
        }
    
    def _simulate_webhook_processing(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate complete webhook processing"""
        try:
            # Import webhook processor
            from helpdesk.www.telegram.webhook import process_telegram_update
            
            # Mock bot document for testing
            if not self.bot_doc:
                return {
                    "success": False,
                    "message": "No bot document available for testing"
                }
            
            return process_telegram_update(webhook_data, self.bot_doc)
            
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "error_type": "webhook_processing_error"
            }
    
    def _validate_result(self, result: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
        """Validate test result against expected values"""
        validation = {"passed": True, "issues": []}
        
        for key, expected_value in expected.items():
            actual_value = result.get(key)
            
            if actual_value != expected_value:
                validation["passed"] = False
                validation["issues"].append({
                    "field": key,
                    "expected": expected_value,
                    "actual": actual_value
                })
        
        return validation
    
    def _calculate_overall_metrics(self, performance_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall performance metrics"""
        if not performance_results:
            return {}
        
        total_iterations = sum(r["iterations"] for r in performance_results)
        total_successful = sum(r["successful_iterations"] for r in performance_results)
        
        all_avg_times = [r["average_time"] for r in performance_results if r.get("average_time")]
        
        return {
            "total_iterations": total_iterations,
            "total_successful": total_successful,
            "overall_success_rate": (total_successful / total_iterations * 100) if total_iterations > 0 else 0,
            "average_response_time": sum(all_avg_times) / len(all_avg_times) if all_avg_times else 0,
            "fastest_average": min(all_avg_times) if all_avg_times else 0,
            "slowest_average": max(all_avg_times) if all_avg_times else 0
        }
    
    def _log_test_start(self, test_name: str) -> None:
        """Log test start"""
        frappe.logger().info(f"Starting test: {test_name}")
    
    def _log_test_result(self, test_name: str, result: Dict[str, Any], execution_time: float) -> None:
        """Log test result"""
        status = "PASSED" if result.get("success") else "FAILED"
        frappe.logger().info(f"Test {test_name}: {status} (took {execution_time:.3f}s)")
        
        self.test_results.append({
            "test_name": test_name,
            "status": status,
            "execution_time": execution_time,
            "result": result,
            "timestamp": now_datetime().isoformat()
        })
    
    def _log_test_error(self, test_name: str, error: str, traceback_str: str) -> None:
        """Log test error"""
        frappe.logger().error(f"Test {test_name} ERROR: {error}")
        
        self.test_results.append({
            "test_name": test_name,
            "status": "ERROR",
            "error": error,
            "traceback": traceback_str,
            "timestamp": now_datetime().isoformat()
        })
    
    def _generate_test_summary(self) -> Dict[str, Any]:
        """Generate test summary"""
        if not self.test_results:
            return {}
        
        passed = len([r for r in self.test_results if r["status"] == "PASSED"])
        failed = len([r for r in self.test_results if r["status"] == "FAILED"])
        errors = len([r for r in self.test_results if r["status"] == "ERROR"])
        total = len(self.test_results)
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "success_rate": (passed / total * 100) if total > 0 else 0,
            "status": "PASSED" if failed == 0 and errors == 0 else "FAILED"
        }


# API Functions
@frappe.whitelist()
def run_bot_tests(bot_name: str = None) -> Dict[str, Any]:
    """
    Run comprehensive bot tests
    
    Args:
        bot_name: Name of the bot to test
        
    Returns:
        Test results
    """
    try:
        tester = TelegramBotTester(bot_name)
        return tester.run_comprehensive_tests()
    except Exception as e:
        frappe.log_error(f"Bot testing failed: {str(e)}")
        return {
            "success": False,
            "message": f"Testing failed: {str(e)}"
        }


@frappe.whitelist()
def run_specific_test(bot_name: str, test_type: str) -> Dict[str, Any]:
    """
    Run a specific test type
    
    Args:
        bot_name: Name of the bot to test
        test_type: Type of test to run
        
    Returns:
        Test results
    """
    try:
        tester = TelegramBotTester(bot_name)
        
        test_methods = {
            "command_processing": tester.test_command_processing,
            "response_templates": tester.test_response_templates,
            "command_router": tester.test_command_router,
            "welcome_messages": tester.test_welcome_messages,
            "permission_system": tester.test_permission_system,
            "error_handling": tester.test_error_handling,
            "performance": tester.test_performance,
            "integration": tester.test_integration_flow
        }
        
        if test_type not in test_methods:
            return {
                "success": False,
                "message": f"Unknown test type: {test_type}"
            }
        
        return test_methods[test_type]()
        
    except Exception as e:
        frappe.log_error(f"Specific test failed: {str(e)}")
        return {
            "success": False,
            "message": f"Test failed: {str(e)}"
        }


@frappe.whitelist()
def validate_bot_configuration(bot_name: str) -> Dict[str, Any]:
    """
    Validate bot configuration
    
    Args:
        bot_name: Name of the bot to validate
        
    Returns:
        Validation results
    """
    try:
        bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        issues = []
        
        # Check bot token
        if not bot_doc.bot_token:
            issues.append("Bot token is missing")
        
        # Check webhook configuration
        if not bot_doc.webhook_url:
            issues.append("Webhook URL is missing")
        
        if not bot_doc.webhook_secret:
            issues.append("Webhook secret is missing")
        
        # Check command mappings
        if not bot_doc.command_mappings:
            issues.append("No command mappings configured")
        else:
            active_commands = [m for m in bot_doc.command_mappings if m.is_active]
            if not active_commands:
                issues.append("No active command mappings found")
        
        # Check templates
        if bot_doc.welcome_template:
            try:
                frappe.get_doc("HD Bot Response Template", bot_doc.welcome_template)
            except frappe.DoesNotExistError:
                issues.append(f"Welcome template '{bot_doc.welcome_template}' not found")
        
        return {
            "success": len(issues) == 0,
            "bot_name": bot_name,
            "issues": issues,
            "validation_status": "PASSED" if len(issues) == 0 else "FAILED",
            "timestamp": now_datetime().isoformat()
        }
        
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "message": f"Bot '{bot_name}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Bot validation failed: {str(e)}")
        return {
            "success": False,
            "message": f"Validation failed: {str(e)}"
        } 