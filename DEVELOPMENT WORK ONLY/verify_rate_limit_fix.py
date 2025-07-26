#!/usr/bin/env python3
"""
Verify the rate limiting fix without running the Flask server
"""

from models import custom_rate_limits_collection
from ip_utils import get_custom_rate_limit

def test_custom_rate_limit_logic():
    """Test the custom rate limit logic"""
    print("=== Testing Custom Rate Limit Logic ===")
    
    # Test IPs and endpoints
    test_cases = [
        ("127.0.0.1", "api_generate_image"),
        ("192.168.1.1", "generate_image"),
        ("10.0.0.1", "api_text_to_video_generate"),
    ]
    
    for ip, endpoint in test_cases:
        print(f"\nTesting IP: {ip}, Endpoint: {endpoint}")
        custom_limit = get_custom_rate_limit(ip, endpoint)
        
        if custom_limit:
            limit_string = custom_limit.get('limit_string')
            print(f"  ✓ Custom limit found: {limit_string}")
            
            # Test the logic from get_rate_limit function
            if limit_string and ('unlimited' in limit_string.lower() or 'per day' in limit_string and int(limit_string.split()[0]) > 100000):
                print(f"  ✓ Would apply high/unlimited rate limit: 1000000 per hour")
            else:
                print(f"  ✓ Would apply custom limit: {limit_string}")
        else:
            print(f"  ✗ No custom limit found - will use default")

def check_database_connection():
    """Check if the database is connected and has custom limits"""
    print("=== Checking Database Connection ===")
    
    if custom_rate_limits_collection is not None:
        print("✓ Database connected")
        
        # Count custom limits
        count = custom_rate_limits_collection.count_documents({})
        print(f"✓ Found {count} custom rate limits in database")
        
        if count > 0:
            print("\nCustom rate limits:")
            for limit in custom_rate_limits_collection.find().limit(10):
                print(f"  IP: {limit['ip']}, Endpoint: {limit['endpoint']}, Limit: {limit['limit_string']}")
        else:
            print("⚠ No custom rate limits found in database")
            print("  This might be why you're seeing default limits")
    else:
        print("✗ Database not connected")

def simulate_rate_limit_function():
    """Simulate the get_rate_limit function logic"""
    print("\n=== Simulating get_rate_limit Function ===")
    
    # Mock some test data
    test_scenarios = [
        {
            'ip': '127.0.0.1',
            'endpoint': 'api_generate_image',
            'custom_limit': {'limit_string': '1000000 per day'}
        },
        {
            'ip': '192.168.1.1', 
            'endpoint': 'generate_image',
            'custom_limit': {'limit_string': 'unlimited'}
        },
        {
            'ip': '10.0.0.1',
            'endpoint': 'api_text_to_video_generate', 
            'custom_limit': None
        }
    ]
    
    for scenario in test_scenarios:
        ip = scenario['ip']
        endpoint = scenario['endpoint']
        custom_limit = scenario['custom_limit']
        
        print(f"\nScenario: IP {ip}, Endpoint {endpoint}")
        
        if custom_limit:
            limit_string = custom_limit.get('limit_string')
            print(f"  Custom limit found: {limit_string}")
            
            # Apply the same logic as get_rate_limit function
            if limit_string and ('unlimited' in limit_string.lower() or 'per day' in limit_string and int(limit_string.split()[0]) > 100000):
                result = "1000000 per hour"
                print(f"  ✓ Result: {result} (high/unlimited)")
            else:
                result = limit_string
                print(f"  ✓ Result: {result} (custom)")
        else:
            result = "get_remote_address"  # Default
            print(f"  ✓ Result: {result} (default)")

if __name__ == "__main__":
    print("=== Rate Limit Fix Verification ===")
    
    # Check database connection
    check_database_connection()
    
    # Test custom rate limit logic
    test_custom_rate_limit_logic()
    
    # Simulate the function
    simulate_rate_limit_function()
    
    print("\n=== Summary ===")
    print("The rate limiting fix should work if:")
    print("1. ✓ Custom rate limits are properly stored in the database")
    print("2. ✓ The IP addresses match exactly (check X-Forwarded-For headers)")
    print("3. ✓ The endpoint names match exactly")
    print("4. ✓ The get_rate_limit() function returns the custom limit string")
    print("\nIf you're still seeing '60 per 1 hour', it means:")
    print("- Either no custom limit is found for your IP/endpoint combination")
    print("- Or the custom limit string is not being returned properly")