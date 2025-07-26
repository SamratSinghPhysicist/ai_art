#!/usr/bin/env python3
"""
Debug script to test rate limiting functionality
"""

import requests
import json
import time
from ip_utils import get_custom_rate_limit
from models import custom_rate_limits_collection

def test_rate_limit_endpoint():
    """Test the rate limit debug endpoint"""
    try:
        response = requests.get('http://localhost:5000/debug/rate-limit-info')
        print("Rate limit info response:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error testing rate limit endpoint: {e}")

def check_custom_limits_in_db():
    """Check what custom rate limits are stored in the database"""
    print("\n=== Custom Rate Limits in Database ===")
    if custom_rate_limits_collection is not None:
        limits = list(custom_rate_limits_collection.find())
        if limits:
            for limit in limits:
                print(f"IP: {limit['ip']}, Endpoint: {limit['endpoint']}, Limit: {limit['limit_string']}")
        else:
            print("No custom rate limits found in database")
    else:
        print("Database not connected")

def test_specific_ip_endpoint(ip, endpoint):
    """Test rate limit for specific IP and endpoint"""
    print(f"\n=== Testing IP {ip} for endpoint {endpoint} ===")
    custom_limit = get_custom_rate_limit(ip, endpoint)
    if custom_limit:
        print(f"Custom limit found: {custom_limit}")
    else:
        print("No custom limit found - will use default")

if __name__ == "__main__":
    print("=== Rate Limit Debug Script ===")
    
    # Test database connection
    check_custom_limits_in_db()
    
    # Test specific IPs (replace with your actual IPs)
    test_ips = [
        "127.0.0.1",
        "your-server-ip-here",  # Replace with your actual server IP
    ]
    
    test_endpoints = [
        "api_generate_image",
        "generate_image",
        "api_text_to_video_generate"
    ]
    
    for ip in test_ips:
        for endpoint in test_endpoints:
            test_specific_ip_endpoint(ip, endpoint)
    
    # Test the debug endpoint if server is running
    print("\n=== Testing Debug Endpoint ===")
    test_rate_limit_endpoint()