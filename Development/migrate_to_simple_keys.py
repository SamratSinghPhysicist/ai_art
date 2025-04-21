import os
import sys
import datetime
import argparse
from pymongo import MongoClient
from bson.objectid import ObjectId

# Add parent directory to path so we can import models
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(parent_dir)

# Make sure we can access the right database
from models import db, StabilityApiKey

def migrate_to_simple_keys():
    """
    Migrate API keys from the usage_count model to a simpler model that only
    tracks created_at and deletes keys after use.
    
    This script:
    1. Finds all API keys in the database
    2. For keys without created_at, sets it to now or copies from last_used if available
    3. Removes usage_count and last_used fields
    4. Ensures is_active field is set correctly
    """
    print("\n===== MIGRATING API KEYS TO SIMPLE MODEL =====")
    
    # Find all API keys in the database
    keys = db['stability_api_keys'].find()
    
    count = 0
    success_count = 0
    error_count = 0
    
    for key in keys:
        count += 1
        api_key = key['api_key']
        print(f"Migrating key {api_key[:5]}...{api_key[-4:]}")
        
        try:
            # Get the old fields or set defaults
            last_used = key.get('last_used')
            
            # Set created_at to last_used if available, otherwise use current time
            created_at = last_used if last_used else datetime.datetime.now()
            
            # Prepare the update data - include only the fields we want to keep
            update_data = {
                'api_key': api_key,
                'created_at': created_at,
                'is_active': key.get('is_active', True)
            }
            
            # Remove the old document and insert the new one
            db['stability_api_keys'].delete_one({'_id': key['_id']})
            db['stability_api_keys'].insert_one(update_data)
            
            print(f"  Migrated successfully to simple model")
            success_count += 1
                
        except Exception as e:
            print(f"  Error migrating key: {e}")
            error_count += 1
    
    print("\n===== MIGRATION SUMMARY =====")
    print(f"Total keys processed: {count}")
    print(f"Successfully migrated: {success_count}")
    print(f"Errors: {error_count}")
    
    # Count active keys after migration
    active_count = db['stability_api_keys'].count_documents({'is_active': True})
    print(f"Active keys in database: {active_count}")
    print("============================\n")

def import_from_env_var():
    """
    Import API key from the STABILITY_API_KEY environment variable and add to database
    """
    print("\n===== IMPORTING API KEY FROM ENVIRONMENT VARIABLE =====")
    
    # Get key from environment variable
    api_key = os.getenv('STABILITY_API_KEY')
    
    if not api_key:
        print("No STABILITY_API_KEY environment variable found. Skipping import.")
        return
    
    # Check if key already exists in database
    existing_key = db['stability_api_keys'].find_one({'api_key': api_key})
    
    if existing_key:
        print(f"API key {api_key[:5]}...{api_key[-4:]} already exists in database. Skipping import.")
        return
    
    try:
        # Create a new StabilityApiKey object
        stability_api_key = StabilityApiKey(
            api_key=api_key,
            created_at=datetime.datetime.now(),
            is_active=True
        )
        
        # Save to database
        stability_api_key.save()
        print(f"Successfully imported API key {api_key[:5]}...{api_key[-4:]} from environment variable")
        
        # Count keys in database
        key_count = db['stability_api_keys'].count_documents({'is_active': True})
        print(f"Total active API keys in database: {key_count}")
        
    except Exception as e:
        print(f"Error importing API key from environment variable: {e}")

def add_key(api_key):
    """
    Add a specific API key to the database
    """
    print(f"\n===== ADDING NEW API KEY =====")
    
    if not api_key:
        print("No API key provided. Skipping.")
        return
    
    # Check if key already exists in database
    existing_key = db['stability_api_keys'].find_one({'api_key': api_key})
    
    if existing_key:
        print(f"API key {api_key[:5]}...{api_key[-4:]} already exists in database. Skipping.")
        return
    
    try:
        # Create a new StabilityApiKey object
        stability_api_key = StabilityApiKey(
            api_key=api_key,
            created_at=datetime.datetime.now(),
            is_active=True
        )
        
        # Save to database
        stability_api_key.save()
        print(f"Successfully added API key {api_key[:5]}...{api_key[-4:]} to database")
        
        # Count keys in database
        key_count = db['stability_api_keys'].count_documents({'is_active': True})
        print(f"Total active API keys in database: {key_count}")
        
    except Exception as e:
        print(f"Error adding API key to database: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stability API Key Migration and Management")
    parser.add_argument("--migrate", action="store_true", help="Migrate existing keys to the new model")
    parser.add_argument("--import-env", action="store_true", help="Import API key from STABILITY_API_KEY environment variable")
    parser.add_argument("--add-key", help="Add a specific API key to the database")
    parser.add_argument("--all", action="store_true", help="Run migration and import from environment variable")
    
    args = parser.parse_args()
    
    # Default to all if no arguments provided
    if not any([args.migrate, args.import_env, args.add_key, args.all]):
        args.all = True
    
    if args.migrate or args.all:
        migrate_to_simple_keys()
    
    if args.import_env or args.all:
        import_from_env_var()
    
    if args.add_key:
        add_key(args.add_key) 