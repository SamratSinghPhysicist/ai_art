# Stability AI API Key Management System

## Overview
This documentation explains how the Stability AI API key management system works. The system has been updated from tracking "credits" to tracking "usage count" for more reliable API key management.

## How It Works

### API Key Usage Tracking
- Each API key starts with a usage count of 0
- Every time the API key is used successfully, its usage count is incremented by 1
- API keys with a usage count of 3 or less are considered "usable"
- When selecting an API key, the system prioritizes the least recently used key with a usage count ≤ 3

### Migration from Credits System
The system previously tracked "credits" for each API key, assuming each key starts with 25 credits. The new system calculates usage count from the old credits value using the formula:
```
usage_count = max(0, 25 - credits_left)
```

## How to Use

### Finding a Usable API Key
```python
from models import StabilityApiKey

# Get an API key that has been used at most 3 times
api_key_obj = StabilityApiKey.find_usable_key(max_uses=3)

if api_key_obj:
    # Use the API key
    api_key = api_key_obj.api_key
    print(f"Using API key with usage count: {api_key_obj.usage_count}")
else:
    print("No usable API key found")
```

### Incrementing API Key Usage
After using an API key successfully, increment its usage count:
```python
from models import StabilityApiKey

# After successful API use
StabilityApiKey.increment_usage(api_key)
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
- `migrate_api_keys.py`: Converts existing API keys from the credits system to the usage count system
- `test_stability_api_key.py`: Tests API key functionality and lists available keys
- `update_api_keys.sh`: Runs migration and displays current API keys

### Commands
List all API keys:
```
python Development/test_stability_api_key.py --list
```

Find a usable API key:
```
python Development/test_stability_api_key.py --find --max-uses=3
```

Generate a new API key:
```
python Development/test_stability_api_key.py --generate
```

## Troubleshooting

### API Key Generation Issues
If the TempMail module is not available, the system will use a fallback mechanism. However, this fallback won't receive verification emails, so manual verification is required.

### Migration Issues
If migration fails, you can manually set the usage_count in the database:
```
db.stability_api_keys.updateMany({}, {$set: {usage_count: 0, last_used: new Date()}})
``` 