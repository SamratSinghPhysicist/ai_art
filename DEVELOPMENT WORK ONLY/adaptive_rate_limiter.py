"""
Adaptive Rate Limiting System for AiArt Application

This module implements intelligent rate limiting that adjusts based on server load,
user tiers, and implements token bucket algorithm for smooth rate limiting.
"""

import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class UserTier(Enum):
    """User tier enumeration for different privilege levels"""
    ANONYMOUS = "anonymous"
    REGISTERED = "registered"
    DONOR = "donor"


@dataclass
class RateLimitConfig:
    """Configuration for rate limits per user tier"""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    queue_priority: int  # Lower number = higher priority
    grace_period_requests: int  # Free requests for new users


@dataclass
class TokenBucket:
    """Token bucket for smooth rate limiting"""
    capacity: int
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: float
    
    def __post_init__(self):
        if self.last_refill == 0:
            self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket"""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self):
        """Refill tokens based on time elapsed"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


class UserTierManager:
    """Manages different user privilege levels and their configurations"""
    
    # Default rate limit configurations per tier
    TIER_CONFIGS = {
        UserTier.ANONYMOUS: RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=60,
            requests_per_day=100,
            queue_priority=3,
            grace_period_requests=5
        ),
        UserTier.REGISTERED: RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=120,
            requests_per_day=300,
            queue_priority=2,
            grace_period_requests=10
        ),
        UserTier.DONOR: RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=300,
            requests_per_day=1000,
            queue_priority=1,
            grace_period_requests=20
        )
    }
    
    def __init__(self):
        self._user_tiers = {}  # user_id -> UserTier
        self._tier_overrides = {}  # user_id -> RateLimitConfig
        self._lock = threading.RLock()
    
    def get_user_tier(self, user_id: Optional[str], is_authenticated: bool = False, 
                     is_donor: bool = False) -> UserTier:
        """Determine user tier based on authentication and donor status"""
        with self._lock:
            # Check for explicit tier assignment first
            if user_id and user_id in self._user_tiers:
                return self._user_tiers[user_id]
            
            # Determine tier based on status
            if is_donor:
                return UserTier.DONOR
            elif is_authenticated:
                return UserTier.REGISTERED
            else:
                return UserTier.ANONYMOUS
    
    def set_user_tier(self, user_id: str, tier: UserTier):
        """Explicitly set a user's tier"""
        with self._lock:
            self._user_tiers[user_id] = tier
            logger.info(f"Set user {user_id} to tier {tier.value}")
    
    def get_tier_config(self, tier: UserTier) -> RateLimitConfig:
        """Get rate limit configuration for a tier"""
        return self.TIER_CONFIGS[tier]
    
    def set_custom_limits(self, user_id: str, config: RateLimitConfig):
        """Set custom rate limits for a specific user"""
        with self._lock:
            self._tier_overrides[user_id] = config
            logger.info(f"Set custom limits for user {user_id}")
    
    def get_effective_config(self, user_id: Optional[str], tier: UserTier) -> RateLimitConfig:
        """Get effective rate limit configuration (considering overrides)"""
        with self._lock:
            if user_id and user_id in self._tier_overrides:
                return self._tier_overrides[user_id]
            return self.get_tier_config(tier)


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts limits based on server load and user tiers.
    Implements token bucket algorithm for smooth rate limiting.
    """
    
    def __init__(self, tier_manager: UserTierManager, resource_monitor=None):
        self.tier_manager = tier_manager
        self.resource_monitor = resource_monitor
        
        # Token buckets per user
        self._user_buckets = defaultdict(dict)  # user_id -> {minute, hour, day} -> TokenBucket
        self._grace_period_usage = defaultdict(int)  # user_id -> count
        self._user_first_request = defaultdict(float)  # user_id -> timestamp
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Load adjustment factors
        self.load_adjustment_factors = {
            0.0: 1.0,   # No load - normal limits
            0.5: 1.0,   # Low load - normal limits  
            0.7: 0.8,   # Medium load - 80% of normal
            0.8: 0.6,   # High load - 60% of normal
            0.9: 0.4,   # Very high load - 40% of normal
            1.0: 0.2,   # Maximum load - 20% of normal
        }
        
        logger.info("AdaptiveRateLimiter initialized")
    
    def _get_server_load(self) -> float:
        """Get current server load (0.0 to 1.0)"""
        if self.resource_monitor:
            try:
                metrics = self.resource_monitor.get_current_metrics()
                return min(1.0, metrics.get('current_load', 0.0) / 100.0)
            except Exception as e:
                logger.warning(f"Failed to get server load: {e}")
        return 0.0  # Default to no load if monitoring unavailable
    
    def _get_load_adjustment_factor(self, server_load: float) -> float:
        """Get load adjustment factor based on current server load"""
        # Find the closest load threshold
        thresholds = sorted(self.load_adjustment_factors.keys())
        for threshold in thresholds:
            if server_load <= threshold:
                return self.load_adjustment_factors[threshold]
        return self.load_adjustment_factors[1.0]  # Maximum load factor
    
    def _get_or_create_bucket(self, user_id: str, period: str, capacity: int, 
                             refill_rate: float) -> TokenBucket:
        """Get or create a token bucket for a user and time period"""
        with self._lock:
            if period not in self._user_buckets[user_id]:
                self._user_buckets[user_id][period] = TokenBucket(
                    capacity=capacity,
                    tokens=capacity,  # Start with full bucket
                    refill_rate=refill_rate,
                    last_refill=time.time()
                )
            return self._user_buckets[user_id][period]
    
    def _is_in_grace_period(self, user_id: str, tier_config: RateLimitConfig) -> bool:
        """Check if user is in grace period (first few requests are free)"""
        with self._lock:
            if user_id not in self._user_first_request:
                self._user_first_request[user_id] = time.time()
                return True
            
            # Grace period is for first N requests within first hour
            first_request_time = self._user_first_request[user_id]
            if time.time() - first_request_time < 3600:  # Within first hour
                usage = self._grace_period_usage[user_id]
                return usage < tier_config.grace_period_requests
            
            return False
    
    def should_allow_request(self, user_id: Optional[str], ip: str, 
                           is_authenticated: bool = False, is_donor: bool = False) -> Tuple[bool, Dict]:
        """
        Check if a request should be allowed based on rate limits.
        
        Returns:
            Tuple of (allowed: bool, info: dict with details)
        """
        # Use IP as fallback identifier for anonymous users
        effective_user_id = user_id or f"ip:{ip}"
        
        # Get user tier and configuration
        tier = self.tier_manager.get_user_tier(user_id, is_authenticated, is_donor)
        base_config = self.tier_manager.get_effective_config(user_id, tier)
        
        # Get current server load and adjustment factor
        server_load = self._get_server_load()
        load_factor = self._get_load_adjustment_factor(server_load)
        
        # Adjust limits based on server load
        adjusted_config = RateLimitConfig(
            requests_per_minute=max(1, int(base_config.requests_per_minute * load_factor)),
            requests_per_hour=max(5, int(base_config.requests_per_hour * load_factor)),
            requests_per_day=max(10, int(base_config.requests_per_day * load_factor)),
            queue_priority=base_config.queue_priority,
            grace_period_requests=base_config.grace_period_requests
        )
        
        # Check grace period first
        if self._is_in_grace_period(effective_user_id, base_config):
            with self._lock:
                self._grace_period_usage[effective_user_id] += 1
            
            return True, {
                'allowed': True,
                'reason': 'grace_period',
                'tier': tier.value,
                'server_load': server_load,
                'load_factor': load_factor,
                'grace_requests_remaining': base_config.grace_period_requests - self._grace_period_usage[effective_user_id]
            }
        
        # Create/get token buckets for different time periods
        minute_bucket = self._get_or_create_bucket(
            effective_user_id, 'minute', 
            adjusted_config.requests_per_minute,
            adjusted_config.requests_per_minute / 60.0  # refill rate per second
        )
        
        hour_bucket = self._get_or_create_bucket(
            effective_user_id, 'hour',
            adjusted_config.requests_per_hour,
            adjusted_config.requests_per_hour / 3600.0  # refill rate per second
        )
        
        day_bucket = self._get_or_create_bucket(
            effective_user_id, 'day',
            adjusted_config.requests_per_day,
            adjusted_config.requests_per_day / 86400.0  # refill rate per second
        )
        
        # Check all buckets - request must pass all limits
        buckets_info = {
            'minute': {'capacity': minute_bucket.capacity, 'tokens': minute_bucket.tokens},
            'hour': {'capacity': hour_bucket.capacity, 'tokens': hour_bucket.tokens},
            'day': {'capacity': day_bucket.capacity, 'tokens': day_bucket.tokens}
        }
        
        # Try to consume from all buckets
        if (minute_bucket.consume() and hour_bucket.consume() and day_bucket.consume()):
            return True, {
                'allowed': True,
                'reason': 'within_limits',
                'tier': tier.value,
                'server_load': server_load,
                'load_factor': load_factor,
                'buckets': buckets_info,
                'adjusted_limits': {
                    'per_minute': adjusted_config.requests_per_minute,
                    'per_hour': adjusted_config.requests_per_hour,
                    'per_day': adjusted_config.requests_per_day
                }
            }
        else:
            # Determine which limit was hit
            limit_hit = []
            if minute_bucket.tokens < 1:
                limit_hit.append('minute')
            if hour_bucket.tokens < 1:
                limit_hit.append('hour')
            if day_bucket.tokens < 1:
                limit_hit.append('day')
            
            # Calculate wait times
            wait_times = {}
            if 'minute' in limit_hit:
                wait_times['minute'] = max(0, int((1 - minute_bucket.tokens) / minute_bucket.refill_rate))
            if 'hour' in limit_hit:
                wait_times['hour'] = max(0, int((1 - hour_bucket.tokens) / hour_bucket.refill_rate))
            if 'day' in limit_hit:
                wait_times['day'] = max(0, int((1 - day_bucket.tokens) / day_bucket.refill_rate))
            
            return False, {
                'allowed': False,
                'reason': 'rate_limit_exceeded',
                'tier': tier.value,
                'server_load': server_load,
                'load_factor': load_factor,
                'limits_hit': limit_hit,
                'wait_times': wait_times,
                'buckets': buckets_info,
                'adjusted_limits': {
                    'per_minute': adjusted_config.requests_per_minute,
                    'per_hour': adjusted_config.requests_per_hour,
                    'per_day': adjusted_config.requests_per_day
                }
            }
    
    def get_user_friendly_message(self, allowed: bool, info: Dict) -> Dict:
        """Generate user-friendly rate limit messages using the new error handling system"""
        if allowed:
            if info['reason'] == 'grace_period':
                return {
                    'type': 'success',
                    'message': f"Welcome! You have {info.get('grace_requests_remaining', 0)} free requests remaining.",
                    'action': 'continue'
                }
            else:
                return {
                    'type': 'success', 
                    'message': 'Request processed successfully.',
                    'action': 'continue'
                }
        
        # Rate limit exceeded - use new error handling system
        from user_friendly_errors import get_error_handler, ErrorType
        
        tier = info.get('tier', 'anonymous')
        server_load = info.get('server_load', 0.0)
        wait_times = info.get('wait_times', {})
        limits_hit = info.get('limits_hit', [])
        
        # Determine shortest wait time
        min_wait = min(wait_times.values()) if wait_times else 60
        
        # Create user-friendly error response
        error_handler = get_error_handler()
        error_response = error_handler.create_rate_limit_response(
            user_tier=tier,
            wait_time=min_wait,
            server_load=server_load,
            limits_hit=limits_hit
        )
        
        # Convert to the expected format for backward compatibility
        response_dict = error_response.to_dict()
        
        return {
            'type': 'rate_limit',
            'message': response_dict['message'],
            'action': 'wait',
            'wait_time': min_wait,
            'tier': tier,
            'server_load': server_load,
            'upgrade_available': response_dict['upgrade_available'],
            'donation_link': response_dict['donation_link'] if response_dict['show_donation_prompt'] else None,
            'title': response_dict['title'],
            'action_message': response_dict['action_message'],
            'donation_message': response_dict['donation_message'],
            'upgrade_message': response_dict['upgrade_message'],
            'alternatives': response_dict['alternatives']
        }
    
    def cleanup_old_buckets(self, max_age_hours: int = 24):
        """Clean up old token buckets to prevent memory leaks"""
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        with self._lock:
            users_to_remove = []
            for user_id, buckets in self._user_buckets.items():
                # Check if any bucket has been used recently
                recent_activity = False
                for bucket in buckets.values():
                    if bucket.last_refill > cutoff_time:
                        recent_activity = True
                        break
                
                if not recent_activity:
                    users_to_remove.append(user_id)
            
            # Remove old buckets
            for user_id in users_to_remove:
                del self._user_buckets[user_id]
                if user_id in self._grace_period_usage:
                    del self._grace_period_usage[user_id]
                if user_id in self._user_first_request:
                    del self._user_first_request[user_id]
            
            if users_to_remove:
                logger.info(f"Cleaned up {len(users_to_remove)} old rate limit buckets")


# Global instances
_tier_manager = None
_adaptive_limiter = None


def get_tier_manager() -> UserTierManager:
    """Get global UserTierManager instance"""
    global _tier_manager
    if _tier_manager is None:
        _tier_manager = UserTierManager()
    return _tier_manager


def get_adaptive_limiter(resource_monitor=None) -> AdaptiveRateLimiter:
    """Get global AdaptiveRateLimiter instance"""
    global _adaptive_limiter
    if _adaptive_limiter is None:
        _adaptive_limiter = AdaptiveRateLimiter(get_tier_manager(), resource_monitor)
    return _adaptive_limiter


def should_allow_request(user_id: Optional[str], ip: str, is_authenticated: bool = False, 
                        is_donor: bool = False, resource_monitor=None) -> Tuple[bool, Dict]:
    """Convenience function to check if request should be allowed"""
    limiter = get_adaptive_limiter(resource_monitor)
    return limiter.should_allow_request(user_id, ip, is_authenticated, is_donor)


def get_rate_limit_message(allowed: bool, info: Dict) -> Dict:
    """Convenience function to get user-friendly rate limit message"""
    limiter = get_adaptive_limiter()
    return limiter.get_user_friendly_message(allowed, info)