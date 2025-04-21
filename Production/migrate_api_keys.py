import os
import sys
import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

# Add parent directory to path so we can import models
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(parent_dir)

# Make sure we can access the right database
from models import db

def migrate_api_keys():
    """
    Migrate API keys from the old credits_left model to the new usage_count model.
    
    This script:
    1. Finds all API keys in the database
    2. For keys with credits_left but no usage_count, calculates usage_count as (25 - credits_left)
    3. For keys with last_checked but no last_used, copies last_checked to last_used
    4. Updates all keys to have the usage_count and last_used fields
    """
    print("\n===== MIGRATING API KEYS TO NEW SCHEMA =====")
    
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
            credits_left = key.get('credits_left', 25)
            last_checked = key.get('last_checked', datetime.datetime.now())
            
            # Calculate the new fields
            # If a key had 25 credits, it has been used 0 times
            # If a key had 0 credits, it has been used 25 times
            usage_count = max(0, 25 - credits_left)
            last_used = key.get('last_used', last_checked)
            
            # Prepare the update data
            update_data = {
                'usage_count': usage_count,
                'last_used': last_used
            }
            
            # Update the document
            result = db['stability_api_keys'].update_one(
                {'_id': key['_id']},
                {'$set': update_data}
            )
            
            if result.modified_count > 0:
                print(f"  Migrated successfully: credits_left={credits_left} → usage_count={usage_count}")
                success_count += 1
            else:
                print(f"  No changes needed")
                success_count += 1
                
        except Exception as e:
            print(f"  Error migrating key: {e}")
            error_count += 1
    
    print("\n===== MIGRATION SUMMARY =====")
    print(f"Total keys processed: {count}")
    print(f"Successfully migrated: {success_count}")
    print(f"Errors: {error_count}")
    print("============================\n")

if __name__ == "__main__":
    migrate_api_keys() 