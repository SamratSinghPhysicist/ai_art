# Stability API Key Generator

This tool automatically generates Stability AI API keys for use in image generation tasks. 

## Features

- Automatically creates Stability AI accounts
- Generates and stores API keys in a MongoDB database
- Tracks credit usage per API key
- Supports dynamic API key selection based on credit availability

## How It Works

1. The `StabilityApiGenerator` class uses Selenium to automate the process of:
   - Creating new accounts with temporary email addresses
   - Verifying the accounts
   - Generating API keys

2. API keys are stored in:
   - A text file (`stability_api_key.txt`) for backward compatibility
   - The MongoDB database (in the `stability_api_keys` collection)

3. The system tracks:
   - The number of credits remaining for each key
   - When the credits were last checked
   - Whether the key is active or not

## Credit Management

API keys from Stability AI come with a limited number of credits. This system:

- Checks the number of credits available for each key
- Only uses keys that have sufficient credits (by default, at least 8 credits)
- Uses the oldest key (by last checked date) that meets the credit requirement
- Updates credit information after each use

## Usage

### Generating a New API Key

```python
from StabilityApiGenerator.stability_api_generator import StabilityApiGenerator

generator = StabilityApiGenerator()
success = generator.generate_api_key()
generator.close()
```

### Testing and Managing API Keys

Use the provided `test_stability_api_key.py` script:

```bash
# List all keys in the database
python test_stability_api_key.py --list

# Refresh credits for all keys
python test_stability_api_key.py --refresh

# Find a usable key with at least 8 credits
python test_stability_api_key.py --find --min-credits 8

# Generate a new key
python test_stability_api_key.py --generate

# Run all tests
python test_stability_api_key.py --all
```

### Using API Keys in Image Generation

The `img2img_stability.py` script has been updated to work with the database:

```bash
# Using a key from the database
python img2img_stability.py --prompt "your prompt" --image "input.jpg"

# Using a specific API key
python img2img_stability.py --api-key "your-api-key" --prompt "your prompt" --image "input.jpg"
```

## Requirements

See `requirements.txt` in the main project directory for all dependencies.

## License

Internal use only - not for distribution. 