import requests
import json
import os

# Use local server for testing
LOCAL_SERVER = False

# API endpoint URL - use either local or production
if LOCAL_SERVER:
    base_url = "http://localhost:5000"
else:
    base_url = "https://aiart-zroo.onrender.com"

url = f"{base_url}/api/generate"

# Payload for the API
payload = {
    "video_description": "A futuristic city skyline at sunset, with flying cars and neon holographic billboards, cyberpunk style",
    "negative_prompt": "blurry, low quality, distorted faces, poor lighting",
    "style_preset": "neon-punk",
    "aspect_ratio": "16:9",
    "output_format": "png",
    "seed": 0
}

# Headers for the API request
headers = {"Content-Type": "application/json"}

print(f"Connecting to: {url}")
print("Sending request...")

# Make the API request
response = requests.post(url, headers=headers, json=payload)

# Check if the request was successful
if response.status_code == 200:
    result = response.json()
    print("Response received successfully!")
    print(f"Response: {result}")
    print(f"==="*30 + "Image generated successfully!" + "==="*30)
    
    # Get original URL
    image_url = result.get('image_url', 'Not provided')
    
    # Fix issues with known URL patterns in the production server
    if '//app/' in image_url:
        # The production server URL has a issue with //app/ in the path
        fixed_url = image_url.replace('//app/', '/')
        print(f"Original URL had //app/ issue, fixed to: {fixed_url}")
        
        # Create alternate URL formats to try
        filename = result.get('filename') or image_url.split('/')[-1]
        folder = result.get('folder') or 'images'
        direct_url = f"{base_url}/{folder}/{filename}"
    else:
        fixed_url = image_url
        direct_url = result.get('direct_url', 'Not provided')
    
    print(f"Image URL: {image_url}")
    print(f"Fixed URL: {fixed_url}")
    print(f"Direct URL: {direct_url}")
    print(f"Filename: {result.get('filename', 'Not provided')}")
    print(f"Folder: {result.get('folder', 'Not provided')}")
    
    # Try downloading with our different URL formats
    urls_to_try = [
        fixed_url,
        direct_url,
        f"{base_url}/{result.get('folder', 'images')}/{result.get('filename', image_url.split('/')[-1])}"
    ]
    
    # Filter out invalid URLs
    urls_to_try = [url for url in urls_to_try if url != 'Not provided' and '://' in url]
    
    # Try each URL
    success = False
    for i, test_url in enumerate(urls_to_try):
        print(f"\nAttempting to download with URL #{i+1}: {test_url}")
        try:
            image_response = requests.get(test_url)
            print(f"Status code: {image_response.status_code}")
            
            if image_response.status_code == 200:
                # Save the image locally
                with open(f'downloaded_image_{i+1}.png', 'wb') as f:
                    f.write(image_response.content)
                print(f"Image successfully downloaded as 'downloaded_image_{i+1}.png'")
                print(f"Image size: {len(image_response.content)} bytes")
                
                # If successful, print the working URL clearly
                print(f"\n★★★ WORKING URL: {test_url} ★★★")
                success = True
                break  # Exit after first successful download
            else:
                print(f"Failed to download. Response code: {image_response.status_code}")
        except Exception as e:
            print(f"Error downloading: {str(e)}")
    
    if not success:
        print("\nAll download attempts failed. The image URL might be incorrect or inaccessible.")
    else:
        print("\nImage download successful! Found a working URL format.")
else:
    print(f"Error: {response.status_code}")
    print(response.text)