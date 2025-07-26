#!/usr/bin/env python3
"""
Test script to verify the rate limiting fix
"""

import requests
import json
import time

def test_debug_endpoint(base_url="http://localhost:5000"):
    """Test the debug endpoint to see current rate limit configuration"""
    try:
        print("=== Testing Debug Endpoint ===")
        response = requests.get(f"{base_url}/debug/rate-limit-info")
        if response.status_code == 200:
            data = response.json()
            print("Rate limit debug info:")
            print(json.dumps(data, indent=2, default=str))
        else:
            print(f"Debug endpoint failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error testing debug endpoint: {e}")

def test_api_endpoint(base_url="http://localhost:5000", endpoint="/api/generate"):
    """Test an API endpoint to see if rate limiting is working"""
    try:
        print(f"\n=== Testing API Endpoint {endpoint} ===")
        
        # Test data for image generation
        test_data = {
            "prompt": "test image",
            "model": "gemini"
        }
        
        response = requests.post(f"{base_url}{endpoint}", json=test_data)
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers:")
        for header, value in response.headers.items():
            if 'rate' in header.lower() or 'limit' in header.lower():
                print(f"  {header}: {value}")
        
        if response.status_code == 429:
            print("Rate limit hit!")
            print(f"Response: {response.text}")
        else:
            print(f"Response: {response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text}")
            
    except Exception as e:
        print(f"Error testing API endpoint: {e}")

def check_custom_limits_via_admin(base_url="http://localhost:5000", admin_secret="your-admin-secret"):
    """Check custom rate limits via admin API"""
    try:
        print("\n=== Checking Custom Rate Limits ===")
        headers = {'X-Admin-Secret-Key': admin_secret}
        response = requests.get(f"{base_url}/admin/api/custom-rate-limits", headers=headers)
        
        if response.status_code == 200:
            limits = response.json()
            if limits:
                print("Custom rate limits found:")
                for limit in limits:
                    print(f"  IP: {limit['ip']}, Endpoint: {limit['endpoint']}, Limit: {limit['limit_string']}")
            else:
                print("No custom rate limits found")
        else:
            print(f"Failed to get custom limits: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error checking custom limits: {e}")

if __name__ == "__main__":
    print("=== Rate Limit Fix Test Script ===")
    
    # You can change these values
    BASE_URL = "http://localhost:5000"  # Change to your server URL
    ADMIN_SECRET = "your-admin-secret-here"  # Replace with your actual admin secret
    
    # Test the debug endpoint
    test_debug_endpoint(BASE_URL)
    
    # Test an API endpoint
    test_api_endpoint(BASE_URL, "/api/generate")
    
    # Check custom limits (requires admin secret)
    # check_custom_limits_via_admin(BASE_URL, ADMIN_SECRET)
    
    print("\n=== Test Complete ===")
    print("If you're still seeing '60 per 1 hour', check:")
    print("1. Your custom rate limits are properly set in the database")
    print("2. The IP address matches exactly")
    print("3. The endpoint name matches exactly")
    print("4. Check the application logs for the debug messages")