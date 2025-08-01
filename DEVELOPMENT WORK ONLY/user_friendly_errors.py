"""
User-Friendly Error Handling and Messaging System

This module provides user-friendly error messages and soft throttling responses
that encourage donations and provide helpful alternatives instead of technical errors.
"""

import time
import random
from typing import Dict, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class ErrorType(Enum):
    """Types of errors that can occur in the system"""
    RATE_LIMIT = "rate_limit"
    SERVER_BUSY = "server_busy"
    QUEUE_FULL = "queue_full"
    API_ERROR = "api_error"
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "auth_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    TIMEOUT_ERROR = "timeout_error"
    GENERATION_FAILED = "generation_failed"


@dataclass
class ErrorResponse:
    """Structured error response with user-friendly messaging"""
    success: bool = False
    error_type: str = ""
    title: str = ""
    message: str = ""
    action_message: str = ""
    wait_time: Optional[int] = None
    retry_after: Optional[int] = None
    show_donation_prompt: bool = False
    donation_message: str = ""
    donation_link: str = "/donate"
    upgrade_available: bool = False
    upgrade_message: str = ""
    alternatives: List[str] = None
    technical_details: str = ""
    status_code: int = 429

    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON responses"""
        return {
            'success': self.success,
            'error_type': self.error_type,
            'title': self.title,
            'message': self.message,
            'action_message': self.action_message,
            'wait_time': self.wait_time,
            'retry_after': self.retry_after,
            'show_donation_prompt': self.show_donation_prompt,
            'donation_message': self.donation_message,
            'donation_link': self.donation_link,
            'upgrade_available': self.upgrade_available,
            'upgrade_message': self.upgrade_message,
            'alternatives': self.alternatives,
            'technical_details': self.technical_details,
            'timestamp': datetime.utcnow().isoformat()
        }


class UserFriendlyErrorHandler:
    """Handles conversion of technical errors to user-friendly messages"""
    
    # Encouraging messages for different scenarios
    BUSY_SERVER_MESSAGES = [
        "🚀 Wow! Our AI art service is super popular right now!",
        "🎨 So many amazing creations happening simultaneously!",
        "✨ The creative energy is through the roof today!",
        "🌟 Our servers are working hard to bring everyone's visions to life!",
        "🎭 High demand means lots of artists are creating with us!"
    ]
    
    RATE_LIMIT_MESSAGES = [
        "⏰ You're creating at lightning speed!",
        "🎨 Taking a creative breather can lead to even better ideas!",
        "✨ Quality over quantity - let's make your next creation amazing!",
        "🌟 Great artists know when to pause and reflect!",
        "🎭 A short break often sparks the best inspiration!"
    ]
    
    DONATION_PROMPTS = [
        "❤️ Love what we're building? Your support helps us serve more artists!",
        "🙏 Consider supporting our mission to democratize AI art creation!",
        "💝 Your donation helps us upgrade servers for faster processing!",
        "🌟 Help us keep this service free and accessible for everyone!",
        "🚀 Support our growth and get premium features in return!",
        "💖 Every donation helps us improve the experience for all users!",
        "🎨 Join our community of supporters and unlock exclusive benefits!"
    ]
    
    UPGRADE_MESSAGES = {
        'anonymous': "💡 Create a free account for higher limits and saved creations!",
        'registered': "⭐ Upgrade to premium for unlimited generations and priority processing!",
        'donor': "🎉 Thank you for supporting us! You have the highest limits available!"
    }
    
    ALTERNATIVE_ACTIONS = {
        'rate_limit': [
            "Try a different art style or prompt while waiting",
            "Browse the gallery for inspiration",
            "Check out our tutorials and tips",
            "Share your previous creations on social media",
            "Join our community Discord for art discussions"
        ],
        'server_busy': [
            "Bookmark this page and try again in a few minutes",
            "Follow us on social media for server status updates",
            "Try during off-peak hours (early morning or late evening)",
            "Use the time to refine your prompt for better results",
            "Check out our blog for AI art tips and techniques"
        ],
        'queue_full': [
            "Try again in 10-15 minutes when the queue clears",
            "Consider upgrading for priority queue access",
            "Use this time to plan your next creative project",
            "Browse our featured artwork for inspiration",
            "Join our newsletter for updates and tips"
        ]
    }
    
    def __init__(self):
        self.donation_link = "/donate"
        self.register_link = "/signup"
        self.login_link = "/login"
    
    def create_rate_limit_response(self, user_tier: str = 'anonymous', 
                                 wait_time: int = 60, server_load: float = 0.0,
                                 limits_hit: List[str] = None) -> ErrorResponse:
        """Create user-friendly rate limit response"""
        
        # Select encouraging message
        base_message = random.choice(self.RATE_LIMIT_MESSAGES)
        
        # Format wait time
        if wait_time < 60:
            wait_msg = f"Please wait {wait_time} seconds"
        elif wait_time < 3600:
            minutes = wait_time // 60
            wait_msg = f"Please wait {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = wait_time // 3600
            wait_msg = f"Please wait {hours} hour{'s' if hours != 1 else ''}"
        
        # Add server load context
        if server_load > 0.8:
            context = " Our servers are experiencing high demand right now."
        elif server_load > 0.5:
            context = " We're processing many requests at the moment."
        else:
            context = " This helps us maintain quality service for everyone."
        
        # Create main message
        message = f"{base_message} {wait_msg} and try again.{context}"
        
        # Determine if we should show donation prompt
        show_donation = server_load > 0.7 or user_tier != 'donor'
        donation_message = random.choice(self.DONATION_PROMPTS) if show_donation else ""
        
        # Upgrade message
        upgrade_available = user_tier != 'donor'
        upgrade_message = self.UPGRADE_MESSAGES.get(user_tier, "")
        
        return ErrorResponse(
            error_type=ErrorType.RATE_LIMIT.value,
            title="Rate Limit Reached",
            message=message,
            action_message=wait_msg,
            wait_time=wait_time,
            retry_after=wait_time,
            show_donation_prompt=show_donation,
            donation_message=donation_message,
            upgrade_available=upgrade_available,
            upgrade_message=upgrade_message,
            alternatives=self.ALTERNATIVE_ACTIONS['rate_limit'],
            status_code=429
        )
    
    def create_server_busy_response(self, server_load: float = 0.9, 
                                  queue_length: int = 0,
                                  estimated_wait: int = 300) -> ErrorResponse:
        """Create user-friendly server busy response"""
        
        # Select encouraging message
        base_message = random.choice(self.BUSY_SERVER_MESSAGES)
        
        # Add context based on server state
        if queue_length > 50:
            context = f" We have {queue_length} requests in queue, but we're processing them as fast as possible!"
        elif server_load > 0.95:
            context = " Our servers are at maximum capacity, but hang tight!"
        else:
            context = " We're working hard to process all requests quickly!"
        
        # Format estimated wait time
        if estimated_wait < 60:
            wait_msg = f"Try again in about {estimated_wait} seconds"
        elif estimated_wait < 3600:
            minutes = estimated_wait // 60
            wait_msg = f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = estimated_wait // 3600
            wait_msg = f"Try again in about {hours} hour{'s' if hours != 1 else ''}"
        
        message = f"{base_message}{context} {wait_msg}."
        
        # Always show donation prompt for server busy situations
        donation_message = random.choice(self.DONATION_PROMPTS)
        
        return ErrorResponse(
            error_type=ErrorType.SERVER_BUSY.value,
            title="Server Busy",
            message=message,
            action_message=wait_msg,
            wait_time=estimated_wait,
            retry_after=estimated_wait,
            show_donation_prompt=True,
            donation_message=donation_message,
            upgrade_available=True,
            upgrade_message="⚡ Premium users get priority processing even during busy times!",
            alternatives=self.ALTERNATIVE_ACTIONS['server_busy'],
            status_code=503
        )
    
    def create_queue_full_response(self, max_queue_size: int = 100) -> ErrorResponse:
        """Create user-friendly queue full response"""
        
        message = (
            "🎨 Our creative queue is completely full right now! "
            f"We can only handle {max_queue_size} requests at a time to ensure quality. "
            "This means lots of amazing art is being created!"
        )
        
        action_message = "Please try again in 10-15 minutes"
        
        donation_message = (
            "💝 Your support helps us expand our server capacity to handle more requests! "
            "Premium supporters also get priority queue access."
        )
        
        return ErrorResponse(
            error_type=ErrorType.QUEUE_FULL.value,
            title="Queue Full",
            message=message,
            action_message=action_message,
            wait_time=900,  # 15 minutes
            retry_after=900,
            show_donation_prompt=True,
            donation_message=donation_message,
            upgrade_available=True,
            upgrade_message="⚡ Premium users get priority queue access!",
            alternatives=self.ALTERNATIVE_ACTIONS['queue_full'],
            status_code=503
        )
    
    def create_api_error_response(self, original_error: str = "", 
                                service_name: str = "AI service") -> ErrorResponse:
        """Create user-friendly API error response"""
        
        messages = [
            f"🔧 Our {service_name} is taking a quick breather!",
            f"⚡ {service_name} is getting a tune-up for better performance!",
            f"🛠️ We're optimizing {service_name} to serve you better!",
            f"🔄 {service_name} is refreshing to bring you amazing results!"
        ]
        
        base_message = random.choice(messages)
        message = f"{base_message} Please try again in a moment."
        
        # Show donation prompt for API errors as they might indicate resource constraints
        donation_message = (
            "🚀 Your support helps us maintain reliable connections to the best AI services! "
            "Premium users also get access to backup services during outages."
        )
        
        return ErrorResponse(
            error_type=ErrorType.API_ERROR.value,
            title="Service Temporarily Unavailable",
            message=message,
            action_message="Try again in 1-2 minutes",
            wait_time=120,
            retry_after=120,
            show_donation_prompt=True,
            donation_message=donation_message,
            upgrade_available=True,
            upgrade_message="⚡ Premium users get access to backup AI services!",
            alternatives=[
                "Try a different art style that uses a different AI service",
                "Check our status page for service updates",
                "Join our Discord for real-time status updates",
                "Try again during off-peak hours"
            ],
            technical_details=original_error,
            status_code=503
        )
    
    def create_validation_error_response(self, field: str = "", 
                                       issue: str = "") -> ErrorResponse:
        """Create user-friendly validation error response"""
        
        if "prompt" in field.lower():
            message = (
                "🎨 Let's make your prompt even better! "
                f"{issue} Try being more specific or creative with your description."
            )
            alternatives = [
                "Add more descriptive adjectives to your prompt",
                "Specify an art style (e.g., 'digital art', 'oil painting')",
                "Include mood or atmosphere descriptions",
                "Check our prompt guide for inspiration",
                "Browse the gallery for prompt examples"
            ]
        else:
            message = f"📝 There's a small issue with your {field}: {issue}"
            alternatives = [
                "Double-check your input format",
                "Try a simpler version first",
                "Check our help documentation",
                "Contact support if you need assistance"
            ]
        
        return ErrorResponse(
            error_type=ErrorType.VALIDATION_ERROR.value,
            title="Input Needs Adjustment",
            message=message,
            action_message="Please adjust your input and try again",
            show_donation_prompt=False,
            upgrade_available=False,
            alternatives=alternatives,
            status_code=400
        )
    
    def create_authentication_error_response(self, user_tier: str = 'anonymous') -> ErrorResponse:
        """Create user-friendly authentication error response"""
        
        if user_tier == 'anonymous':
            message = (
                "🔐 You've reached the limit for anonymous users! "
                "Creating a free account gives you higher limits and saves your creations."
            )
            action_message = "Sign up for free to continue"
            alternatives = [
                "Create a free account in just 30 seconds",
                "Log in if you already have an account",
                "Try again tomorrow for more free generations",
                "Check out the gallery while you decide"
            ]
        else:
            message = (
                "🔑 Your session has expired for security. "
                "Please log in again to continue creating amazing art!"
            )
            action_message = "Please log in again"
            alternatives = [
                "Log in with your existing account",
                "Reset your password if needed",
                "Contact support if you're having trouble",
                "Browse the gallery while logged out"
            ]
        
        return ErrorResponse(
            error_type=ErrorType.AUTHENTICATION_ERROR.value,
            title="Authentication Required",
            message=message,
            action_message=action_message,
            show_donation_prompt=user_tier == 'anonymous',
            donation_message="❤️ Support our free service and get premium benefits!",
            upgrade_available=True,
            upgrade_message="⭐ Premium accounts never expire and get unlimited access!",
            alternatives=alternatives,
            status_code=401
        )
    
    def create_generation_failed_response(self, service_name: str = "AI art generator",
                                        retry_count: int = 0) -> ErrorResponse:
        """Create user-friendly generation failure response"""
        
        if retry_count == 0:
            message = (
                f"🎨 {service_name} had a creative hiccup! "
                "Sometimes the AI needs a moment to get inspired. Let's try again!"
            )
            action_message = "Click generate to try again"
            wait_time = 30
        elif retry_count < 3:
            message = (
                f"🔄 {service_name} is being extra thoughtful about your request! "
                f"Attempt {retry_count + 1} - sometimes the best art takes a few tries."
            )
            action_message = "Try again with the same or modified prompt"
            wait_time = 60
        else:
            message = (
                f"🛠️ {service_name} seems to be having trouble with this specific request. "
                "Try modifying your prompt or switching to a different art style."
            )
            action_message = "Modify your prompt and try again"
            wait_time = 120
        
        return ErrorResponse(
            error_type=ErrorType.GENERATION_FAILED.value,
            title="Generation Needs Another Try",
            message=message,
            action_message=action_message,
            wait_time=wait_time,
            retry_after=wait_time,
            show_donation_prompt=retry_count > 1,
            donation_message="🚀 Premium users get access to multiple AI services for better reliability!",
            upgrade_available=True,
            upgrade_message="⚡ Premium accounts get priority processing and backup services!",
            alternatives=[
                "Try a simpler or more specific prompt",
                "Switch to a different art style",
                "Use different keywords or descriptions",
                "Check the gallery for working prompt examples",
                "Try again in a few minutes"
            ],
            status_code=500
        )
    
    def create_timeout_response(self, service_name: str = "generation service",
                              timeout_duration: int = 300) -> ErrorResponse:
        """Create user-friendly timeout response"""
        
        minutes = timeout_duration // 60
        
        message = (
            f"⏰ {service_name} is taking longer than usual (over {minutes} minutes)! "
            "This sometimes happens with complex requests during busy periods. "
            "Your request might still be processing in the background."
        )
        
        action_message = "Try again or check back in a few minutes"
        
        return ErrorResponse(
            error_type=ErrorType.TIMEOUT_ERROR.value,
            title="Request Taking Longer Than Expected",
            message=message,
            action_message=action_message,
            wait_time=300,
            retry_after=300,
            show_donation_prompt=True,
            donation_message="⚡ Premium users get faster processing and extended timeouts!",
            upgrade_available=True,
            upgrade_message="🚀 Premium accounts get priority processing for faster results!",
            alternatives=[
                "Try a simpler prompt for faster processing",
                "Check back in 5-10 minutes",
                "Try during off-peak hours",
                "Contact support if this keeps happening",
                "Browse the gallery while waiting"
            ],
            status_code=408
        )
    
    def handle_flask_error(self, error_type: ErrorType, **kwargs) -> Tuple[Dict, int]:
        """
        Handle Flask errors and return appropriate response tuple.
        
        Returns:
            Tuple of (response_dict, status_code) for Flask jsonify
        """
        
        if error_type == ErrorType.RATE_LIMIT:
            response = self.create_rate_limit_response(**kwargs)
        elif error_type == ErrorType.SERVER_BUSY:
            response = self.create_server_busy_response(**kwargs)
        elif error_type == ErrorType.QUEUE_FULL:
            response = self.create_queue_full_response(**kwargs)
        elif error_type == ErrorType.API_ERROR:
            response = self.create_api_error_response(**kwargs)
        elif error_type == ErrorType.VALIDATION_ERROR:
            response = self.create_validation_error_response(**kwargs)
        elif error_type == ErrorType.AUTHENTICATION_ERROR:
            response = self.create_authentication_error_response(**kwargs)
        elif error_type == ErrorType.GENERATION_FAILED:
            response = self.create_generation_failed_response(**kwargs)
        elif error_type == ErrorType.TIMEOUT_ERROR:
            response = self.create_timeout_response(**kwargs)
        else:
            # Default error response
            response = ErrorResponse(
                error_type="unknown_error",
                title="Something Unexpected Happened",
                message="🤖 Our systems encountered something unusual! Please try again in a moment.",
                action_message="Try again in a few seconds",
                wait_time=30,
                show_donation_prompt=True,
                donation_message="❤️ Your support helps us improve system reliability!",
                status_code=500
            )
        
        return response.to_dict(), response.status_code


# Global error handler instance
_error_handler = None


def get_error_handler() -> UserFriendlyErrorHandler:
    """Get global UserFriendlyErrorHandler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = UserFriendlyErrorHandler()
    return _error_handler


# Convenience functions for common error scenarios

def create_rate_limit_error(user_tier: str = 'anonymous', wait_time: int = 60, 
                          server_load: float = 0.0) -> Tuple[Dict, int]:
    """Create rate limit error response for Flask"""
    handler = get_error_handler()
    return handler.handle_flask_error(
        ErrorType.RATE_LIMIT,
        user_tier=user_tier,
        wait_time=wait_time,
        server_load=server_load
    )


def create_server_busy_error(server_load: float = 0.9, queue_length: int = 0,
                           estimated_wait: int = 300) -> Tuple[Dict, int]:
    """Create server busy error response for Flask"""
    handler = get_error_handler()
    return handler.handle_flask_error(
        ErrorType.SERVER_BUSY,
        server_load=server_load,
        queue_length=queue_length,
        estimated_wait=estimated_wait
    )


def create_api_error(original_error: str = "", service_name: str = "AI service") -> Tuple[Dict, int]:
    """Create API error response for Flask"""
    handler = get_error_handler()
    return handler.handle_flask_error(
        ErrorType.API_ERROR,
        original_error=original_error,
        service_name=service_name
    )


def create_validation_error(field: str = "", issue: str = "") -> Tuple[Dict, int]:
    """Create validation error response for Flask"""
    handler = get_error_handler()
    return handler.handle_flask_error(
        ErrorType.VALIDATION_ERROR,
        field=field,
        issue=issue
    )


def create_generation_failed_error(service_name: str = "AI art generator",
                                 retry_count: int = 0) -> Tuple[Dict, int]:
    """Create generation failed error response for Flask"""
    handler = get_error_handler()
    return handler.handle_flask_error(
        ErrorType.GENERATION_FAILED,
        service_name=service_name,
        retry_count=retry_count
    )