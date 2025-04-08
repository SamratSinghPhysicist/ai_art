from pymongo import MongoClient
import os
from dotenv import load_dotenv
from bson.objectid import ObjectId
import datetime

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['thumbnail_generator']

def create_test_thumbnail():
    """Create a test thumbnail without image_data"""
    # First check if the image file exists
    image_path = 'processed_images/Hyperrealistic_You.jpg'
    full_path = os.path.join(os.getcwd(), image_path)
    
    if not os.path.exists(full_path):
        print(f"Error: Image file {full_path} does not exist")
        return
    
    # Create a test thumbnail without image_data
    thumbnail_data = {
        'user_id': ObjectId('000000000000000000000001'),  # Dummy user ID
        'image_path': image_path,
        'description': 'Test thumbnail without image_data',
        'created_at': datetime.datetime.now()
        # Intentionally not including image_data
    }
    
    result = db['thumbnails'].insert_one(thumbnail_data)
    print(f"Created test thumbnail with ID: {result.inserted_id}")

if __name__ == "__main__":
    create_test_thumbnail()
