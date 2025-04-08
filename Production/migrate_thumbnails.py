from pymongo import MongoClient
import os
import base64
from dotenv import load_dotenv
from bson.objectid import ObjectId

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['thumbnail_generator']

def migrate_thumbnails():
    """Migrate existing thumbnails to include base64 image data"""
    print("Starting thumbnail migration...")
    
    # Get all thumbnails that don't have image_data
    thumbnails = db['thumbnails'].find({
        '$or': [
            {'image_data': None},
            {'image_data': {'$exists': False}}
        ]
    })
    
    # Convert cursor to list and get count
    thumbnails_list = list(thumbnails)
    count = len(thumbnails_list)
    print(f"Found {count} thumbnails that need migration")
    
    success_count = 0
    error_count = 0
    
    for thumbnail in thumbnails_list:
        image_path = thumbnail.get('image_path')
        
        if not image_path:
            print(f"Thumbnail {thumbnail['_id']} has no image_path, skipping")
            error_count += 1
            continue
        
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
        
        print(f"Processing thumbnail {thumbnail['_id']} with path: {image_path}")
        print(f"Full path: {full_path}")
        
        # Read the image file and encode it as base64
        try:
            with open(full_path, 'rb') as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
                
            # Update the thumbnail with the image data
            db['thumbnails'].update_one(
                {'_id': thumbnail['_id']},
                {'$set': {'image_data': image_data}}
            )
            
            print(f"Updated thumbnail {thumbnail['_id']} with image data")
            success_count += 1
            
        except Exception as e:
            print(f"Error updating thumbnail {thumbnail['_id']}: {e}")
            error_count += 1
    
    print(f"Migration complete. Processed {count} thumbnails.")
    print(f"Success: {success_count}, Errors: {error_count}")


if __name__ == "__main__":
    migrate_thumbnails()