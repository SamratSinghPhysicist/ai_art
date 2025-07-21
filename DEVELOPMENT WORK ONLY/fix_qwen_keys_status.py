#!/usr/bin/env python3
"""
Migration script to fix Qwen API keys that are missing the status field.
This script will add 'status': 'available' to all keys that don't have a status field.
"""

import os
import sys
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_qwen_keys_status():
    """Fix Qwen API keys that are missing the status field"""
    
    # Get MongoDB connection details
    mongo_uri = os.getenv('MONGO_URI')
    if not mongo_uri:
        print("Error: MONGO_URI not found in environment variables")
        return False
    
    try:
        # Connect to MongoDB (using same approach as models.py)
        client = MongoClient(mongo_uri)
        db_name = os.getenv("DB_NAME", "ai_art_db")  # Use the same database name as in models.py
        db = client[db_name]
        collection = db['qwen_api_keys']
        
        print("Connected to MongoDB successfully")
        
        # Find keys without status field
        keys_without_status = list(collection.find({"status": {"$exists": False}}))
        
        if not keys_without_status:
            print("✅ All Qwen API keys already have status field")
            return True
        
        print(f"Found {len(keys_without_status)} keys without status field")
        
        # Update keys to add status and timestamps
        current_time = datetime.now(timezone.utc)
        
        result = collection.update_many(
            {"status": {"$exists": False}},
            {
                "$set": {
                    "status": "available",
                    "updated_at": current_time,
                    "created_at": current_time  # Set created_at if missing
                }
            }
        )
        
        print(f"✅ Updated {result.modified_count} keys with status 'available'")
        
        # Also ensure all keys have updated_at field
        keys_without_updated_at = collection.count_documents({"updated_at": {"$exists": False}})
        if keys_without_updated_at > 0:
            collection.update_many(
                {"updated_at": {"$exists": False}},
                {"$set": {"updated_at": current_time}}
            )
            print(f"✅ Added updated_at field to {keys_without_updated_at} keys")
        
        # Show final status
        total_keys = collection.count_documents({})
        available_keys = collection.count_documents({"status": "available"})
        generating_keys = collection.count_documents({"status": "generating"})
        
        print(f"\n📊 Final Status:")
        print(f"   Total keys: {total_keys}")
        print(f"   Available: {available_keys}")
        print(f"   Generating: {generating_keys}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    print("🔧 Fixing Qwen API keys status...")
    success = fix_qwen_keys_status()
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)