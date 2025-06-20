#!/bin/bash

echo "==== Updating API Key Management System ===="
echo "This script will migrate existing API keys to the simplified model"
echo "where keys are deleted after use instead of tracking usage count."
echo

# Install required packages
echo "Installing requirements..."
pip install -e Development/StabilityApiGenerator

# Run the migration script
echo "Running migration script..."
python Development/migrate_to_simple_keys.py

# Display current API keys
echo "Running test to show current API keys..."
python Development/test_stability_api_key.py --list

echo
echo "==== Update Complete ===="
echo "To find the oldest API key, run:"
echo "python Development/test_stability_api_key.py --find"
echo 
echo "To generate a new API key, run:"
echo "python Development/test_stability_api_key.py --generate"
echo
echo "To delete the oldest API key, run:"
echo "python Development/test_stability_api_key.py --delete"
echo 