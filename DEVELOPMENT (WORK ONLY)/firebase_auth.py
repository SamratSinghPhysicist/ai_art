import firebase_admin
from firebase_admin import credentials, auth
import pyrebase
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK for server-side operations
cred = None
firebase = None
pb = None

def initialize_firebase():
    """Initialize Firebase with credentials from environment variables"""
    global cred, firebase, pb
    
    # Check if Firebase is already initialized
    if firebase:
        return
    
    # Get Firebase configuration from environment variables
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL", ""),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.getenv("FIREBASE_APP_ID")
    }
    
    # Initialize Firebase Admin SDK with service account
    try:
        # Check for credential file path in environment
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
        
        if service_account_path and os.path.exists(service_account_path):
            # Initialize with file
            cred = credentials.Certificate(service_account_path)
        else:
            # Try to initialize with JSON content from environment
            service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            if service_account_json:
                try:
                    service_account_dict = json.loads(service_account_json)
                    cred = credentials.Certificate(service_account_dict)
                except json.JSONDecodeError:
                    raise ValueError("Invalid FIREBASE_SERVICE_ACCOUNT_JSON format")
            else:
                raise ValueError("No Firebase credentials found")
        
        # Initialize Firebase Admin SDK
        firebase = firebase_admin.initialize_app(cred)
        
        # Initialize Pyrebase for client operations
        pb = pyrebase.initialize_app(firebase_config)
        
        print("Firebase initialized successfully")
        
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        # Continue without Firebase if initialization fails
        pass

def sign_up(email, password, display_name=None):
    """Create a new user with Firebase Authentication"""
    try:
        # Create user with Firebase Admin SDK
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name or "",
            email_verified=False
        )
        
        # Return user info
        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "display_name": user.display_name
        }
    except auth.EmailAlreadyExistsError:
        return {"success": False, "error": "Email already exists"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sign_in(email, password):
    """Sign in a user with email and password"""
    try:
        # Sign in with Pyrebase
        user = pb.auth().sign_in_with_email_and_password(email, password)
        
        # Get user details from Firebase
        user_info = auth.get_user_by_email(email)
        
        # Return user info and token
        return {
            "success": True,
            "uid": user_info.uid,
            "email": user_info.email,
            "display_name": user_info.display_name,
            "id_token": user["idToken"],
            "refresh_token": user["refreshToken"]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_user_by_email(email):
    """Get user information by email"""
    try:
        user = auth.get_user_by_email(email)
        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "display_name": user.display_name
        }
    except auth.UserNotFoundError:
        return {"success": False, "error": "User not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_user_by_id(uid):
    """Get user information by UID"""
    try:
        user = auth.get_user(uid)
        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "display_name": user.display_name
        }
    except auth.UserNotFoundError:
        return {"success": False, "error": "User not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def update_user(uid, display_name=None, email=None, password=None):
    """Update user information"""
    try:
        # Prepare update parameters
        params = {}
        if display_name is not None:
            params["display_name"] = display_name
        if email is not None:
            params["email"] = email
        if password is not None:
            params["password"] = password
        
        # Update user
        user = auth.update_user(uid, **params)
        
        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "display_name": user.display_name
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def verify_id_token(id_token):
    """Verify Firebase ID token and get user information"""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return {
            "success": True,
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email", ""),
            "email_verified": decoded_token.get("email_verified", False)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Initialize Firebase when the module is imported
initialize_firebase() 