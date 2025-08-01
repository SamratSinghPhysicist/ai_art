"""
Test suite for User-Friendly Error Handling System

This module tests the user-friendly error handling and messaging system
to ensure it provides appropriate responses for different error scenarios.
"""

import unittest
import json
from unittest.mock import Mock, patch
from user_friendly_errors import (
    UserFriendlyErrorHandler, ErrorType, ErrorResponse,
    get_error_handler, create_rate_limit_error, create_server_busy_error,
    create_api_error, create_validation_error, create_generation_failed_error
)


class TestErrorResponse(unittest.TestCase):
    """Test ErrorResponse dataclass functionality"""
    
    def test_error_response_creation(self):
        """Test creating an ErrorResponse with default values"""
        response = ErrorResponse()
        
        self.assertFalse(response.success)
        self.assertEqual(response.error_type, "")
        self.assertEqual(response.alternatives, [])
        self.assertEqual(response.status_code, 429)
    
    def test_error_response_to_dict(self):
        """Test converting ErrorResponse to dictionary"""
        response = ErrorResponse(
            success=False,
            error_type="rate_limit",
            title="Rate Limit Reached",
            message="Please wait and try again",
            wait_time=60
        )
        
        result = response.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertFalse(result['success'])
        self.assertEqual(result['error_type'], "rate_limit")
        self.assertEqual(result['title'], "Rate Limit Reached")
        self.assertEqual(result['wait_time'], 60)
        self.assertIn('timestamp', result)


class TestUserFriendlyErrorHandler(unittest.TestCase):
    """Test UserFriendlyErrorHandler functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.handler = UserFriendlyErrorHandler()
    
    def test_create_rate_limit_response(self):
        """Test creating rate limit error response"""
        response = self.handler.create_rate_limit_response(
            user_tier='anonymous',
            wait_time=120,
            server_load=0.5
        )
        
        self.assertIsInstance(response, ErrorResponse)
        self.assertEqual(response.error_type, ErrorType.RATE_LIMIT.value)
        self.assertEqual(response.wait_time, 120)
        self.assertEqual(response.retry_after, 120)
        self.assertIn("wait", response.message.lower())
        self.assertTrue(response.upgrade_available)
        self.assertIsInstance(response.alternatives, list)
        self.assertGreater(len(response.alternatives), 0)
    
    def test_create_rate_limit_response_different_tiers(self):
        """Test rate limit responses for different user tiers"""
        # Anonymous user
        anon_response = self.handler.create_rate_limit_response(user_tier='anonymous')
        self.assertTrue(anon_response.show_donation_prompt)
        self.assertTrue(anon_response.upgrade_available)
        
        # Registered user
        reg_response = self.handler.create_rate_limit_response(user_tier='registered')
        self.assertTrue(reg_response.upgrade_available)
        
        # Donor
        donor_response = self.handler.create_rate_limit_response(user_tier='donor')
        self.assertFalse(donor_response.upgrade_available)
    
    def test_create_server_busy_response(self):
        """Test creating server busy error response"""
        response = self.handler.create_server_busy_response(
            server_load=0.95,
            queue_length=25,
            estimated_wait=300
        )
        
        self.assertEqual(response.error_type, ErrorType.SERVER_BUSY.value)
        self.assertEqual(response.wait_time, 300)
        self.assertTrue(response.show_donation_prompt)
        self.assertTrue(response.upgrade_available)
        self.assertIn("popular", response.message.lower())
        self.assertEqual(response.status_code, 503)
    
    def test_create_queue_full_response(self):
        """Test creating queue full error response"""
        response = self.handler.create_queue_full_response(max_queue_size=100)
        
        self.assertEqual(response.error_type, ErrorType.QUEUE_FULL.value)
        self.assertEqual(response.wait_time, 900)  # 15 minutes
        self.assertTrue(response.show_donation_prompt)
        self.assertTrue(response.upgrade_available)
        self.assertIn("queue", response.message.lower())
        self.assertIn("100", response.message)
    
    def test_create_api_error_response(self):
        """Test creating API error response"""
        original_error = "Connection timeout to AI service"
        response = self.handler.create_api_error_response(
            original_error=original_error,
            service_name="Stability AI"
        )
        
        self.assertEqual(response.error_type, ErrorType.API_ERROR.value)
        self.assertEqual(response.technical_details, original_error)
        self.assertIn("Stability AI", response.message)
        self.assertTrue(response.show_donation_prompt)
        self.assertEqual(response.status_code, 503)
    
    def test_create_validation_error_response(self):
        """Test creating validation error response"""
        response = self.handler.create_validation_error_response(
            field="prompt",
            issue="Prompt is too long (over 500 characters)"
        )
        
        self.assertEqual(response.error_type, ErrorType.VALIDATION_ERROR.value)
        self.assertFalse(response.show_donation_prompt)
        self.assertFalse(response.upgrade_available)
        self.assertIn("prompt", response.message.lower())
        self.assertEqual(response.status_code, 400)
    
    def test_create_authentication_error_response(self):
        """Test creating authentication error response"""
        # Anonymous user
        anon_response = self.handler.create_authentication_error_response(user_tier='anonymous')
        self.assertEqual(anon_response.error_type, ErrorType.AUTHENTICATION_ERROR.value)
        self.assertTrue(anon_response.show_donation_prompt)
        self.assertIn("anonymous", anon_response.message.lower())
        
        # Registered user
        reg_response = self.handler.create_authentication_error_response(user_tier='registered')
        self.assertIn("session", reg_response.message.lower())
    
    def test_create_generation_failed_response(self):
        """Test creating generation failed error response"""
        # First attempt
        first_response = self.handler.create_generation_failed_response(
            service_name="AI Art Generator",
            retry_count=0
        )
        self.assertEqual(first_response.error_type, ErrorType.GENERATION_FAILED.value)
        self.assertFalse(first_response.show_donation_prompt)
        self.assertEqual(first_response.wait_time, 30)
        
        # Multiple attempts
        multi_response = self.handler.create_generation_failed_response(
            service_name="AI Art Generator",
            retry_count=2
        )
        self.assertTrue(multi_response.show_donation_prompt)
        self.assertGreater(multi_response.wait_time, first_response.wait_time)
    
    def test_create_timeout_response(self):
        """Test creating timeout error response"""
        response = self.handler.create_timeout_response(
            service_name="Video Generator",
            timeout_duration=600
        )
        
        self.assertEqual(response.error_type, ErrorType.TIMEOUT_ERROR.value)
        self.assertEqual(response.wait_time, 300)
        self.assertTrue(response.show_donation_prompt)
        self.assertIn("10 minutes", response.message)
        self.assertEqual(response.status_code, 408)
    
    def test_handle_flask_error(self):
        """Test handling Flask errors and returning appropriate tuples"""
        response_dict, status_code = self.handler.handle_flask_error(
            ErrorType.RATE_LIMIT,
            user_tier='anonymous',
            wait_time=60
        )
        
        self.assertIsInstance(response_dict, dict)
        self.assertEqual(status_code, 429)
        self.assertFalse(response_dict['success'])
        self.assertEqual(response_dict['error_type'], 'rate_limit')
        self.assertIn('timestamp', response_dict)
    
    def test_handle_unknown_error_type(self):
        """Test handling unknown error types"""
        response_dict, status_code = self.handler.handle_flask_error("unknown_error_type")
        
        self.assertEqual(response_dict['error_type'], 'unknown_error')
        self.assertEqual(status_code, 500)
        self.assertIn('unusual', response_dict['message'].lower())


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions for common error scenarios"""
    
    def test_create_rate_limit_error(self):
        """Test rate limit error convenience function"""
        response_dict, status_code = create_rate_limit_error(
            user_tier='registered',
            wait_time=90,
            server_load=0.7
        )
        
        self.assertIsInstance(response_dict, dict)
        self.assertEqual(status_code, 429)
        self.assertEqual(response_dict['error_type'], 'rate_limit')
    
    def test_create_server_busy_error(self):
        """Test server busy error convenience function"""
        response_dict, status_code = create_server_busy_error(
            server_load=0.9,
            queue_length=50
        )
        
        self.assertEqual(status_code, 503)
        self.assertEqual(response_dict['error_type'], 'server_busy')
    
    def test_create_api_error(self):
        """Test API error convenience function"""
        response_dict, status_code = create_api_error(
            original_error="Service unavailable",
            service_name="Test Service"
        )
        
        self.assertEqual(status_code, 503)
        self.assertEqual(response_dict['error_type'], 'api_error')
        self.assertEqual(response_dict['technical_details'], "Service unavailable")
    
    def test_create_validation_error(self):
        """Test validation error convenience function"""
        response_dict, status_code = create_validation_error(
            field="email",
            issue="Invalid email format"
        )
        
        self.assertEqual(status_code, 400)
        self.assertEqual(response_dict['error_type'], 'validation_error')
    
    def test_create_generation_failed_error(self):
        """Test generation failed error convenience function"""
        response_dict, status_code = create_generation_failed_error(
            service_name="Test Generator",
            retry_count=1
        )
        
        self.assertEqual(status_code, 500)
        self.assertEqual(response_dict['error_type'], 'generation_failed')


class TestGlobalErrorHandler(unittest.TestCase):
    """Test global error handler instance"""
    
    def test_get_error_handler_singleton(self):
        """Test that get_error_handler returns the same instance"""
        handler1 = get_error_handler()
        handler2 = get_error_handler()
        
        self.assertIs(handler1, handler2)
        self.assertIsInstance(handler1, UserFriendlyErrorHandler)


class TestErrorMessageContent(unittest.TestCase):
    """Test that error messages contain appropriate content"""
    
    def setUp(self):
        self.handler = UserFriendlyErrorHandler()
    
    def test_messages_are_encouraging(self):
        """Test that error messages are encouraging and positive"""
        response = self.handler.create_rate_limit_response()
        
        # Should not contain negative words
        negative_words = ['failed', 'error', 'problem', 'issue', 'wrong']
        message_lower = response.message.lower()
        
        for word in negative_words:
            self.assertNotIn(word, message_lower, 
                           f"Message contains negative word '{word}': {response.message}")
        
        # Should contain positive elements (emojis, encouraging language)
        self.assertTrue(any(char in response.message for char in '🎨✨🌟🚀💡'),
                       f"Message should contain encouraging emojis: {response.message}")
    
    def test_donation_prompts_are_present(self):
        """Test that donation prompts appear in appropriate scenarios"""
        # High server load should show donation prompt
        busy_response = self.handler.create_server_busy_response(server_load=0.9)
        self.assertTrue(busy_response.show_donation_prompt)
        self.assertTrue(len(busy_response.donation_message) > 0)
        
        # API errors should show donation prompt
        api_response = self.handler.create_api_error_response()
        self.assertTrue(api_response.show_donation_prompt)
    
    def test_upgrade_messages_are_appropriate(self):
        """Test that upgrade messages are appropriate for user tiers"""
        # Anonymous users should see registration prompts
        anon_response = self.handler.create_rate_limit_response(user_tier='anonymous')
        self.assertIn('account', anon_response.upgrade_message.lower())
        
        # Registered users should see premium prompts
        reg_response = self.handler.create_rate_limit_response(user_tier='registered')
        self.assertIn('premium', reg_response.upgrade_message.lower())
        
        # Donors should see thank you messages
        donor_response = self.handler.create_rate_limit_response(user_tier='donor')
        self.assertFalse(donor_response.upgrade_available)
    
    def test_alternatives_are_helpful(self):
        """Test that alternative actions are helpful and actionable"""
        response = self.handler.create_rate_limit_response()
        
        self.assertIsInstance(response.alternatives, list)
        self.assertGreater(len(response.alternatives), 0)
        
        # Each alternative should be a non-empty string
        for alternative in response.alternatives:
            self.assertIsInstance(alternative, str)
            self.assertGreater(len(alternative.strip()), 0)
            # Should contain actionable language
            actionable_words = ['try', 'check', 'browse', 'use', 'join', 'share']
            self.assertTrue(any(word in alternative.lower() for word in actionable_words),
                           f"Alternative should be actionable: {alternative}")


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)