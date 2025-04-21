#!/bin/bash

echo "==== Updating API Key Management System ===="
echo "This script will migrate existing API keys from the credits system to the usage count system"
echo

# Install required packages
echo "Installing requirements..."
pip install -e Development/StabilityApiGenerator

# Run the migration script
echo "Running migration script..."
python Development/migrate_api_keys.py

# Display current API keys
echo "Running test to show current API keys..."
python Development/test_stability_api_key.py --list

echo
echo "==== Update Complete ===="
echo "To test if an API key is usable, run:"
echo "python Development/test_stability_api_key.py --find --max-uses=3"
echo 
echo "To generate a new API key, run:"
echo "python Development/test_stability_api_key.py --generate"
echo 