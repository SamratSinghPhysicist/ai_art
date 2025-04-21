import os
import sys
import argparse
from models import StabilityApiKey
from StabilityApiGenerator.stability_api_generator import StabilityApiGenerator

def list_all_keys():
    """List all API keys stored in the database with their credit status"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== STABILITY API KEYS IN DATABASE =====")
    keys = db['stability_api_keys'].find().sort('last_checked', 1)
    
    found = False
    for idx, key in enumerate(keys, 1):
        found = True
        print(f"Key #{idx}:")
        print(f"  API Key: {key['api_key'][:5]}...{key['api_key'][-4:]}")
        print(f"  Credits: {key['credits_left']}")
        print(f"  Last Checked: {key['last_checked']}")
        print(f"  Active: {key['is_active']}")
        print("-" * 40)
    
    if not found:
        print("No API keys found in the database")
    
    print("=========================================\n")

def refresh_credits():
    """Check and update credits for all API keys in the database"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== REFRESHING CREDITS FOR ALL KEYS =====")
    keys = db['stability_api_keys'].find({'is_active': True})
    
    count = 0
    for key in keys:
        count += 1
        api_key = key['api_key']
        print(f"Checking key {api_key[:5]}...{api_key[-4:]}")
        
        old_credits = key['credits_left']
        new_credits = StabilityApiKey.check_credits(api_key)
        
        if new_credits is not None:
            print(f"  Credits updated: {old_credits} -> {new_credits}")
        else:
            print(f"  Failed to check credits. Key might be invalid.")
            # Mark as inactive if we couldn't check credits
            db['stability_api_keys'].update_one(
                {'_id': key['_id']},
                {'$set': {'is_active': False}}
            )
            print(f"  Key marked as inactive.")
    
    if count == 0:
        print("No active API keys found in the database")
    
    print("==========================================\n")

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

def find_usable_key(min_credits=8):
    """Find a usable API key with sufficient credits"""
    print(f"\n===== FINDING USABLE KEY (MIN CREDITS: {min_credits}) =====")
    
    key = StabilityApiKey.find_usable_key(min_credits)
    if key:
        print(f"Found usable key: {key.api_key[:5]}...{key.api_key[-4:]}")
        print(f"Credits: {key.credits_left}")
        print(f"Last Checked: {key.last_checked}")
        
        # Verify credits
        actual_credits = StabilityApiKey.check_credits(key.api_key)
        if actual_credits is not None:
            print(f"Actual credits verified: {actual_credits}")
        else:
            print("Could not verify actual credits")
    else:
        print("No usable key found with sufficient credits")
    
    print("=================================================\n")
    return key

def main():
    parser = argparse.ArgumentParser(description="Test Stability API Key functionality")
    parser.add_argument("--list", action="store_true", help="List all API keys in the database")
    parser.add_argument("--refresh", action="store_true", help="Refresh credits for all keys")
    parser.add_argument("--generate", action="store_true", help="Generate a new API key")
    parser.add_argument("--find", action="store_true", help="Find a usable API key")
    parser.add_argument("--min-credits", type=int, default=8, help="Minimum credits for finding a usable key")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any([args.list, args.refresh, args.generate, args.find, args.all]):
        parser.print_help()
        return
    
    if args.list or args.all:
        list_all_keys()
    
    if args.refresh or args.all:
        refresh_credits()
    
    if args.find or args.all:
        find_usable_key(args.min_credits)
    
    if args.generate or args.all:
        generate_new_key()
        # Show updated list after generation
        if args.all:
            list_all_keys()

if __name__ == "__main__":
    main() 