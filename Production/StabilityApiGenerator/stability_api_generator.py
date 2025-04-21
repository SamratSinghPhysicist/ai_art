import time
import random
import pyperclip
import os
import logging
import sys
import traceback
import platform
import datetime

# Print system information for debugging in CI
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"Working directory: {os.getcwd()}")
print(f"Directory contents: {os.listdir('.')}")

# Add parent directory to path so we can import models
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)
print(f"Parent directory added to path: {parent_dir}")

try:
    from models import StabilityApiKey
    print("Successfully imported StabilityApiKey model")
except ImportError as e:
    print(f"ERROR: Failed to import StabilityApiKey model: {e}")
    traceback.print_exc()

# Setup logging to console and file
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler("stability_generator.log")  # Also log to file for GitHub artifacts
    ]
)
logger = logging.getLogger(__name__)
logger.info("Logger initialized")

# Check environment variables
mongo_uri = os.environ.get('MONGO_URI')
logger.info(f"MONGO_URI is {'set' if mongo_uri else 'NOT SET'}")

# Check for GitHub Actions environment
is_ci = os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')
logger.info(f"Running in CI environment: {is_ci is not None}")
if is_ci:
    # List all environment variables in CI (without exposing secrets)
    logger.info("CI environment variables (names only):")
    for key in os.environ:
        if 'secret' not in key.lower() and 'token' not in key.lower() and 'password' not in key.lower():
            logger.info(f"  {key}")

# Import Selenium after logging setup
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.common.keys import Keys
    logger.info("Successfully imported Selenium modules")
except ImportError as e:
    logger.critical(f"Failed to import Selenium modules: {e}")
    traceback.print_exc()
    sys.exit(1)

# Make TempMail optional - provide a fallback if not available
TEMP_MAIL_AVAILABLE = False
try:
    from temp_mail import TempMail
    logger.info("Successfully imported TempMail module")
    TEMP_MAIL_AVAILABLE = True
except ImportError as e:
    logger.warning(f"TempMail module not available: {e}")
    logger.warning("Will use fallback mechanism for email")
    
    # Define a simple fallback TempMail class
    class FallbackTempMail:
        def __init__(self):
            logger.info("Using FallbackTempMail")
            
        def create_account(self):
            # Generate a random email that won't actually receive emails
            # but will allow the signup process to proceed
            import random
            import string
            random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{random_str}@example.com"
            logger.info(f"FallbackTempMail created fake email: {email}")
            return {"email": email, "password": "Study@123"}
            
        def get_messages(self, account):
            # Always return empty list - no actual emails will be received
            return []
            
        def get_message_details(self, account, message_id):
            # No actual messages will be received
            return None

class StabilityApiGenerator:
    def __init__(self):
        logger.info("Initializing StabilityApiGenerator")
        self.temp_mail = TempMail() if TEMP_MAIL_AVAILABLE else FallbackTempMail()
        self.setup_driver()
        self.api_key = None
        
    def setup_driver(self):
        """Set up the Selenium WebDriver"""
        logger.info("Setting up Chrome WebDriver")
        chrome_options = Options()
        
        # Check if running in GitHub Actions or CI environment
        is_ci = os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')
        if is_ci:
            logger.info("Running in CI environment - using headless mode with enhanced options")
            chrome_options.add_argument("--headless=new")  # New headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--dns-prefetch-disable")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        else:
            # Uncomment the line below to run in headless mode locally
        # chrome_options.add_argument("--headless")
            pass
            
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        
        # Add additional options for CI
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--v=1")  # Verbose logging
        
        # Log all Chrome options for debugging
        logger.info(f"Chrome options: {chrome_options.arguments}")
        
        try:
            # Use webdriver-manager for automatic ChromeDriver management
            logger.info("Using webdriver-manager for ChromeDriver management")
            from webdriver_manager.chrome import ChromeDriverManager
            # ChromeType is no longer available in webdriver-manager 4.0.1+
            
            try:
                # Check Chrome version to use specific driver version if needed
                import subprocess
                try:
                    chrome_version_output = subprocess.check_output(["google-chrome", "--version"]).decode("utf-8").strip()
                    logger.info(f"Detected Chrome version: {chrome_version_output}")
                    chrome_major_version = chrome_version_output.split()[-1].split('.')[0]
                    logger.info(f"Chrome major version: {chrome_major_version}")
                    
                    # Use specific driver version for Chrome 135
                    if chrome_major_version == "135":
                        logger.info("Using known compatible ChromeDriver version for Chrome 135")
                        self.driver = webdriver.Chrome(
                            service=Service(ChromeDriverManager(version="135.0.7049.0").install()),
                            options=chrome_options
                        )
                    else:
                        # Let webdriver manager pick the right version
                        self.driver = webdriver.Chrome(
                            service=Service(ChromeDriverManager().install()),
                            options=chrome_options
                        )
                except Exception as e:
                    # If Chrome version detection fails, use default
                    logger.warning(f"Failed to detect Chrome version: {e}")
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                    options=chrome_options
                )
                
                logger.info("ChromeDriver initialized successfully with webdriver-manager")
            except Exception as e:
                logger.error(f"Error initializing ChromeDriver with webdriver-manager: {e}")
                
                # Fallback to alternative methods
                try:
                    # Try using system ChromeDriver if available
                    logger.info("Trying system ChromeDriver")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    logger.info("ChromeDriver initialized using system executable")
                except Exception as e2:
                    logger.critical(f"Failed to initialize ChromeDriver: {e2}")
                    raise Exception("Could not initialize ChromeDriver by any method") from e
            
            # Set up wait times
            self.wait = WebDriverWait(self.driver, 60)
            logger.info("WebDriver initialization complete")
            
        except Exception as e:
            logger.critical(f"WebDriver setup failed: {e}")
            raise
        
    def navigate_to_stability_platform(self):
        """Navigate to the Stability AI platform"""
        logger.info("Navigating to Stability AI platform")
        try:
            self.driver.get("https://platform.stability.ai/")
            logger.info("Navigated to Stability AI platform successfully")
        except Exception as e:
            logger.error(f"Failed to navigate to Stability AI platform: {e}")
            raise
        
    def click_element_safely(self, selector, selector_type=By.CSS_SELECTOR, timeout=30, sleep_after=0):
        """Click an element safely after waiting for it to be clickable"""
        logger.info(f"Attempting to click element: {selector}")
        try:
            element = self.wait.until(EC.element_to_be_clickable((selector_type, selector)))
            element.click()
            logger.info(f"Clicked on element: {selector}")
            if sleep_after > 0:
                logger.info(f"Sleeping for {sleep_after} seconds")
                time.sleep(sleep_after)
            return True
        except Exception as e:
            logger.error(f"Failed to click element {selector}: {e}")
            return False
            
    def fill_input_safely(self, selector, text, selector_type=By.CSS_SELECTOR, timeout=30, sleep_after=0):
        """Fill an input field safely after waiting for it to be visible"""
        logger.info(f"Attempting to fill input {selector} with text: {text}")
        try:
            element = self.wait.until(EC.visibility_of_element_located((selector_type, selector)))
            element.clear()
            element.send_keys(text)
            logger.info(f"Filled input {selector} with text: {text}")
            if sleep_after > 0:
                logger.info(f"Sleeping for {sleep_after} seconds")
                time.sleep(sleep_after)
            return True
        except Exception as e:
            logger.error(f"Failed to fill input {selector}: {e}")
            return False
            
    def extract_verification_link(self, html_content):
        """Extract verification link from email HTML content using multiple methods"""
        logger.info("Attempting to extract verification link from email")
        
        # Convert html_content to string if it's a list
        if isinstance(html_content, list):
            logger.info("HTML content is a list, joining elements")
            html_content = ''.join(html_content)
        
        # Save HTML content to a file for debugging
        try:
            with open("email_content.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("Saved email HTML content to email_content.html for debugging")
        except Exception as e:
            logger.error(f"Error saving HTML content to file: {e}")
        
        # Method 1: Look for common verification button/link text
        logger.info("Method 1: Looking for common verification text")
        verification_texts = [
            "Confirm my account",
            "Confirm my account",
            "Confirm my account",
        ]
        
        for text in verification_texts:
            if text in html_content:
                logger.info(f"Found '{text}' in email")
                # Try to find a nearby link - search 200 chars before and after
                text_pos = html_content.find(text)
                search_start = max(0, text_pos - 200)
                search_end = min(len(html_content), text_pos + 200 + len(text))
                search_area = html_content[search_start:search_end]
                
                # Look for href in the search area
                href_start = search_area.find('href="')
                if href_start != -1:
                    href_start += 6  # Length of 'href="'
                    href_end = search_area.find('"', href_start)
                    if href_end != -1:
                        link = search_area[href_start:href_end]
                        link = link.replace("&amp;", "&")
                        logger.info(f"Method 1 found link near '{text}': {link}")
                        return link
        
        logger.info("No verification text with nearby link found")
        
        # Method 2: Look for common domain patterns
        logger.info("Method 2: Looking for verification domains")
        verification_domains = [
            "stabilityai.us.auth0.com",
            "auth0.com/u/email-verification",
            "platform.stability.ai/verify",
            "stability.ai/verify",
            "verify",
            "confirmation",
            "email/confirm"
        ]
        
        import re
        # Find all href links in the HTML
        all_links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html_content)
        logger.info(f"Found {len(all_links)} links in the email")
        
        for link in all_links:
            logger.info(f"Checking link: {link}")
            if any(domain in link.lower() for domain in verification_domains):
                link = link.replace("&amp;", "&")
                logger.info(f"Method 2 found verification domain link: {link}")
                return link
        
        # Method 3: Extract all links and check for common verification patterns
        logger.info("Method 3: Examining all links for verification patterns")
        verification_keywords = ["verify", "verification", "confirm", "email-verification", 
                              "ticket", "activate", "account", "auth0", "stability"]
        
        for link in all_links:
            link_lower = link.lower()
            if any(keyword in link_lower for keyword in verification_keywords):
                link = link.replace("&amp;", "&")
                logger.info(f"Method 3 found likely verification link: {link}")
                return link
        
        # Method 4: Look for button with verification text
        logger.info("Method 4: Looking for button elements with verification text")
        button_patterns = [
            r'<button[^>]*>(.*?Confirm.*?)</button>',
            r'<button[^>]*>(.*?Verify.*?)</button>',
            r'<button[^>]*>(.*?Activate.*?)</button>',
            r'<a[^>]*class="[^"]*button[^"]*"[^>]*>(.*?Confirm.*?)</a>',
            r'<a[^>]*class="[^"]*btn[^"]*"[^>]*>(.*?Verify.*?)</a>'
        ]
        
        for pattern in button_patterns:
            buttons = re.findall(pattern, html_content, re.IGNORECASE)
            for button_text in buttons:
                logger.info(f"Found button with text: {button_text}")
                # Find the href around this button
                button_pos = html_content.find(button_text)
                if button_pos != -1:
                    search_start = max(0, button_pos - 100)
                    search_end = min(len(html_content), button_pos + 100)
                    button_area = html_content[search_start:search_end]
                    href_start = button_area.find('href="')
                    if href_start != -1:
                        href_start += 6
                        href_end = button_area.find('"', href_start)
                        if href_end != -1:
                            link = button_area[href_start:href_end]
                            link = link.replace("&amp;", "&")
                            logger.info(f"Method 4 found link near button: {link}")
                            return link
        
        # If all methods fail, log all links found for debugging
        logger.warning("Could not find verification link with any method. All links found:")
        for i, link in enumerate(all_links):
            logger.warning(f"Link {i+1}: {link}")
        
        return None
        
    def is_valid_full_api_key(self, key):
        """Check if the key is a valid full API key (no asterisks)"""
        if not key or not key.startswith("sk-"):
            return False
            
        # Check key doesn't contain asterisks (masked key)
        if "*" in key:
            logger.warning(f"Rejecting masked API key: {key}")
            return False
            
        # Check key length (should be around 50 chars)
        if len(key) < 30:
            logger.warning(f"API key too short: {len(key)} chars")
            return False
            
        # Check key format (should be alphanumeric after the "sk-" prefix)
        import re
        if not re.match(r'^sk-[a-zA-Z0-9]{30,60}$', key):
            logger.warning(f"API key has invalid format")
            return False
            
        logger.info(f"Valid full API key detected: {key[:5]}*****{key[-4:]}")
        return True
        
    def handle_alerts(self):
        """Handle any alerts on the page"""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            logger.info(f"Alert found: '{alert_text}'")
            alert.accept()
            logger.info("Alert accepted")
            return True
        except Exception as e:
            logger.info(f"No alert present or error handling alert: {e}")
            return False
            
    def try_clipboard_access(self):
        """Try multiple methods to access the clipboard content"""
        # First try regular pyperclip paste
        try:
            logger.info("Trying standard clipboard access")
            clipboard_content = pyperclip.paste()
            if clipboard_content and self.is_valid_full_api_key(clipboard_content):
                logger.info(f"Found valid API key in clipboard: {clipboard_content[:5]}*****{clipboard_content[-4:]}")
                return clipboard_content
        except Exception as e:
            logger.error(f"Error accessing clipboard with pyperclip: {e}")
        
        # Try using keyboard shortcuts with actionchains
        try:
            logger.info("Trying keyboard shortcuts Ctrl+C, Enter")
            # First focus on the element with the API key
            api_key_element = self.driver.find_element(By.CSS_SELECTOR, "div.truncate")
            self.driver.execute_script("arguments[0].focus();", api_key_element)
            time.sleep(1)
            
            # Try Ctrl+C
            webdriver.ActionChains(self.driver)\
                .key_down(Keys.CONTROL)\
                .send_keys('c')\
                .key_up(Keys.CONTROL)\
                .perform()
            time.sleep(1)
            
            # Try pressing Enter if needed
            webdriver.ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            time.sleep(1)
            
            # Check clipboard
            clipboard_content = pyperclip.paste()
            if clipboard_content and self.is_valid_full_api_key(clipboard_content):
                logger.info(f"Found valid API key in clipboard after keyboard shortcuts: {clipboard_content[:5]}*****{clipboard_content[-4:]}")
                return clipboard_content
        except Exception as e:
            logger.error(f"Error using keyboard shortcuts: {e}")
        
        # If we're here, we couldn't get the API key from clipboard
        return None

    def extract_api_key(self):
        """Extract API key from the page using multiple methods"""
        logger.info("Attempting to extract API key from the page")
        
        # Method 1: Try getting API key from clipboard first
        try:
            logger.info("Method 1: Trying to get API key from clipboard")
            api_key = self.try_clipboard_access()
            if api_key:
                return api_key
            else:
                logger.info("Could not find valid API key in clipboard")
        except Exception as e:
            logger.error(f"Error accessing clipboard: {e}")
            
        # Method 2: Try to make API key visible by clicking the eye button and extract from page
        logger.info("Method 2: Trying to make API key visible and extract from page")
        try:
            # Take a screenshot before attempting to click the eye button
            self.driver.save_screenshot("before_eye_button_click.png")
            logger.info("Saved screenshot before attempting to click eye button")
            
            # Log all buttons on the page to help diagnose which one to target
            try:
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                logger.info(f"Found {len(all_buttons)} buttons on the page")
                for i, button in enumerate(all_buttons):
                    text = button.text.strip() if button.text else "No text"
                    classes = button.get_attribute("class") or "No class"
                    logger.info(f"Button {i+1}: Text='{text}', Class='{classes}'")
            except Exception as e:
                logger.error(f"Error listing buttons: {e}")
            
            # IMPORTANT: Avoid "Create API Key" button by explicitly excluding buttons with text
            # Look for the "eye" button to show the API key - very specific selectors
            eye_button_selectors = [
                # Target eye buttons without text (view buttons typically have no text, just an icon)
                "button.bg-brand-amber-1:not(:has(text))",
                "button.bg-brand-amber-1:empty",
                
                # Target specifically by icon presence - the eye has a circle inside it
                "button.bg-brand-amber-1:has(svg:has(circle))",
                "button:has(svg:has(circle[cx='12'][cy='12']))",
                
                # Target by SVG path for the eye
                "button:has(svg:has(path[d='M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z']))",
                
                # XPath selectors that are more specific
                "//button[contains(@class, 'bg-brand-amber-1')][.//circle[@cx='12' and @cy='12']]",
                "//button[contains(@class, 'bg-brand-amber-1')][not(text())]",
                
                # Specifically exclude buttons with "Create" text
                "//button[contains(@class, 'bg-brand-amber-1')][not(contains(., 'Create'))]",
                
                # If there are multiple similar buttons, target by position relative to the API key display
                "//div[contains(@class, 'truncate')]/following-sibling::button",
                "//div[contains(@class, 'truncate')]/preceding-sibling::button"
            ]
            
            eye_button_found = False
            for selector in eye_button_selectors:
                selector_type = By.CSS_SELECTOR
                if selector.startswith("//"):
                    selector_type = By.XPATH
                    
                logger.info(f"Trying eye button selector: {selector}")
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    logger.info(f"Found {len(elements)} elements with selector: {selector}")
                    
                    if elements:
                        # For safety, get the first button that doesn't have "Create" in its text
                        for element in elements:
                            button_text = element.text.strip()
                            logger.info(f"Button text: '{button_text}'")
                            
                            if not button_text or "Create" not in button_text:
                                logger.info(f"Clicking button without 'Create' text")
                                element.click()
                                eye_button_found = True
                                time.sleep(2)
                                break
                        
                        if eye_button_found:
                            break
                except Exception as e:
                    logger.error(f"Error with selector {selector}: {e}")
            
            # If standard methods fail, try JavaScript that specifically targets the eye icon
            if not eye_button_found:
                logger.info("Trying JavaScript to click eye button")
                js_scripts = [
                    # Specifically target eye button by circle element
                    "document.querySelector('button svg circle[cx=\"12\"][cy=\"12\"]')?.closest('button')?.click()",
                    
                    # Avoid buttons with text - eye button typically has no text
                    "Array.from(document.querySelectorAll('button.bg-brand-amber-1')).filter(btn => !btn.innerText.trim()).forEach(btn => btn.click())",
                    
                    # Explicitly avoid buttons containing "Create"
                    "Array.from(document.querySelectorAll('button')).filter(btn => btn.querySelector('svg') && !btn.innerText.includes('Create')).forEach(btn => btn.click())"
                ]
                
                for script in js_scripts:
                    try:
                        logger.info(f"Executing JavaScript: {script}")
                        self.driver.execute_script(script)
                        time.sleep(2)
                        
                        # Check if any element with "sk-" is visible after the click
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text
                        if "sk-" in page_text and "*" not in page_text:
                            eye_button_found = True
                            logger.info("JavaScript click appears to have succeeded - full 'sk-' key found in page")
                            break
                    except Exception as e:
                        logger.error(f"JavaScript execution error: {e}")
            
            if not eye_button_found:
                logger.warning("Could not find or click the eye button to make API key visible")
                # Take a screenshot to help debug
                screenshot_path = "api_keys_page_eye_button_failed.png"
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Saved screenshot to {screenshot_path}")
            
            # Take another screenshot after attempting to click
            self.driver.save_screenshot("after_eye_button_click.png")
            logger.info("Saved screenshot after attempting to click eye button")
            
            # Wait a moment for the API key to become visible
            time.sleep(3)
            
            # Try to find the API key in the page
            api_key_selectors = [
                "div.truncate",
                "//div[contains(@class, 'truncate')]",
                "//div[contains(text(), 'sk-')]",
                "//span[contains(text(), 'sk-')]"
            ]
            
            for selector in api_key_selectors:
                selector_type = By.CSS_SELECTOR
                if selector.startswith("//"):
                    selector_type = By.XPATH
                    
                logger.info(f"Trying to find API key with selector: {selector}")
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    logger.info(f"Found {len(elements)} potential API key elements")
                    
                    for element in elements:
                        text = element.text.strip()
                        if text and self.is_valid_full_api_key(text):
                            return text
                except Exception as e:
                    logger.error(f"Error finding API key with selector {selector}: {e}")
            
            # If we still can't find the API key, try to get the page source and search for it
            logger.info("Searching page source for API key pattern")
            page_source = self.driver.page_source
            
            # Save page source for debugging
            with open("api_key_page_source.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            logger.info("Saved page source to api_key_page_source.html")
            
            import re
            
            # Look for full API keys (no asterisks)
            logger.info("Looking for full API keys in page source")
            api_key_candidates = []
            
            # Pattern for full keys without asterisks
            sk_pattern = re.compile(r'sk-[a-zA-Z0-9]{30,60}')
            matches = sk_pattern.findall(page_source)
            
            for match in matches:
                if "*" not in match and len(match) >= 30:
                    api_key_candidates.append(match)
            
            if api_key_candidates:
                logger.info(f"Found {len(api_key_candidates)} candidate API keys")
                for i, key in enumerate(api_key_candidates):
                    logger.info(f"Candidate {i+1}: {key[:5]}*****{key[-4:]}")
                
                # Return the first valid candidate
                for key in api_key_candidates:
                    if self.is_valid_full_api_key(key):
                        return key
            
            logger.warning("Could not find a valid full API key in the page")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting API key from page: {e}")
            # Handle any alerts that might have appeared
            self.handle_alerts()
            
            # Try accessing clipboard again after handling the alert
            logger.info("Trying clipboard again after error")
            api_key = self.try_clipboard_access()
            if api_key:
                return api_key
                
            return None

    def click_button_by_multiple_methods(self, selectors, is_clipboard=False, avoid_text=None):
        """Try multiple methods to click a button until one succeeds"""
        button_found = False
        button_element = None
        
        # 1. First try finding with various selectors
        for selector in selectors:
            selector_type = By.CSS_SELECTOR
            if selector.startswith("//"):
                selector_type = By.XPATH
                
            logger.info(f"Trying button selector: {selector}")
            try:
                elements = self.driver.find_elements(selector_type, selector)
                logger.info(f"Found {len(elements)} elements with selector: {selector}")
                
                if elements:
                    # If we need to avoid certain text, filter the elements
                    valid_elements = []
                    for element in elements:
                        element_text = element.text.strip()
                        if avoid_text and avoid_text in element_text:
                            logger.info(f"Skipping button with text '{element_text}' containing '{avoid_text}'")
                            continue
                        valid_elements.append(element)
                    
                    if valid_elements:
                        button_element = valid_elements[0]
                        button_found = True
                        logger.info(f"Found valid button with selector: {selector}")
                        break
                    else:
                        logger.info(f"All elements for selector {selector} were filtered out")
            except Exception as e:
                logger.error(f"Error finding button with selector {selector}: {e}")
        
        if not button_found:
            logger.error("Could not find button with any selector")
            return False
            
        # 2. Try multiple click methods on the found element
        click_methods = [
            # Standard Selenium click
            lambda btn: btn.click(),
            
            # JavaScript click
            lambda btn: self.driver.execute_script("arguments[0].click();", btn),
            
            # Action chains click
            lambda btn: webdriver.ActionChains(self.driver).move_to_element(btn).click().perform(),
            
            # Click with coordinates
            lambda btn: webdriver.ActionChains(self.driver).move_to_element_with_offset(btn, 5, 5).click().perform(),
            
            # Focus and click
            lambda btn: (self.driver.execute_script("arguments[0].focus();", btn), 
                         time.sleep(0.5), 
                         btn.click())
        ]
        
        # If it's a clipboard button, add specific methods for clipboard actions
        if is_clipboard:
            # For clipboard, also try sendKeys(Ctrl+C)
            click_methods.append(
                lambda btn: webdriver.ActionChains(self.driver)
                    .move_to_element(btn)
                    .click()
                    .key_down(Keys.CONTROL)
                    .send_keys('c')
                    .key_up(Keys.CONTROL)
                    .perform()
            )
        
        # Try each click method
        for i, click_method in enumerate(click_methods):
            try:
                logger.info(f"Trying click method {i+1}")
                click_method(button_element)
                time.sleep(1)  # Wait a bit after each click attempt
                
                if is_clipboard:
                    # For clipboard buttons, verify if something was copied
                    try:
                        clipboard_content = pyperclip.paste()
                        if clipboard_content and clipboard_content.startswith("sk-"):
                            logger.info("Clipboard contains API key, click successful")
                            return True
                        else:
                            logger.info(f"Clipboard doesn't contain API key: '{clipboard_content}'")
                    except Exception as clipboard_error:
                        logger.error(f"Error checking clipboard: {clipboard_error}")
                else:
                    # For other buttons, assume click worked
                    return True
                    
            except Exception as e:
                logger.error(f"Click method {i+1} failed: {e}")
        
        # If we get here, all click methods failed
        logger.error("All click methods failed")
        return False

    def generate_api_key(self):
        """Generate a Stability API key"""
        logger.info("Starting API key generation process")
        # Create temporary email account
        account = self.temp_mail.create_account()
        if not account:
            logger.error("Failed to create temporary email account")
            return False
            
        logger.info(f"Using email: {account['email']}")
        
        # Navigate to Stability AI platform
        self.navigate_to_stability_platform()
        
        # Click on Login
        logger.info("Clicking on Login button")
        if not self.click_element_safely("a.cursor-pointer.select-none.text-sm.font-semibold.hover\\:text-indigo-500", sleep_after=3):
            # Try alternative selector or XPath
            logger.info("Trying alternative login button selector")
            if not self.click_element_safely("//a[contains(text(), 'Login')]", selector_type=By.XPATH, sleep_after=3):
                logger.error("Failed to click login button")
                return False
        
        # Wait for page to load
        logger.info("Waiting for login page to load (15s)")
        time.sleep(15)
        
        # Click on Sign up
        logger.info("Clicking on Sign up link")
        if not self.click_element_safely("a[href*='/u/signup']", sleep_after=3):
            # Try alternative selector or XPath
            logger.info("Trying alternative signup link selector")
            if not self.click_element_safely("//a[contains(text(), 'Sign up')]", selector_type=By.XPATH, sleep_after=3):
                logger.error("Failed to click signup link")
                return False
        
        # Wait for sign up page to load
        logger.info("Waiting for signup page to load (15s)")
        time.sleep(15)
        
        # Fill in email and password
        if not self.fill_input_safely("input#email", account['email'], sleep_after=1):
            logger.error("Failed to fill email field")
            return False
            
        if not self.fill_input_safely("input#password", "Study@123", sleep_after=1):
            logger.error("Failed to fill password field")
            return False
        
        # Click Continue
        logger.info("Clicking Continue button")
        if not self.click_element_safely("button[type='submit'][name='action']", sleep_after=5):
            # Try alternative selector
            logger.info("Trying alternative continue button selector")
            if not self.click_element_safely("//button[contains(text(), 'Continue')]", selector_type=By.XPATH, sleep_after=5):
                logger.error("Failed to click continue button")
                return False
        
        # Wait for verification email
        logger.info("Waiting for verification email...")
        max_wait_time = 300  # 5 minutes
        start_time = time.time()
        verification_link = None
        
        while time.time() - start_time < max_wait_time:
            messages = self.temp_mail.get_messages(account)
            logger.info(f"Checking for messages... Found {len(messages)} messages")
            
            for message in messages:
                sender = message.get('from', {}).get('address', '')
                logger.info(f"Found message from: {sender}")
                
                if "platform@stability.ai" in sender:
                    logger.info("Found message from Stability AI")
                    message_details = self.temp_mail.get_message_details(account, message['id'])
                    
                    if message_details:
                        logger.info(f"Message subject: {message_details.get('subject', 'No subject')}")
                        
                        # Try to extract from HTML content
                        if 'html' in message_details:
                            html_content = message_details['html']
                            logger.info(f"HTML content type: {type(html_content)}")
                            logger.info("Parsing email HTML content for verification link")
                            verification_link = self.extract_verification_link(html_content)
                        
                        # If HTML parsing failed, try text content
                        if not verification_link and 'text' in message_details:
                            logger.info("Trying to find verification link in text content")
                            text_content = message_details['text']
                            
                            # Save text content for debugging
                            with open("email_content.txt", "w", encoding="utf-8") as f:
                                f.write(text_content)
                            logger.info("Saved email text content to email_content.txt")
                            
                            import re
                            urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*(?:\?[-\w=&]+)*', text_content)
                            for url in urls:
                                logger.info(f"Found URL in text: {url}")
                                if "verify" in url or "confirm" in url or "auth0" in url:
                                    verification_link = url
                                    logger.info(f"Found verification link in text: {verification_link}")
                                    break
                        
                        if verification_link:
                            break
            
            if verification_link:
                break
                
            logger.info("No verification email yet, checking again in 10 seconds...")
            time.sleep(10)
        
        if not verification_link:
            logger.error("Failed to receive verification email within the timeout period")
            return False
            
        # Navigate to verification link
        logger.info(f"Navigating to verification link: {verification_link}")
        self.driver.get(verification_link)
        
        # Wait for page to load
        logger.info("Waiting for verification page to load (30s)")
        time.sleep(30)
        
        # Click Accept button
        logger.info("Clicking Accept button")
        if not self.click_element_safely("button[type='submit'][name='action'][value='accept']", sleep_after=5):
            # Try alternative selector
            logger.info("Trying alternative accept button selector")
            if not self.click_element_safely("//button[contains(text(), 'Accept')]", selector_type=By.XPATH, sleep_after=5):
                logger.error("Failed to click accept button")
                return False
        
        # Wait for redirection
        logger.info("Waiting for redirection after acceptance (30s)")
        time.sleep(30)
        
        # Navigate to API keys page
        logger.info("Navigating to API keys page")
        self.driver.get("https://platform.stability.ai/account/keys")
        
        # Wait for page to load
        logger.info("Waiting for API keys page to load (15s)")
        time.sleep(15)
        
        # Take a screenshot of the API keys page for debugging
        screenshot_path = "api_keys_page.png"
        self.driver.save_screenshot(screenshot_path)
        logger.info(f"Saved screenshot of API keys page to {screenshot_path}")
        
        # First try clicking the copy button
        logger.info("Trying to copy API key to clipboard")
        
        # Log all buttons for debugging
        try:
            all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"Found {len(all_buttons)} buttons on the page")
            for i, button in enumerate(all_buttons):
                text = button.text.strip() if button.text else "No text"
                classes = button.get_attribute("class") or "No class"
                has_svg = "Yes" if button.find_elements(By.TAG_NAME, "svg") else "No"
                logger.info(f"Button {i+1}: Text='{text}', Class='{classes}', Has SVG={has_svg}")
        except Exception as e:
            logger.error(f"Error listing buttons: {e}")
        
        # Define the exact XPaths and selectors for each button type
        create_button_xpath = "/html/body/div[1]/div/div[2]/div/div[2]/div/button"
        clipboard_button_xpath = "/html/body/div[1]/div/div[2]/div/div[2]/div/div/div[2]/div[1]/div[2]/div[3]/div/button"
        eye_button_xpath = "/html/body/div[1]/div/div[2]/div/div[2]/div/div/div[2]/div[1]/div[2]/div[3]/button"
        
        logger.info("Using provided exact XPaths for buttons")
        
        # Try directly clicking the clipboard button using exact XPath
        logger.info("Trying to click clipboard button with exact XPath")
        try:
            clipboard_element = self.driver.find_element(By.XPATH, clipboard_button_xpath)
            logger.info("Found clipboard button with exact XPath")
            
            # Check that it's not the create button (should not have text)
            button_text = clipboard_element.text.strip()
            if button_text and "Create" in button_text:
                logger.warning(f"Button appears to be Create button, not clicking: '{button_text}'")
            else:
                logger.info("Attempting to click clipboard button")
                # Try multiple ways to click
                self.driver.execute_script("arguments[0].scrollIntoView(true);", clipboard_element)
                time.sleep(1)
                
                # Try JavaScript click first
                self.driver.execute_script("arguments[0].click();", clipboard_element)
                logger.info("Clicked clipboard button with JavaScript")
                time.sleep(2)
                
                # Handle any alerts
                self.handle_alerts()
                
                # Check clipboard
                api_key = self.try_clipboard_access()
                if api_key:
                    self.api_key = api_key
                    logger.info(f"Successfully got API key from clipboard: {self.api_key[:5]}*****{self.api_key[-4:]}")
                    self.save_api_key_to_file()
                    return True
        except Exception as e:
            logger.error(f"Error clicking clipboard button with exact XPath: {e}")
        
        # Try multiple selectors for the copy button - VERY PRECISE BASED ON PROVIDED HTML
        copy_button_selectors = [
            # Exact XPath provided
            clipboard_button_xpath,
            
            # Very specific CSS based on provided HTML
            "button:has(svg:has(rect[width='14'][height='14']))",
            "button:has(svg:has(path[d^='M4 16c-1.1']))",
            
            # Avoid the Create API Key button which has lines in SVG
            "button.bg-brand-amber-1:not(:has(svg:has(line)))",
            
            # Avoid buttons with text (Create API Key has text)
            "button.bg-brand-amber-1:not(:has(span:contains('Create')))",
            
            # Specifically target the rect in the clipboard icon
            "button svg rect[width='14'][height='14']",
            
            # XPath that targets clipboard icon specifically
            "//button[.//svg[.//rect[@width='14' and @height='14']]]",
            "//button[not(contains(., 'Create'))][.//svg[.//rect]]"
        ]
        
        # Now try clicking the eye button if needed
        eye_button_selectors = [
            # Exact XPath provided
            eye_button_xpath,
            
            # Very specific CSS based on provided HTML
            "button:has(svg:has(path[d^='M2 12s3-7']))",
            "button:has(svg:has(circle[cx='12'][cy='12']))",
            
            # Avoid the Create API Key button
            "button.bg-brand-amber-1:not(:has(span:contains('Create')))",
            
            # Specifically target the circle in the eye icon
            "button svg circle[cx='12'][cy='12']",
            
            # XPath that targets eye icon specifically
            "//button[.//svg[.//circle[@cx='12' and @cy='12']]]",
            "//button[not(contains(., 'Create'))][.//svg[.//path[contains(@d, 'M2 12s3-7')]]]"
        ]
        
        # Try clicking the clipboard button with multiple methods, explicitly avoiding Create button
        clipboard_clicked = self.click_button_by_multiple_methods(
            copy_button_selectors, 
            is_clipboard=True,
            avoid_text="Create"  # Explicitly avoid any button with Create text
        )
        
        # Handle any alerts that might have appeared
        self.handle_alerts()
        
        if clipboard_clicked:
            logger.info("Successfully clicked the clipboard button")
            # Check clipboard again to see if the API key is there
            api_key = self.try_clipboard_access()
            if api_key:
                self.api_key = api_key
                logger.info(f"Successfully got API key from clipboard: {self.api_key[:5]}*****{self.api_key[-4:]}")
                self.save_api_key_to_file()
                return True
        else:
            logger.warning("Failed to click the clipboard button, trying eye button")
            
            # Try clicking the eye button
            logger.info("Trying to click eye button to make API key visible")
            eye_clicked = self.click_button_by_multiple_methods(
                eye_button_selectors,
                avoid_text="Create"
            )
            
            if eye_clicked:
                logger.info("Successfully clicked the eye button")
                # Wait for API key to become visible
                time.sleep(2)
                
                # Try to read the API key directly from the page
                try:
                    logger.info("Trying to read visible API key")
                    elements = self.driver.find_elements(By.CSS_SELECTOR, "div.truncate")
                    for element in elements:
                        text = element.text.strip()
                        if text and text.startswith("sk-") and "*" not in text:
                            logger.info(f"Found visible API key: {text[:5]}*****{text[-4:]}")
                            self.api_key = text
                            print(f"\n==== STABILITY API KEY ====\n{self.api_key}\n===========================\n")
                            self.save_api_key_to_file()
                            return True
                except Exception as e:
                    logger.error(f"Error reading visible API key: {e}")
            
            # If all the above fails, try our direct JavaScript targeting
            logger.warning("Trying direct JavaScript method")
            
            try:
                logger.info("Using direct JavaScript to locate and click the buttons")
                js_script = """
                    // Find all buttons
                    const allButtons = document.querySelectorAll('button');
                    let clipboardButton = null;
                    let eyeButton = null;
                    
                    // Identify each button type
                    for (const btn of allButtons) {
                        // Skip any button with "Create" text
                        if (btn.innerText.includes('Create')) continue;
                        
                        // Check for SVG elements
                        const svgs = btn.querySelectorAll('svg');
                        if (svgs.length === 0) continue;
                        
                        // Check for clipboard icon (rect element)
                        if (btn.querySelector('svg rect[width="14"][height="14"]')) {
                            clipboardButton = btn;
                            continue;
                        }
                        
                        // Check for eye icon (circle element)
                        if (btn.querySelector('svg circle[cx="12"][cy="12"]')) {
                            eyeButton = btn;
                            continue;
                        }
                    }
                    
                    // Try clipboard button first
                    if (clipboardButton) {
                        clipboardButton.click();
                        return "Clicked clipboard button";
                    }
                    
                    // Then try eye button
                    if (eyeButton) {
                        eyeButton.click();
                        return "Clicked eye button";
                    }
                    
                    return "No suitable buttons found";
                """
                result = self.driver.execute_script(js_script)
                logger.info(f"JavaScript result: {result}")
                time.sleep(2)
                
                # Handle any alerts
                self.handle_alerts()
                
                # Try clipboard again
                api_key = self.try_clipboard_access()
                if api_key:
                    self.api_key = api_key
                    logger.info(f"Successfully got API key after JavaScript: {self.api_key[:5]}*****{self.api_key[-4:]}")
                    self.save_api_key_to_file()
                    return True
                    
                # If clipboard failed but we clicked the eye button, try to read visible API key
                if "eye button" in result:
                    logger.info("Trying to read visible API key after JavaScript eye button click")
                    elements = self.driver.find_elements(By.CSS_SELECTOR, "div.truncate")
                    for element in elements:
                        text = element.text.strip()
                        if text and text.startswith("sk-") and "*" not in text:
                            logger.info(f"Found visible API key: {text[:5]}*****{text[-4:]}")
                            self.api_key = text
                            print(f"\n==== STABILITY API KEY ====\n{self.api_key}\n===========================\n")
                            self.save_api_key_to_file()
                            return True
            except Exception as e:
                logger.error(f"Error with JavaScript button approach: {e}")
        
        # Extract API key using various methods
        self.api_key = self.extract_api_key()
        
        if self.api_key and self.is_valid_full_api_key(self.api_key):
            logger.info(f"Successfully extracted valid API key: {self.api_key[:5]}*****{self.api_key[-4:]}")
            # Print the key in the console
            print(f"\n==== STABILITY API KEY ====\n{self.api_key}\n===========================\n")
            self.save_api_key_to_file()
            return True
        else:
            # One final attempt - try to manually trigger Ctrl+C then Enter
            logger.info("Final attempt - manually trigger Ctrl+C, Enter sequence")
            try:
                # Find the API key element
                api_key_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.truncate")
                if api_key_elements:
                    api_key_element = api_key_elements[0]
                    
                    # Click to select it
                    api_key_element.click()
                    time.sleep(1)
                    
                    # Try Ctrl+C, Enter
                    webdriver.ActionChains(self.driver)\
                        .key_down(Keys.CONTROL)\
                        .send_keys('c')\
                        .key_up(Keys.CONTROL)\
                        .send_keys(Keys.ENTER)\
                        .perform()
                    time.sleep(1)
                    
                    # Handle any alerts
                    self.handle_alerts()
                    
                    # Check clipboard
                    self.api_key = pyperclip.paste()
                    if self.api_key and self.is_valid_full_api_key(self.api_key):
                        logger.info(f"Successfully got API key in final attempt: {self.api_key[:5]}*****{self.api_key[-4:]}")
                        print(f"\n==== STABILITY API KEY ====\n{self.api_key}\n===========================\n")
                        self.save_api_key_to_file()
                        return True
            except Exception as e:
                logger.error(f"Error in final attempt: {e}")
            
            logger.error("Failed to extract a valid full API key")
            return False
        
    def save_api_key_to_file(self):
        """Save the API key to a txt file and database"""
        if not self.api_key:
            logger.error("No API key to save")
            return False
            
        # Save to txt file for legacy support
        file_path = "stability_api_key.txt"
        try:
            with open(file_path, "w") as f:
                f.write(self.api_key)
            logger.info(f"API key saved to {os.path.abspath(file_path)}")
        except Exception as e:
            logger.error(f"Failed to save API key to file: {e}")
        
        # Save to database
        try:
            # Create a new StabilityApiKey object
            stability_api_key = StabilityApiKey(
                api_key=self.api_key,
                created_at=datetime.datetime.now(),
                is_active=True
            )
            
            # Save to database
            stability_api_key.save()
            logger.info("API key saved to database")
            
            # Count keys in database
            from models import db
            key_count = db['stability_api_keys'].count_documents({'is_active': True})
            logger.info(f"Total active API keys in database: {key_count}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to save API key to database: {e}")
            return False
        
    def close(self):
        """Close the browser"""
        logger.info("Closing browser")
        if hasattr(self, 'driver'):
            self.driver.quit()
            logger.info("Browser closed")
            
if __name__ == "__main__":
    logger.info("Starting Stability API Generator")
    generator = None
    max_retries = 3
    current_retry = 0
    success = False  # Initialize success variable
    
    # Check if running in GitHub Actions
    is_ci = os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')
    if is_ci:
        logger.info("Running in CI environment - using increased retries")
        max_retries = 5  # More retries in CI environment
    
    while current_retry < max_retries:
        try:
            current_retry += 1
            logger.info(f"Attempt {current_retry} of {max_retries}")
            
            generator = StabilityApiGenerator()
            success = generator.generate_api_key()

            if success:
                    logger.info(f"Successfully generated Stability API key: {generator.api_key[:5]}*****{generator.api_key[-4:]}")
                    break  # Exit the retry loop on success
            else:
                    logger.error(f"Failed to generate Stability API key (Attempt {current_retry}/{max_retries})")
                    if current_retry < max_retries:
                        wait_time = current_retry * 60  # Progressively longer waits
                        logger.info(f"Waiting {wait_time} seconds before retrying...")
                        time.sleep(wait_time)
        except Exception as e:
            logger.critical(f"An error occurred: {e}", exc_info=True)
            
            # Detailed error logging especially useful in CI
            logger.critical("Exception traceback:")
            traceback.print_exc()
            
            if current_retry < max_retries:
                wait_time = current_retry * 60
                logger.info(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
        finally:
            if generator:
                generator.close()
                generator = None  # Reset for next attempt
    
    if current_retry >= max_retries and not success:
        logger.critical(f"Failed to generate API key after {max_retries} attempts")
        sys.exit(1)  # Exit with error code for CI to detect failure
