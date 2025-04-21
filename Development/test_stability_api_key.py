import os
import sys
import argparse
from models import StabilityApiKey
from StabilityApiGenerator.stability_api_generator import StabilityApiGenerator

def list_all_keys():
    """List all API keys stored in the database with their usage count"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== STABILITY API KEYS IN DATABASE =====")
    keys = db['stability_api_keys'].find().sort('last_used', 1)
    
    found = False
    for idx, key in enumerate(keys, 1):
        found = True
        print(f"Key #{idx}:")
        print(f"  API Key: {key['api_key'][:5]}...{key['api_key'][-4:]}")
        print(f"  Usage Count: {key.get('usage_count', 0)}")
        print(f"  Last Used: {key.get('last_used', 'Never')}")
        print(f"  Active: {key['is_active']}")
        # For backward compatibility, show simulated credits
        simulated_credits = max(0, 25 - key.get('usage_count', 0))
        print(f"  Simulated Credits: {simulated_credits}")
        print("-" * 40)
    
    if not found:
        print("No API keys found in the database")
    
    print("=========================================\n")

def update_usage_info():
    """Update the last_used timestamp for all API keys in the database"""
    from pymongo import MongoClient
    from models import db
    
    print("\n===== UPDATING USAGE INFO FOR ALL KEYS =====")
    keys = db['stability_api_keys'].find({'is_active': True})
    
    count = 0
    for key in keys:
        count += 1
        api_key = key['api_key']
        print(f"Checking key {api_key[:5]}...{api_key[-4:]}")
        
        # For each key, check if it exists and update the last_used timestamp
        result = StabilityApiKey.check_credits(api_key)
        
        if result is not None:
            usage_count = key.get('usage_count', 0)
            simulated_credits = max(0, 25 - usage_count)
            print(f"  Current usage count: {usage_count} (simulated credits: {simulated_credits})")
        else:
            print(f"  Failed to check key. Key might be invalid.")
            # Mark as inactive if we couldn't check
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

def find_usable_key(max_uses=3):
    """Find a usable API key with acceptable usage count"""
    print(f"\n===== FINDING USABLE KEY (MAX USES: {max_uses}) =====")
    
    key = StabilityApiKey.find_usable_key(max_uses)
    if key:
        print(f"Found usable key: {key.api_key[:5]}...{key.api_key[-4:]}")
        print(f"Usage Count: {key.usage_count}")
        print(f"Last Used: {key.last_used}")
        
        # For backward compatibility, show simulated credits
        simulated_credits = max(0, 25 - key.usage_count)
        print(f"Simulated Credits: {simulated_credits}")
    else:
        print(f"No usable key found with usage count ≤ {max_uses}")
    
    print("=================================================\n")
    return key

def main():
    parser = argparse.ArgumentParser(description="Test Stability API Key functionality")
    parser.add_argument("--list", action="store_true", help="List all API keys in the database")
    parser.add_argument("--update", action="store_true", help="Update usage info for all keys")
    parser.add_argument("--generate", action="store_true", help="Generate a new API key")
    parser.add_argument("--find", action="store_true", help="Find a usable API key")
    parser.add_argument("--max-uses", type=int, default=3, help="Maximum usage count for finding a usable key")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any([args.list, args.update, args.generate, args.find, args.all]):
        parser.print_help()
        return
    
    if args.list or args.all:
        list_all_keys()
    
    if args.update or args.all:
        update_usage_info()
    
    if args.find or args.all:
        find_usable_key(args.max_uses)
    
    if args.generate or args.all:
        generate_new_key()
        # Show updated list after generation
        if args.all:
            list_all_keys()

if __name__ == "__main__":
    main() 