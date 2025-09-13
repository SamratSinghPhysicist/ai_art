from pymongo import MongoClient

# Your MongoDB URI
MONGO_URI = "mongodb+srv://ai-thumbnail-generator:Study%40123@cluster0.7khtr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Connect to MongoDB
client = MongoClient(MONGO_URI)

# Select the database and collection
db = client["ai_image_generator"]
collection = db["stability_api_keys"]

# Find the oldest 1000 docs sorted by created_at
oldest_docs = collection.find().sort("created_at", 1).limit(1000)

# Extract their IDs
ids_to_delete = [doc["_id"] for doc in oldest_docs]

# Delete them
if ids_to_delete:
    result = collection.delete_many({"_id": {"$in": ids_to_delete}})
    print(f"✅ Deleted {result.deleted_count} oldest documents.")
else:
    print("⚠️ No documents found to delete.")
