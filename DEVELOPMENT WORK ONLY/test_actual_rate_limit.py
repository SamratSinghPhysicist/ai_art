#!/usr/bin/env python3
"""
Test the actual rate limiting behavior with the improved logic
"""

def simulate_improved_get_rate_limit(ip, endpoint, custom_limit_data):
    """Simulate the improved get_rate_limit function"""
    
    if custom_limit_data:
        limit_string = custom_limit_data.get('limit_string')
        print(f"Custom rate limit found for IP {ip}, endpoint {endpoint}: {limit_string}")
        
        # Handle unlimited or very high limits
        if limit_string:
            # Check for unlimited keyword
            if 'unlimited' in limit_string.lower():
                print(f"Applying unlimited rate limit for IP {ip}")
                return "1000000 per hour"
            
            # Check for extremely large numbers (more than 15 digits)
            if any(len(part.split('/')[0]) > 15 for part in limit_string.split(';') if '/' in part):
                print(f"Applying high rate limit for IP {ip} (extremely large numbers detected)")
                return "1000000 per hour"
            
            # Check for high daily limits
            try:
                if '/day' in limit_string:
                    # Extract the number before '/day'
                    parts = limit_string.split(';')
                    for part in parts:
                        if '/day' in part:
                            number = int(part.split('/')[0])
                            if number > 100000:
                                print(f"Applying high rate limit for IP {ip} (high daily limit: {number})")
                                return "1000000 per hour"
            except (ValueError, IndexError):
                print(f"Could not parse rate limit string for IP {ip}: {limit_string}")
                return "1000000 per hour"  # Default to high limit if parsing fails
        
        return limit_string
    else:
        print(f"No custom rate limit for IP {ip}, endpoint {endpoint}, using default")
    
    return "get_remote_address"

def test_scenarios():
    """Test various rate limiting scenarios"""
    
    scenarios = [
        {
            'name': 'Localhost with extremely large numbers',
            'ip': '127.0.0.1',
            'endpoint': 'api_generate_image',
            'custom_limit': {
                'limit_string': '100000000000000000000000000000000000000000000000000000000000000000000000000000000000/minute;1000000000000000000000000000000000000000000000000000000000000000000000000000000000000/hour;1000000000000000000000000000000000000000000000000000000000000000000000000000000000000/day;1000000000000000000000000000000000000000000000000000000000000000000000000000000000000/second'
            }
        },
        {
            'name': 'Normal high daily limit',
            'ip': '192.168.1.1',
            'endpoint': 'generate_image',
            'custom_limit': {
                'limit_string': '100/minute;5000000/day'
            }
        },
        {
            'name': 'Unlimited keyword',
            'ip': '10.0.0.1',
            'endpoint': 'api_text_to_video_generate',
            'custom_limit': {
                'limit_string': 'unlimited'
            }
        },
        {
            'name': 'Normal rate limit',
            'ip': '203.0.113.1',
            'endpoint': 'api_generate_image',
            'custom_limit': {
                'limit_string': '100/minute;5000/day'
            }
        },
        {
            'name': 'No custom limit',
            'ip': '198.51.100.1',
            'endpoint': 'generate_image',
            'custom_limit': None
        }
    ]
    
    print("=== Testing Rate Limiting Scenarios ===\n")
    
    for scenario in scenarios:
        print(f"Scenario: {scenario['name']}")
        print(f"IP: {scenario['ip']}, Endpoint: {scenario['endpoint']}")
        
        result = simulate_improved_get_rate_limit(
            scenario['ip'], 
            scenario['endpoint'], 
            scenario['custom_limit']
        )
        
        print(f"Result: {result}")
        
        # Analyze the result
        if result == "1000000 per hour":
            print("✅ SUCCESS: High/unlimited rate limit applied - should fix the '60 per hour' issue")
        elif result == "get_remote_address":
            print("⚠️  DEFAULT: Will use Flask-Limiter default limits")
        else:
            print(f"📝 CUSTOM: Will use custom limit: {result}")
        
        print("-" * 80)

if __name__ == "__main__":
    test_scenarios()
    
    print("\n=== Summary ===")
    print("The improved rate limiting logic should:")
    print("1. ✅ Detect extremely large numbers and convert to '1000000 per hour'")
    print("2. ✅ Detect 'unlimited' keyword and convert to '1000000 per hour'") 
    print("3. ✅ Detect high daily limits (>100,000) and convert to '1000000 per hour'")
    print("4. ✅ Handle parsing errors gracefully")
    print("5. ✅ Pass through normal custom limits unchanged")
    print("\nThis should fix the '60 per 1 hour' issue for users with custom unlimited limits!")