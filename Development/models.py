from pymongo import MongoClient
import bcrypt
import os
import datetime
from dotenv import load_dotenv
from bson.objectid import ObjectId
import requests

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['ai_image_generator']
users_collection = db['users']

# Ensure indexes for email uniqueness
users_collection.create_index('email', unique=True)

class User:
    """User model for authentication and database operations"""
    
    def __init__(self, email, password=None, name=None, _id=None):
        self.email = email
        self.password = password
        self.name = name
        self._id = _id
    
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
        # Hash password if it exists and is not already hashed
        if self.password and not self.password.startswith('$2b$'):
            self.password = bcrypt.hashpw(self.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Prepare user document
        user_data = {
            'email': self.email,
            'password': self.password,
            'name': self.name
        }
        
        # Insert or update user
        if self._id:
            users_collection.update_one({'_id': self._id}, {'$set': user_data})
            return self._id
        else:
            result = users_collection.insert_one(user_data)
            self._id = result.inserted_id
            return result.inserted_id
    
    @staticmethod
    def find_by_email(email):
        """Find user by email"""
        user_data = users_collection.find_one({'email': email})
        if user_data:
            return User(
                email=user_data['email'],
                password=user_data['password'],
                name=user_data.get('name'),
                _id=user_data['_id']
            )
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
                    password=user_data['password'],
                    name=user_data.get('name'),
                    _id=user_data['_id']
                )
        except Exception as e:
            print(f"Error finding user by ID: {e}")
        return None
    
    def check_password(self, password):
        """Check if password matches"""
        if not self.password:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))
    
    def get_thumbnails(self):
        """Get all images created by this user"""
        images = db['images'].find({'user_id': self._id})
        return list(images)
    
    def save_thumbnail(self, image_path, description):
        """Save image to user's collection"""
        # Read the image file and convert to base64
        import base64
        import os
        from flask import current_app
        
        # Remove the leading slash if present
        if image_path.startswith('/'):
            image_path = image_path[1:]
        
        # Determine the full path to the image file
        if 'test_assets' in image_path:
            full_path = os.path.join(os.getcwd(), image_path)
        elif 'processed_images' in image_path:
            full_path = os.path.join(os.getcwd(), image_path)
        else:  # images folder
            full_path = os.path.join(os.getcwd(), image_path)
        
        # Read the image file and encode it as base64
        try:
            with open(full_path, 'rb') as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error reading image file: {e}")
            # If there's an error, store the path instead
            image_data = None
        
        # Store both the image data and the path (for backward compatibility)
        image_data_obj = {
            'user_id': self._id,
            'image_path': image_path,  # Keep the path for backward compatibility
            'image_data': image_data,  # Store the actual image data
            'description': description,
            'created_at': datetime.datetime.now()
        }
        return db['images'].insert_one(image_data_obj).inserted_id

class StabilityApiKey:
    """Model for managing Stability API keys"""
    
    def __init__(self, api_key, usage_count=0, last_used=None, is_active=True, _id=None):
        self.api_key = api_key
        self.usage_count = usage_count  # Track usage count instead of credits
        self.last_used = last_used or datetime.datetime.now()
        self.is_active = is_active
        self._id = _id
    
    def save(self):
        """Save API key to database"""
        # Check if this key already exists
        existing_key = db['stability_api_keys'].find_one({'api_key': self.api_key})
        
        api_key_data = {
            'api_key': self.api_key,
            'usage_count': self.usage_count,
            'last_used': self.last_used,
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
                    usage_count=api_key_data.get('usage_count', 0),
                    last_used=api_key_data.get('last_used', datetime.datetime.now()),
                    is_active=api_key_data['is_active'],
                    _id=api_key_data['_id']
                )
        except Exception as e:
            print(f"Error finding API key by ID: {e}")
        return None
    
    @staticmethod
    def find_usable_key(max_uses=3):
        """Find the oldest API key with at most max_uses usage count"""
        try:
            # Find keys with usage count less than or equal to max_uses that are active
            usable_keys = db['stability_api_keys'].find({
                'usage_count': {'$lte': max_uses},
                'is_active': True
            }).sort('last_used', 1)  # Sort by oldest used first
            
            # Return the first one if available
            api_key_data = next(usable_keys, None)
            if api_key_data:
                return StabilityApiKey(
                    api_key=api_key_data['api_key'],
                    usage_count=api_key_data.get('usage_count', 0),
                    last_used=api_key_data.get('last_used', datetime.datetime.now()),
                    is_active=api_key_data['is_active'],
                    _id=api_key_data['_id']
                )
        except Exception as e:
            print(f"Error finding usable API key: {e}")
        return None
    
    @staticmethod
    def increment_usage(api_key_str):
        """Increment the usage count for a specific API key"""
        try:
            result = db['stability_api_keys'].update_one(
                {'api_key': api_key_str},
                {
                    '$inc': {'usage_count': 1},
                    '$set': {'last_used': datetime.datetime.now()}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating API key usage count: {e}")
            return False
    
    @staticmethod
    def check_credits(api_key_str):
        """
        This method is maintained for backward compatibility.
        Instead of checking credits (which isn't reliable), it now just
        ensures the key exists and updates its last used timestamp.
        """
        try:
            # Check if the key exists in our database
            api_key_data = db['stability_api_keys'].find_one({'api_key': api_key_str})
            
            if api_key_data:
                # Key exists, return its current usage count
                # We return 25 - usage_count to simulate "credits" for backward compatibility
                usage_count = api_key_data.get('usage_count', 0)
                remaining = max(0, 25 - usage_count)  # Simulate "credits" based on usage
                
                # Update the last_used timestamp
                db['stability_api_keys'].update_one(
                    {'api_key': api_key_str},
                    {'$set': {'last_used': datetime.datetime.now()}}
                )
                
                return remaining
            else:
                # Key doesn't exist
                return None
        except Exception as e:
            print(f"Error checking API key: {e}")
            return None