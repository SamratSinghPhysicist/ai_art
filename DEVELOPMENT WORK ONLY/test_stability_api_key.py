import os
import sys
import argparse
from models import StabilityApiKey
from StabilityApiGenerator.stability_api_generator import StabilityApiGenerator

def list_all_keys():
    """List all API keys stored in the database"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== STABILITY API KEYS IN DATABASE =====")
    keys = db['stability_api_keys'].find().sort('created_at', 1)
    
    found = False
    for idx, key in enumerate(keys, 1):
        found = True
        print(f"Key #{idx}:")
        print(f"  API Key: {key['api_key'][:5]}...{key['api_key'][-4:]}")
        print(f"  Created At: {key.get('created_at', 'Unknown')}")
        print(f"  Active: {key['is_active']}")
        print("-" * 40)
    
    if not found:
        print("No API keys found in the database")
    
    # Show total count
    count = StabilityApiKey.count_keys()
    print(f"Total active API keys: {count}")
    print("=========================================\n")

def check_keys():
    """Check if keys exist and count them"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== CHECKING API KEYS =====")
    count = StabilityApiKey.count_keys()
    print(f"Total active API keys available: {count}")
    
    # Find the oldest key
    oldest_key = StabilityApiKey.find_oldest_key()
    if oldest_key:
        print(f"Oldest key: {oldest_key.api_key[:5]}...{oldest_key.api_key[-4:]}")
        print(f"Created at: {oldest_key.created_at}")
    else:
        print("No active API keys found")
    
    print("==============================\n")

def generate_new_key():
    """Generate a new API key and save it to the database"""
    print("\n===== GENERATING NEW STABILITY API KEY =====")
    
    generator = None
    try:
        generator = StabilityApiGenerator()
        success = generator.generate_api_key()
        
        if success:
            print(f"Successfully generated new API key")
            return True
        else:
            print("Failed to generate new API key")
            return False
    except Exception as e:
        print(f"Error generating API key: {e}")
        return False
    finally:
        if generator:
            generator.close()
    
    print("===========================================\n")

def find_key():
    """Find the oldest API key"""
    print(f"\n===== FINDING OLDEST API KEY =====")
    
    key = StabilityApiKey.find_oldest_key()
    if key:
        print(f"Found oldest key: {key.api_key[:5]}...{key.api_key[-4:]}")
        print(f"Created At: {key.created_at}")
    else:
        print("No API keys available")
    
    print("================================\n")
    return key

def delete_key(api_key_str=None):
    """Delete a specific API key or the oldest one if no key specified"""
    if api_key_str:
        print(f"\n===== DELETING SPECIFIC API KEY =====")
        success = StabilityApiKey.delete_key(api_key_str)
        if success:
            print(f"Successfully deleted API key: {api_key_str[:5]}...{api_key_str[-4:]}")
        else:
            print(f"Failed to delete API key: {api_key_str[:5]}...{api_key_str[-4:]}")
    else:
        print(f"\n===== DELETING OLDEST API KEY =====")
        key = StabilityApiKey.find_oldest_key()
        if key:
            success = StabilityApiKey.delete_key(key.api_key)
            if success:
                print(f"Successfully deleted oldest API key: {key.api_key[:5]}...{key.api_key[-4:]}")
            else:
                print(f"Failed to delete oldest API key")
        else:
            print("No API keys available to delete")
    
    print("================================\n")

def main():
    parser = argparse.ArgumentParser(description="Test Stability API Key functionality")
    parser.add_argument("--list", action="store_true", help="List all API keys in the database")
    parser.add_argument("--check", action="store_true", help="Check API key count and find oldest key")
    parser.add_argument("--generate", action="store_true", help="Generate a new API key")
    parser.add_argument("--find", action="store_true", help="Find the oldest API key")
    parser.add_argument("--delete", action="store_true", help="Delete the oldest API key")
    parser.add_argument("--delete-key", help="Delete a specific API key by value")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any([args.list, args.check, args.generate, args.find, args.delete, args.delete_key, args.all]):
        parser.print_help()
        return
    
    if args.list or args.all:
        list_all_keys()
    
    if args.check or args.all:
        check_keys()
    
    if args.find or args.all:
        find_key()
    
    if args.delete:
        delete_key()
    
    if args.delete_key:
        delete_key(args.delete_key)
    
    if args.generate or args.all:
        generate_new_key()
        # Show updated list after generation
        if args.all:
            list_all_keys()

if __name__ == "__main__":
    main() 