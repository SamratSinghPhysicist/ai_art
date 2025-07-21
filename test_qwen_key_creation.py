#!/usr/bin/env python3
"""
Test script to verify that new Qwen API keys are created with the correct status field.
"""

import os
import sys
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

# Add the current directory to the path so we can import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import QwenApiKey, db

def test_qwen_key_creation():
    """Test creating a new Qwen API key and verify it has the correct status"""
    
    print("🧪 Testing Qwen API key creation...")
    
    # Create a test key
    test_key = QwenApiKey(
        auth_token="test_auth_token_123",
        chat_id="test_chat_id_456",
        fid="test_fid_789",
        children_ids=["child1", "child2"],
        x_request_id="test_x_request_id_abc"
    )
    
    print(f"✅ Created QwenApiKey object with status: {test_key.status}")
    
    # Save the key
    key_id = test_key.save()
    print(f"✅ Saved key with ID: {key_id}")
    
    # Verify the key was saved correctly
    if db is not None:
        saved_key = db['qwen_api_keys'].find_one({'_id': key_id})
        if saved_key:
            print(f"✅ Retrieved saved key with status: {saved_key.get('status')}")
            print(f"✅ Key has created_at: {saved_key.get('created_at')}")
            print(f"✅ Key has updated_at: {saved_key.get('updated_at')}")
            
            # Clean up - delete the test key
            QwenApiKey.delete(str(key_id))
            print("✅ Cleaned up test key")
            
            return saved_key.get('status') == 'available'
        else:
            print("❌ Could not retrieve saved key")
            return False
    else:
        print("❌ Database connection not available")
        return False

def list_all_keys():
    """List all existing keys and their status"""
    print("\n📋 Listing all existing Qwen API keys:")
    
    keys = QwenApiKey.get_all()
    if not keys:
        print("   No keys found")
        return
    
    for i, key in enumerate(keys, 1):
        status = key.get('status', 'NO STATUS')
        created_at = key.get('created_at', 'N/A')
        print(f"   {i}. Status: {status}, Created: {created_at}")

if __name__ == "__main__":
    # List existing keys first
    list_all_keys()
    
    # Test key creation
    success = test_qwen_key_creation()
    
    if success:
        print("\n✅ Test passed! New keys are created with 'available' status.")
    else:
        print("\n❌ Test failed! New keys are not getting the correct status.")
        sys.exit(1)