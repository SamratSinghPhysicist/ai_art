import time
import re
import os
import sys # Added import
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from temp_mail import TempMail

try:
    # Adjust Python path to import 'models' from the parent directory
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(SCRIPT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)

    from models import save_giz_account
except:
    print("Failed to import save_giz_account from models.")

class GizAccountGenerator:
    def __init__(self):
        self.driver = None
        self.wait = None

    def setup_driver(self):
        """Set up the Selenium WebDriver"""
        print("Setting up Chrome WebDriver")
        chrome_options = Options()

        # Check if running in GitHub Actions or CI environment
        is_ci = os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')
        if is_ci:
            print("Running in CI environment - using headless mode with enhanced options")
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
        print(f"Chrome options: {chrome_options.arguments}")

        try:
            # Use webdriver-manager for automatic ChromeDriver management
            print("Using webdriver-manager for ChromeDriver management")
            # ChromeType is no longer available in webdriver-manager 4.0.1+

            try:
                # Check Chrome version to use specific driver version if needed
                import subprocess
                try:
                    chrome_version_output = subprocess.check_output(["google-chrome", "--version"]).decode("utf-8").strip()
                    print(f"Detected Chrome version: {chrome_version_output}")
                    chrome_major_version = chrome_version_output.split()[-1].split('.')[0]
                    print(f"Chrome major version: {chrome_major_version}")

                    # Use specific driver version for Chrome 135
                    if chrome_major_version == "135":
                        print("Using known compatible ChromeDriver version for Chrome 135")
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
                    print(f"Failed to detect Chrome version: {e}")
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=chrome_options
                    )

                print("ChromeDriver initialized successfully with webdriver-manager")
            except Exception as e:
                print(f"Error initializing ChromeDriver with webdriver-manager: {e}")

                # Fallback to alternative methods
                try:
                    # Try using system ChromeDriver if available
                    print("Trying system ChromeDriver")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    print("ChromeDriver initialized using system executable")
                except Exception as e2:
                    print(f"Failed to initialize ChromeDriver: {e2}")
                    raise Exception("Could not initialize ChromeDriver by any method") from e

            # Set up wait times
            self.wait = WebDriverWait(self.driver, 60)
            print("WebDriver initialization complete")

        except Exception as e:
            print(f"WebDriver setup failed: {e}")
            raise

    def create_giz_account(self):
        # Initialize TempMail
        temp_mail = TempMail()
        account = temp_mail.create_account()

        if not account:
            print("Failed to create temporary email account.")
            return

        email = account['email']
        print(f"Created temporary email: {email}")

        # Initialize Selenium WebDriver
        #service = Service(executable_path="chromedriver")  # Replace with the actual path to chromedriver if needed
        #driver = webdriver.Chrome(service=service)

        # Use the setup_driver method
        self.setup_driver()
        driver = self.driver

        try:
            # Navigate to the signup page
            driver.get("https://app.giz.ai/signUp")

            # Enter the email
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Email"]'))
            )
            email_input.send_keys(email)

            # Wait for 3 seconds
            time.sleep(3)

            # Click the "Send code" button
            send_code_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@title="Send code"]'))
            )
            send_code_button.click()

            # Wait for the verification code (5-60 seconds)
            print("Waiting for verification code...")
            messages = temp_mail.wait_for_messages(account, timeout=60)

            if not messages:
                print("Failed to receive verification code.")
                return

            latest_message = messages[0]
            message_details = temp_mail.get_message_details(account, latest_message['id'])

            if not message_details:
                print("Failed to retrieve message details.")
                return

            html_content = message_details.get('html')
            if isinstance(html_content, list):
                html_content = html_content[0]  # Use the first element if it's a list

            verification_code_match = re.search(r"Verification Code: (\w+)", html_content)
            if verification_code_match:
                verification_code = verification_code_match.group(1)
                print(f"Verification code found: {verification_code}")
            else:
                print("Verification code not found in email.")
                return

            # Enter the verification code
            verification_code_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Email verification code"]'))
            )
            verification_code_input.send_keys(verification_code)

            # Enter the password and confirm password
            password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Password"]'))
            )
            password_input.send_keys("Ai@Art_123")
            confirm_password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Confirm password"]'))
            )
            confirm_password_input.send_keys("Ai@Art_123")

            # Wait for 2 seconds
            time.sleep(2)

            # Enter the full name
            full_name_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Full name"]'))
            )
            full_name_input.send_keys("Ai Art")

            # Wait for 2 seconds
            time.sleep(2)

            # Click the "Sign up" button
            sign_up_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[text()="Sign up"]'))
            )
            sign_up_button.click()

            # Wait for 3 seconds
            time.sleep(3)

            print("Account creation completed successfully.")

            # Save account details to MongoDB
            try:
                save_giz_account(email, "Ai@Art_123")
                print(f"Account details saved to MongoDB for email: {email}")
            except Exception as db_error:
                print(f"Error saving account details to MongoDB: {db_error}")

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            # Close the browser
            if driver:
                driver.quit()

if __name__ == "__main__":
    generator = GizAccountGenerator()
    generator.create_giz_account()
