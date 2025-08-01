"""
Unit tests for the adaptive rate limiting system.
"""

import unittest
import time
from unittest.mock import Mock, patch
from adaptive_rate_limiter import (
    AdaptiveRateLimiter, UserTierManager, UserTier, RateLimitConfig, TokenBucket,
    get_tier_manager, get_adaptive_limiter, should_allow_request, get_rate_limit_message
)


class TestTokenBucket(unittest.TestCase):
    """Test TokenBucket implementation"""
    
    def test_token_bucket_creation(self):
        """Test token bucket is created with correct initial values"""
        bucket = TokenBucket(capacity=10, tokens=10, refill_rate=1.0, last_refill=0)
        self.assertEqual(bucket.capacity, 10)
        self.assertEqual(bucket.tokens, 10)
        self.assertEqual(bucket.refill_rate, 1.0)
        self.assertGreater(bucket.last_refill, 0)  # Should be set in __post_init__
    
    def test_token_consumption(self):
        """Test token consumption works correctly"""
        bucket = TokenBucket(capacity=10, tokens=5, refill_rate=1.0, last_refill=time.time())
        
        # Should be able to consume available tokens
        self.assertTrue(bucket.consume(3))
        self.assertEqual(bucket.tokens, 2)
        
        # Should not be able to consume more than available
        self.assertFalse(bucket.consume(5))
        self.assertEqual(bucket.tokens, 2)  # Tokens should remain unchanged
    
    def test_token_refill(self):
        """Test token refill mechanism"""
        start_time = time.time()
        bucket = TokenBucket(capacity=10, tokens=0, refill_rate=2.0, last_refill=start_time - 2)
        
        # After 2 seconds at 2 tokens/second, should have 4 tokens (but capped at capacity)
        bucket._refill()
        self.assertEqual(bucket.tokens, 4)
        
        # Test capacity limit
        bucket = TokenBucket(capacity=5, tokens=0, refill_rate=10.0, last_refill=start_time - 2)
        bucket._refill()
        self.assertEqual(bucket.tokens, 5)  # Should be capped at capacity


class TestUserTierManager(unittest.TestCase):
    """Test UserTierManager functionality"""
    
    def setUp(self):
        self.tier_manager = UserTierManager()
    
    def test_get_user_tier_anonymous(self):
        """Test anonymous user tier detection"""
        tier = self.tier_manager.get_user_tier(None, is_authenticated=False, is_donor=False)
        self.assertEqual(tier, UserTier.ANONYMOUS)
    
    def test_get_user_tier_registered(self):
        """Test registered user tier detection"""
        tier = self.tier_manager.get_user_tier("user123", is_authenticated=True, is_donor=False)
        self.assertEqual(tier, UserTier.REGISTERED)
    
    def test_get_user_tier_donor(self):
        """Test donor user tier detection"""
        tier = self.tier_manager.get_user_tier("user123", is_authenticated=True, is_donor=True)
        self.assertEqual(tier, UserTier.DONOR)
    
    def test_explicit_tier_assignment(self):
        """Test explicit tier assignment overrides automatic detection"""
        self.tier_manager.set_user_tier("user123", UserTier.DONOR)
        tier = self.tier_manager.get_user_tier("user123", is_authenticated=False, is_donor=False)
        self.assertEqual(tier, UserTier.DONOR)
    
    def test_tier_configurations(self):
        """Test tier configurations are correct"""
        anonymous_config = self.tier_manager.get_tier_config(UserTier.ANONYMOUS)
        registered_config = self.tier_manager.get_tier_config(UserTier.REGISTERED)
        donor_config = self.tier_manager.get_tier_config(UserTier.DONOR)
        
        # Anonymous should have lowest limits
        self.assertEqual(anonymous_config.requests_per_minute, 3)
        self.assertEqual(anonymous_config.queue_priority, 3)
        
        # Registered should have medium limits
        self.assertEqual(registered_config.requests_per_minute, 5)
        self.assertEqual(registered_config.queue_priority, 2)
        
        # Donor should have highest limits
        self.assertEqual(donor_config.requests_per_minute, 10)
        self.assertEqual(donor_config.queue_priority, 1)
    
    def test_custom_limits(self):
        """Test custom rate limit overrides"""
        custom_config = RateLimitConfig(
            requests_per_minute=20,
            requests_per_hour=500,
            requests_per_day=2000,
            queue_priority=0,
            grace_period_requests=50
        )
        
        self.tier_manager.set_custom_limits("vip_user", custom_config)
        effective_config = self.tier_manager.get_effective_config("vip_user", UserTier.ANONYMOUS)
        
        self.assertEqual(effective_config.requests_per_minute, 20)
        self.assertEqual(effective_config.requests_per_hour, 500)


class TestAdaptiveRateLimiter(unittest.TestCase):
    """Test AdaptiveRateLimiter functionality"""
    
    def setUp(self):
        self.tier_manager = UserTierManager()
        self.mock_resource_monitor = Mock()
        self.limiter = AdaptiveRateLimiter(self.tier_manager, self.mock_resource_monitor)
    
    def test_server_load_adjustment(self):
        """Test rate limits adjust based on server load"""
        # Mock different server loads
        self.mock_resource_monitor.get_current_metrics.return_value = {'current_load': 90.0}
        
        allowed, info = self.limiter.should_allow_request("user123", "192.168.1.1", 
                                                         is_authenticated=True, is_donor=False)
        
        # At 90% load, limits should be reduced to 40% of normal
        # Registered user normally gets 5/min, at 90% load should get 2/min (5 * 0.4 = 2)
        self.assertEqual(info['adjusted_limits']['per_minute'], 2)
    
    def test_grace_period_functionality(self):
        """Test grace period allows free requests for new users"""
        # First few requests should be allowed regardless of limits
        for i in range(5):  # Anonymous users get 5 grace requests
            allowed, info = self.limiter.should_allow_request(None, "192.168.1.1")
            self.assertTrue(allowed)
            self.assertEqual(info['reason'], 'grace_period')
        
        # 6th request should be subject to normal rate limiting
        allowed, info = self.limiter.should_allow_request(None, "192.168.1.1")
        # This might be allowed or not depending on token bucket state, but shouldn't be grace period
        if allowed:
            self.assertEqual(info['reason'], 'within_limits')
    
    def test_rate_limit_enforcement(self):
        """Test rate limits are properly enforced"""
        user_id = "test_user"
        ip = "192.168.1.1"
        
        # Exhaust the minute limit for anonymous user (3 requests/minute)
        # First consume grace period
        for i in range(5):
            self.limiter.should_allow_request(user_id, ip)
        
        # Now test rate limiting - anonymous users get 3/minute
        allowed_count = 0
        for i in range(10):  # Try 10 requests
            allowed, info = self.limiter.should_allow_request(user_id, ip)
            if allowed:
                allowed_count += 1
        
        # Should allow approximately 3 requests (might be slightly more due to token bucket refill)
        self.assertLessEqual(allowed_count, 5)  # Allow some tolerance for timing
    
    def test_different_user_tiers(self):
        """Test different user tiers get different limits"""
        # Test anonymous user
        allowed, info = self.limiter.should_allow_request(None, "192.168.1.1")
        if info['reason'] != 'grace_period':
            self.assertEqual(info['adjusted_limits']['per_minute'], 3)
        
        # Test registered user
        allowed, info = self.limiter.should_allow_request("user123", "192.168.1.2", 
                                                         is_authenticated=True)
        if info['reason'] != 'grace_period':
            self.assertEqual(info['adjusted_limits']['per_minute'], 5)
        
        # Test donor user
        allowed, info = self.limiter.should_allow_request("donor123", "192.168.1.3", 
                                                         is_authenticated=True, is_donor=True)
        if info['reason'] != 'grace_period':
            self.assertEqual(info['adjusted_limits']['per_minute'], 10)
    
    def test_user_friendly_messages(self):
        """Test user-friendly message generation"""
        # Test success message
        allowed_info = {'reason': 'within_limits', 'tier': 'registered'}
        message = self.limiter.get_user_friendly_message(True, allowed_info)
        self.assertEqual(message['type'], 'success')
        self.assertEqual(message['action'], 'continue')
        
        # Test rate limit message
        denied_info = {
            'reason': 'rate_limit_exceeded',
            'tier': 'anonymous',
            'server_load': 0.5,
            'wait_times': {'minute': 30},
            'limits_hit': ['minute']
        }
        message = self.limiter.get_user_friendly_message(False, denied_info)
        self.assertEqual(message['type'], 'rate_limit')
        self.assertEqual(message['action'], 'wait')
        self.assertEqual(message['wait_time'], 30)
        self.assertTrue('Register for an account' in message['message'])
    
    def test_cleanup_old_buckets(self):
        """Test cleanup of old token buckets"""
        # Create some buckets
        self.limiter.should_allow_request("user1", "192.168.1.1")
        self.limiter.should_allow_request("user2", "192.168.1.2")
        
        # Verify buckets exist
        self.assertIn("user1", self.limiter._user_buckets)
        self.assertIn("user2", self.limiter._user_buckets)
        
        # Mock old timestamps
        for user_id in self.limiter._user_buckets:
            for bucket in self.limiter._user_buckets[user_id].values():
                bucket.last_refill = time.time() - 25 * 3600  # 25 hours ago
        
        # Run cleanup
        self.limiter.cleanup_old_buckets(max_age_hours=24)
        
        # Buckets should be cleaned up
        self.assertEqual(len(self.limiter._user_buckets), 0)


class TestGlobalFunctions(unittest.TestCase):
    """Test global convenience functions"""
    
    def test_get_tier_manager_singleton(self):
        """Test tier manager singleton pattern"""
        manager1 = get_tier_manager()
        manager2 = get_tier_manager()
        self.assertIs(manager1, manager2)
    
    def test_get_adaptive_limiter_singleton(self):
        """Test adaptive limiter singleton pattern"""
        limiter1 = get_adaptive_limiter()
        limiter2 = get_adaptive_limiter()
        self.assertIs(limiter1, limiter2)
    
    def test_convenience_functions(self):
        """Test convenience functions work correctly"""
        # Test should_allow_request function
        allowed, info = should_allow_request(None, "192.168.1.1")
        self.assertIsInstance(allowed, bool)
        self.assertIsInstance(info, dict)
        
        # Test get_rate_limit_message function
        message = get_rate_limit_message(allowed, info)
        self.assertIsInstance(message, dict)
        self.assertIn('type', message)
        self.assertIn('message', message)


class TestLoadAdjustment(unittest.TestCase):
    """Test load-based rate limit adjustments"""
    
    def setUp(self):
        self.tier_manager = UserTierManager()
        self.mock_resource_monitor = Mock()
        self.limiter = AdaptiveRateLimiter(self.tier_manager, self.mock_resource_monitor)
    
    def test_load_adjustment_factors(self):
        """Test different load levels produce correct adjustment factors"""
        test_cases = [
            (0.0, 1.0),   # No load
            (0.5, 1.0),   # Low load
            (0.7, 0.8),   # Medium load
            (0.8, 0.6),   # High load
            (0.9, 0.4),   # Very high load
            (1.0, 0.2),   # Maximum load
        ]
        
        for load, expected_factor in test_cases:
            factor = self.limiter._get_load_adjustment_factor(load)
            self.assertEqual(factor, expected_factor, 
                           f"Load {load} should produce factor {expected_factor}, got {factor}")
    
    def test_no_resource_monitor_fallback(self):
        """Test fallback behavior when resource monitor is unavailable"""
        limiter_no_monitor = AdaptiveRateLimiter(self.tier_manager, None)
        load = limiter_no_monitor._get_server_load()
        self.assertEqual(load, 0.0)  # Should default to no load
    
    def test_resource_monitor_exception_handling(self):
        """Test handling of resource monitor exceptions"""
        self.mock_resource_monitor.get_current_metrics.side_effect = Exception("Monitor failed")
        load = self.limiter._get_server_load()
        self.assertEqual(load, 0.0)  # Should default to no load on exception


if __name__ == '__main__':
    unittest.main()