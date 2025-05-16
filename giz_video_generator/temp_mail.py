import requests
import time
import logging
import json

# Configure logging if not already configured
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("temp_mail.log"),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

class TempMail:
    def __init__(self):
        self.base_url = "https://api.mail.tm"
        logger.info("TempMail initialized with base URL: %s", self.base_url)

    def create_account(self):
        try:
            logger.info("Fetching available domains...")
            domain_response = requests.get(f"{self.base_url}/domains")
            
            if domain_response.status_code != 200:
                logger.error(f"Error fetching domains: {domain_response.status_code} - {domain_response.text}")
                return None
                
            domains = domain_response.json().get('hydra:member', [])
            if not domains:
                logger.error("No domains available")
                return None
                
            domain = domains[0]['domain']
            logger.info(f"Using domain: {domain}")
            
            import random
            random_number = random.randint(1000, 9999)
            email = f"temp{int(time.time())}{random_number}@{domain}"
            password = "password123"
            
            data = {"address": email, "password": password}
            logger.info(f"Creating account with email: {email}")
            response = requests.post(f"{self.base_url}/accounts", json=data)
            
            if response.status_code == 201:
                logger.info(f"Temporary Email Created: {email}")
                token = self.login(email, password)
                return {"email": email, "password": password, "token": token}
            else:
                logger.error(f"Error creating email account: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception in create_account: {e}")
            return None

    def login(self, email, password):
        try:
            logger.info(f"Logging in with email: {email}")
            response = requests.post(f"{self.base_url}/token", json={"address": email, "password": password})
            
            if response.status_code == 200:
                token = response.json().get("token")
                logger.info("Login successful, token received")
                return token
            else:
                logger.error(f"Error logging in: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception in login: {e}")
            return None

    def get_messages(self, account):
        try:
            if not account or not account.get('token'):
                logger.error("Invalid account or missing token")
                return []
                
            headers = {"Authorization": f"Bearer {account['token']}"}
            logger.info("Fetching messages...")
            response = requests.get(f"{self.base_url}/messages", headers=headers)
            
            if response.status_code == 200:
                messages = response.json().get("hydra:member", [])
                logger.info(f"Retrieved {len(messages)} messages")
                return messages
            else:
                logger.error(f"Error fetching messages: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Exception in get_messages: {e}")
            return []

    def get_message_details(self, account, message_id):
        try:
            if not account or not account.get('token'):
                logger.error("Invalid account or missing token")
                return None
                
            headers = {"Authorization": f"Bearer {account['token']}"}
            logger.info(f"Fetching details for message ID: {message_id}")
            response = requests.get(f"{self.base_url}/messages/{message_id}", headers=headers)
            
            if response.status_code == 200:
                message_details = response.json()
                logger.info(f"Retrieved message details: Subject '{message_details.get('subject')}'")
                
                # Check HTML content format
                html_content = message_details.get('html')
                if html_content:
                    logger.info(f"HTML content type: {type(html_content)}")
                    if isinstance(html_content, list):
                        logger.info(f"HTML content is a list with {len(html_content)} elements")
                    elif isinstance(html_content, str):
                        logger.info(f"HTML content is a string of length {len(html_content)}")
                else:
                    logger.info("No HTML content in message")
                
                # Save complete message details for debugging
                # try:
                #     with open(f"message_{message_id}.json", "w", encoding="utf-8") as f:
                #         json.dump(message_details, f, indent=2)
                #     logger.info(f"Saved complete message details to message_{message_id}.json")
                # except Exception as e:
                #     logger.error(f"Error saving message details to file: {e}")
                
                return message_details
            else:
                logger.error(f"Error fetching message details: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception in get_message_details: {e}")
            return None

    def wait_for_messages(self, account, timeout=180, check_interval=10):
        """Wait for incoming emails for a specified timeout period"""
        logger.info("Waiting for emails...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            messages = self.get_messages(account)
            if messages:
                logger.info(f"Received {len(messages)} messages")
                return messages
            logger.info(f"No messages yet, checking again in {check_interval} seconds...")
            time.sleep(check_interval)
        
        logger.warning("No messages received within the timeout period.")
        return []
