# Stability AI API Key Management System

## Overview
This documentation explains how the Stability AI API key management system works. The system has been simplified to use a "use once and delete" approach for API keys.

## How It Works

### API Key Management
- Each API key is stored in the database with a creation timestamp
- When an API key is needed, the system selects the oldest key available
- After each successful API request, the used key is deleted from the database
- New API keys can be generated and added to the database as needed

### Benefits of This Approach
- Simple management: no need to track usage count or credits
- Guaranteed fresh keys for each request
- Easy to troubleshoot: just add more keys to the pool when needed

## How to Use

### Finding an API Key
```python
from models import StabilityApiKey

# Get the oldest API key from the database
api_key_obj = StabilityApiKey.find_oldest_key()

if api_key_obj:
    # Use the API key
    api_key = api_key_obj.api_key
    print(f"Using API key: {api_key[:5]}...{api_key[-4:]}")
else:
    print("No API keys available in the database")
```

### Deleting an API Key After Use
```python
from models import StabilityApiKey

# After using an API key, delete it from the database
StabilityApiKey.delete_key(api_key)
```

### Generating New API Keys
Use the StabilityApiGenerator to create new API keys when needed:
```python
from StabilityApiGenerator.stability_api_generator import StabilityApiGenerator

generator = StabilityApiGenerator()
success = generator.generate_api_key()

if success:
    print("Successfully generated new API key")
```

## Utilities

### Scripts
- `migrate_to_simple_keys.py`: Converts existing API keys to the new simpler model
- `test_stability_api_key.py`: Tests API key functionality and lists available keys
- `update_api_keys.sh`: Runs migration and displays current API keys

### Commands
List all API keys:
```
python Development/test_stability_api_key.py --list
```

Find the oldest API key:
```
python Development/test_stability_api_key.py --find
```

Generate a new API key:
```
python Development/test_stability_api_key.py --generate
```

Delete the oldest API key:
```
python Development/test_stability_api_key.py --delete
```

Delete a specific API key:
```
python Development/test_stability_api_key.py --delete-key "sk-your-key-here"
```

## Troubleshooting

### Running Out of API Keys
If you're running out of API keys, generate more using:
```
python Development/test_stability_api_key.py --generate
```

You can also check how many keys are available:
```
python Development/test_stability_api_key.py --check
```

### API Key Generation Issues
If the TempMail module is not available, the system will use a fallback mechanism. However, this fallback won't receive verification emails, so manual verification is required.

### Migration Issues
If migration fails, you can manually update the database with:
```
db.stability_api_keys.updateMany({}, {$set: {created_at: new Date(), is_active: true}})
``` 