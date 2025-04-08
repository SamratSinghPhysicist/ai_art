from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['thumbnail_generator']

def check_thumbnails():
    """Check thumbnails in the database and their image_data status"""
    # Get total count
    total_count = db['thumbnails'].count_documents({})
    print(f"Total thumbnails in database: {total_count}")
    
    # Count thumbnails without image_data
    missing_image_data = db['thumbnails'].count_documents({
        '$or': [
            {'image_data': None},
            {'image_data': {'$exists': False}}
        ]
    })
    print(f"Thumbnails missing image_data: {missing_image_data}")
    
    # Show sample thumbnails
    print("\nSample thumbnails:")
    for thumbnail in db['thumbnails'].find().limit(3):
        has_image_data = 'image_data' in thumbnail and thumbnail['image_data'] is not None
        print(f"ID: {thumbnail['_id']}, Has image_data: {has_image_data}, Path: {thumbnail.get('image_path')}")

if __name__ == "__main__":
    check_thumbnails()
