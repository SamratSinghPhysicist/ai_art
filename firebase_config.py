import os
import json
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth
import pyrebase

# Load environment variables
load_dotenv()

# Path to service account JSON file (for direct file upload in deployment)
SERVICE_ACCOUNT_PATH = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', './firebase-service-account.json')

# Initialize Firebase Admin SDK
def initialize_firebase_admin():
    """Initialize Firebase Admin SDK with service account credentials"""
    try:
        # First, try to use the service account JSON file if it exists
        if os.path.exists(SERVICE_ACCOUNT_PATH):
            print(f"Loading Firebase Admin SDK credentials from: {SERVICE_ACCOUNT_PATH}")
            return credentials.Certificate(SERVICE_ACCOUNT_PATH)
        
        # If file doesn't exist, try to use environment variables
        print("Loading Firebase Admin SDK credentials from environment variables")
        return credentials.Certificate({
            "type": os.getenv("FIREBASE_TYPE", "service_account"),
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
        })
    except ValueError as e:
        print(f"Error initializing Firebase Admin SDK: {e}")
        # Fallback option for development without credentials
        if os.getenv("FLASK_ENV") == "development":
            print("DEVELOPMENT MODE: Using application default credentials")
            return credentials.ApplicationDefault()
        raise

# Initialize the Admin SDK
cred = initialize_firebase_admin()
firebase_admin.initialize_app(cred)

# Load Firebase configuration for client-side
def get_firebase_config():
    """Get Firebase configuration for client-side"""
    config = {}
    
    # First check if a config file exists
    config_path = os.getenv('FIREBASE_CONFIG_PATH', './firebase-config.json')
    if os.path.exists(config_path):
        print(f"Loading Firebase client config from: {config_path}")
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        # Otherwise use environment variables
        print("Loading Firebase client config from environment variables")
        config = {
            "apiKey": os.getenv("FIREBASE_API_KEY"),
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
            "projectId": os.getenv("FIREBASE_PROJECT_ID"),
            "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
            "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
            "appId": os.getenv("FIREBASE_APP_ID")
        }
    
    # Ensure databaseURL is present
    if "databaseURL" not in config or not config["databaseURL"]:
        config["databaseURL"] = os.getenv("FIREBASE_DATABASE_URL", "https://placeholder-default-rtdb.firebaseio.com")
        print(f"Using databaseURL: {config['databaseURL']}")
    
    print("Firebase client config keys:", list(config.keys()))
    return config

# Get Firebase configuration
firebase_config = get_firebase_config()

# Create a minimal configuration for Pyrebase in development if config is incomplete
if not firebase_config.get("apiKey") and os.getenv("FLASK_ENV") == "development":
    print("WARNING: Using placeholder Firebase config for development")
    firebase_config = {
        "apiKey": "placeholder-api-key",
        "authDomain": "placeholder.firebaseapp.com",
        "databaseURL": "https://placeholder-default-rtdb.firebaseio.com",
        "projectId": "placeholder",
        "storageBucket": "placeholder.appspot.com",
        "messagingSenderId": "000000000000",
        "appId": "1:000000000000:web:0000000000000000000000"
    }

# Initialize Pyrebase with the config
print("Initializing Pyrebase with config keys:", list(firebase_config.keys()))
firebase = pyrebase.initialize_app(firebase_config)
firebase_auth = firebase.auth() 