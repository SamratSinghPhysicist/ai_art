# Stability API Key Generator

This application automates the process of generating a Stability API key using a temporary email.

## Setup

1. Install Python 3.7 or later
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Download Chrome browser if not already installed
4. **Important**: Download the appropriate ChromeDriver for your Chrome browser version:
   - Download from: https://chromedriver.chromium.org/downloads
   - Make sure the ChromeDriver version matches your Chrome browser version
   - Place the `chromedriver.exe` (Windows) or `chromedriver` (Mac/Linux) in the same directory as the script

## Usage

Run the main script:
```
python stability_api_generator.py
```

The script will:
1. Generate a temporary email using Mail.tm API
2. Open a Chrome browser window
3. Navigate to the Stability AI platform
4. Automatically sign up with the temporary email
5. Verify the account through the verification email
6. Copy the API key and save it to `stability_api_key.txt`

## Troubleshooting

- **ChromeDriver Error**: If you encounter `NoneType object has no attribute 'split'` or other driver-related errors, download the correct ChromeDriver version for your Chrome browser and place it in the script directory.
- **Clipboard Access Issue**: The script needs access to the clipboard to retrieve the API key. Make sure pyperclip is properly installed and your system allows clipboard access.
- **Timing Issues**: If elements aren't found, the script includes fallback selectors. Check the logs to see where it's failing.

## Logs

The application creates detailed logs in `stability_api_generator.log` that can help troubleshoot any issues.

## Files

- `temp_mail.py`: Contains the TempMail class for generating and managing temporary emails
- `stability_api_generator.py`: Main application that uses Selenium to automate the API key generation process
- `requirements.txt`: List of required Python packages 