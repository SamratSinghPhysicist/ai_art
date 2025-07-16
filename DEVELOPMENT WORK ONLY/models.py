import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# It's recommended to store your MongoDB URI in a .env file
# for security and ease of configuration.
# Example .env file:
# MONGO_URI="mongodb://localhost:27017/"
# DB_NAME="ai_art_db"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_art_db")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # The ismaster command is cheap and does not require auth.
    client.admin.command('ismaster')
    print("MongoDB connection successful.")
    db = client[DB_NAME]
    blocked_ips_collection = db["blocked_ips"]
    request_logs_collection = db["request_logs"]
    custom_rate_limits_collection = db["custom_rate_limits"]
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    db = None
    blocked_ips_collection = None
    request_logs_collection = None
    custom_rate_limits_collection = None
import bcrypt
import os
import datetime
from dotenv import load_dotenv
from bson.objectid import ObjectId
import requests
from firebase_admin import auth as firebase_admin_auth

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['ai_image_generator']
users_collection = db['users']

# Handle MongoDB indexes properly
try:
    # First, try to drop the existing unique index on email if it exists
    indexes = users_collection.index_information()
    if 'email_1' in indexes:
        if indexes['email_1'].get('unique', False):
            print("Dropping existing unique email index")
            users_collection.drop_index('email_1')
    
    # Create firebase_uid index with unique and sparse constraints
    users_collection.create_index('firebase_uid', unique=True, sparse=True, name='firebase_uid_1')
    
    # Create non-unique email index with a different name
    users_collection.create_index('email', unique=False, name='email_non_unique')
    
    print("MongoDB indexes set up successfully")
except Exception as e:
    print(f"Warning: Could not set up MongoDB indexes: {e}")
    print("The application will continue, but some database operations might not work as expected")

class User:
    """User model for authentication and database operations"""
    
    def __init__(self, email, password=None, name=None, _id=None, plaintext_password=None, firebase_uid=None, email_verified=False):
        self.email = email
        self.password = password
        self.name = name
        self._id = _id
        self.plaintext_password = plaintext_password
        self.firebase_uid = firebase_uid
        self.email_verified = email_verified
    
    # Flask-Login integration methods
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_active(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self._id)
    
    def save(self):
        """Save user to database"""
        try:
            # Store plaintext password if provided
            if self.password and not self.password.startswith('$2b$'):
                self.plaintext_password = self.password
                self.password = bcrypt.hashpw(self.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Prepare user document
            user_data = {
                'email': self.email,
                'password': self.password,
                'plaintext_password': self.plaintext_password,
                'name': self.name,
                'firebase_uid': self.firebase_uid,
                'email_verified': self.email_verified
            }
            
            # Insert or update user
            if self._id:
                users_collection.update_one({'_id': self._id}, {'$set': user_data})
                return self._id
            else:
                # Check for existing Firebase UID first
                if self.firebase_uid:
                    existing = users_collection.find_one({'firebase_uid': self.firebase_uid})
                    if existing:
                        self._id = existing['_id']
                        users_collection.update_one({'_id': self._id}, {'$set': user_data})
                        return self._id
                
                # If no existing user found by firebase_uid or email (without firebase_uid),
                # perform an upsert based on email and firebase_uid (which might be None)
                # This handles cases where multiple users might have firebase_uid: null
                # and prevents duplicate key errors on the sparse unique index.
                filter_query = {'email': self.email}
                if self.firebase_uid is None:
                    # Explicitly filter for documents where firebase_uid is null
                    filter_query['firebase_uid'] = None
                else:
                    # Filter by the specific firebase_uid if it exists
                    filter_query['firebase_uid'] = self.firebase_uid

                result = users_collection.update_one(
                    filter_query,
                    {'$set': user_data},
                    upsert=True
                )

                if result.upserted_id:
                    self._id = result.upserted_id
                    print(f"Upserted new user with ID: {self._id}")
                elif result.matched_count > 0:
                    # Document was matched and updated
                    existing_doc = users_collection.find_one(filter_query)
                    if existing_doc:
                        self._id = existing_doc['_id']
                        print(f"Matched and updated existing user with ID: {self._id}")
                    else:
                         print("Matched existing user but could not retrieve ID after update.")
                else:
                    print("Upsert operation completed but no document was upserted or matched.")

                # Ensure _id is set if it wasn't already
                if self._id is None and self.email:
                     # Attempt to find the document by email and firebase_uid=None if _id is still not set
                     found_doc = users_collection.find_one({'email': self.email, 'firebase_uid': None})
                     if found_doc:
                         self._id = found_doc['_id']
                         print(f"Found user ID after upsert attempt: {self._id}")


                if self._id:
                    return self._id
                else:
                    # Fallback error if _id is still not set after upsert attempt
                    raise Exception("Failed to get user ID after save/upsert operation.")

        except Exception as e:
            print(f"Error saving user: {e}")
            import traceback
            traceback.print_exc() # Print traceback for better debugging
            raise
    
    @staticmethod
    def find_by_email(email):
        """Find user by email"""
        if not email:
            return None
        
        try:
            user_data = users_collection.find_one({'email': email})
            if user_data:
                return User(
                    email=user_data['email'],
                    password=user_data.get('password'),
                    plaintext_password=user_data.get('plaintext_password'),
                    name=user_data.get('name'),
                    _id=user_data['_id'],
                    firebase_uid=user_data.get('firebase_uid'),
                    email_verified=user_data.get('email_verified', False)
                )
        except Exception as e:
            print(f"Error finding user by email '{email}': {e}")
        return None
    
    @staticmethod
    def find_by_firebase_uid(firebase_uid):
        """Find user by Firebase UID"""
        if not firebase_uid:
            return None
            
        try:
            user_data = users_collection.find_one({'firebase_uid': firebase_uid})
            if user_data:
                return User(
                    email=user_data['email'],
                    password=user_data.get('password'),
                    plaintext_password=user_data.get('plaintext_password'),
                    name=user_data.get('name'),
                    _id=user_data['_id'],
                    firebase_uid=user_data.get('firebase_uid'),
                    email_verified=user_data.get('email_verified', False)
                )
        except Exception as e:
            print(f"Error finding user by firebase_uid '{firebase_uid}': {e}")
        return None

    @staticmethod
    def create_or_update_from_firebase(firebase_user):
        """Create or update user from Firebase user data"""
        try:
            print(f"Firebase user data: {firebase_user}")
            
            # Extract data from firebase_user
            email = firebase_user.get('email')
            
            # Handle different naming conventions from different sources
            name = firebase_user.get('displayName') or firebase_user.get('display_name', 'User')
            
            # Handle different UID field names
            firebase_uid = firebase_user.get('localId') or firebase_user.get('uid')
            
            # Handle different verification status field names
            email_verified = firebase_user.get('emailVerified', False)
            
            if not email:
                print("Error: No email found in Firebase user data")
                return None
                
            if not firebase_uid:
                print("Error: No Firebase UID found in Firebase user data")
                return None
            
            print(f"Processing Firebase user - Email: {email}, UID: {firebase_uid}")
            
            # First, try to find by Firebase UID (most reliable)
            existing_user = User.find_by_firebase_uid(firebase_uid)
            
            # If not found by UID, try by email
            if not existing_user and email:
                existing_user = User.find_by_email(email)
                print(f"Found existing user by email: {existing_user is not None}")
            
            if existing_user:
                # Update existing user
                print(f"Updating existing user: {existing_user.email}")
                existing_user.firebase_uid = firebase_uid
                existing_user.email = email 
                existing_user.email_verified = email_verified
                if name and name != 'User':
                    existing_user.name = name
                existing_user.save()
                return existing_user
            else:
                # Create new user
                print(f"Creating new user with email: {email}, firebase_uid: {firebase_uid}")
                new_user = User(
                    email=email,
                    name=name,
                    firebase_uid=firebase_uid,
                    email_verified=email_verified
                )
                new_user.save()
                return new_user
        except Exception as e:
            print(f"Error in create_or_update_from_firebase: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def find_by_id(user_id):
        """Find user by ID"""
        try:
            # Convert string ID to ObjectId if it's a string
            if isinstance(user_id, str):
                user_id = ObjectId(user_id)
            user_data = users_collection.find_one({'_id': user_id})
            if user_data:
                return User(
                    email=user_data['email'],
                    password=user_data.get('password'),
                    plaintext_password=user_data.get('plaintext_password'),
                    name=user_data.get('name'),
                    _id=user_data['_id'],
                    firebase_uid=user_data.get('firebase_uid'),
                    email_verified=user_data.get('email_verified', False)
                )
        except Exception as e:
            print(f"Error finding user by ID: {e}")
        return None
    
    def check_password(self, password):
        """Check if password matches"""
        if not self.password:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))


class StabilityApiKey:
    """Model for managing Stability API keys"""
    
    def __init__(self, api_key, created_at=None, is_active=True, _id=None):
        self.api_key = api_key
        self.created_at = created_at or datetime.datetime.now()
        self.is_active = is_active
        self._id = _id
    
    def save(self):
        """Save API key to database"""
        # Check if this key already exists
        existing_key = db['stability_api_keys'].find_one({'api_key': self.api_key})
        
        api_key_data = {
            'api_key': self.api_key,
            'created_at': self.created_at,
            'is_active': self.is_active
        }
        
        # Update existing key or insert new one
        if existing_key:
            self._id = existing_key['_id']
            db['stability_api_keys'].update_one({'_id': self._id}, {'$set': api_key_data})
            return self._id
        else:
            result = db['stability_api_keys'].insert_one(api_key_data)
            self._id = result.inserted_id
            return result.inserted_id
    
    @staticmethod
    def find_by_id(api_key_id):
        """Find API key by ID"""
        try:
            if isinstance(api_key_id, str):
                api_key_id = ObjectId(api_key_id)
            api_key_data = db['stability_api_keys'].find_one({'_id': api_key_id})
            if api_key_data:
                return StabilityApiKey(
                    api_key=api_key_data['api_key'],
                    created_at=api_key_data.get('created_at', datetime.datetime.now()),
                    is_active=api_key_data['is_active'],
                    _id=api_key_data['_id']
                )
        except Exception as e:
            print(f"Error finding API key by ID: {e}")
        return None
    
    @staticmethod
    def find_oldest_key():
        """Find the oldest API key available"""
        try:
            # Find active keys sorted by creation date (oldest first)
            oldest_key = db['stability_api_keys'].find({
                'is_active': True
            }).sort('created_at', 1).limit(1)
            
            # Return the first one if available
            api_key_data = next(oldest_key, None)
            if api_key_data:
                return StabilityApiKey(
                    api_key=api_key_data['api_key'],
                    created_at=api_key_data.get('created_at', datetime.datetime.now()),
                    is_active=api_key_data['is_active'],
                    _id=api_key_data['_id']
                )
        except Exception as e:
            print(f"Error finding oldest API key: {e}")
        return None
    
    @staticmethod
    def delete_key(api_key_str):
        """Delete an API key from the database after it's been used"""
        try:
            result = db['stability_api_keys'].delete_one({'api_key': api_key_str})
            if result.deleted_count > 0:
                print(f"Deleted API key: {api_key_str[:5]}...{api_key_str[-4:]}")
                return True
            else:
                print(f"API key not found: {api_key_str[:5]}...{api_key_str[-4:]}")
                return False
        except Exception as e:
            print(f"Error deleting API key: {e}")
            return False
    
    @staticmethod
    def count_keys():
        """Count the number of active API keys in the database"""
        try:
            return db['stability_api_keys'].count_documents({'is_active': True})
        except Exception as e:
            print(f"Error counting API keys: {e}")
            return 0


import uuid
from datetime import timezone

class QwenApiKey:
    """Model for managing Qwen API keys"""

    def __init__(self, auth_token, chat_id, fid, children_ids, x_request_id, status='available', _id=None):
        self.auth_token = auth_token
        self.chat_id = chat_id
        self.fid = fid
        self.children_ids = children_ids
        self.x_request_id = x_request_id
        self.status = status
        self._id = _id

    def save(self):
        """Save API key to database"""
        api_key_data = {
            'auth_token': self.auth_token,
            'chat_id': self.chat_id,
            'fid': self.fid,
            'children_ids': self.children_ids,
            'x_request_id': self.x_request_id,
            'status': self.status
        }

        if self._id:
            db['qwen_api_keys'].update_one({'_id': self._id}, {'$set': api_key_data})
            return self._id
        else:
            result = db['qwen_api_keys'].insert_one(api_key_data)
            self._id = result.inserted_id
            return result.inserted_id

    @staticmethod
    def get_all():
        """Get all API keys"""
        try:
            return list(db['qwen_api_keys'].find())
        except Exception as e:
            print(f"Error getting all Qwen API keys: {e}")
            return []

    @staticmethod
    def delete(key_id):
        """Delete an API key from the database"""
        try:
            result = db['qwen_api_keys'].delete_one({'_id': ObjectId(key_id)})
            if result.deleted_count > 0:
                print(f"Deleted Qwen API key with ID: {key_id}")
                return True
            else:
                print(f"Qwen API key not found with ID: {key_id}")
                return False
        except Exception as e:
            print(f"Error deleting Qwen API key: {e}")
            return False

    @staticmethod
    def find_available_key():
        """Atomically finds an available key and marks it as 'generating'."""
        if db is None: return None
        return db['qwen_api_keys'].find_one_and_update(
            {'status': 'available'},
            {'$set': {'status': 'generating', 'updated_at': datetime.datetime.now(timezone.utc)}},
            return_document=True
        )

    @staticmethod
    def mark_key_available(key_id):
        """Marks a key as available by its ID."""
        if db is None: return
        db['qwen_api_keys'].update_one(
            {'_id': ObjectId(key_id)},
            {'$set': {'status': 'available', 'updated_at': datetime.datetime.now(timezone.utc)}}
        )
    
    @staticmethod
    def get_key_status(key_id):
        """Gets the status of a specific key."""
        if db is None: return None
        key = db['qwen_api_keys'].find_one({'_id': ObjectId(key_id)})
        return key.get('status') if key else None

class VideoTask:
    @staticmethod
    def create(prompt):
        """Creates a new video task in the queue."""
        if db is None: return None
        
        task_id = str(uuid.uuid4())
        task_document = {
            "task_id": task_id,
            "prompt": prompt,
            "status": "pending", # pending, processing, completed, failed
            "result_url": None,
            "error_message": None,
            "assigned_key_id": None,
            "created_at": datetime.datetime.now(timezone.utc),
            "updated_at": datetime.datetime.now(timezone.utc),
        }
        db['video_tasks'].insert_one(task_document)
        return db['video_tasks'].find_one({"task_id": task_id})

    @staticmethod
    def get_by_id(task_id):
        """Retrieves a task by its task_id."""
        if db is None: return None
        return db['video_tasks'].find_one({"task_id": task_id})

    @staticmethod
    def update(task_id, status, result_url=None, assigned_key_id=None, error_message=None):
        """Updates a task's status and other fields."""
        if db is None: return
        
        update_fields = {
            "status": status,
            "updated_at": datetime.datetime.now(timezone.utc)
        }
        if result_url is not None:
            update_fields["result_url"] = result_url
        if assigned_key_id is not None:
            update_fields["assigned_key_id"] = assigned_key_id
        if error_message is not None:
            update_fields["error_message"] = error_message
            
        db['video_tasks'].update_one(
            {"task_id": task_id},
            {"$set": update_fields}
        )
