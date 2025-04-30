import requests
import os
import json
from pathlib import Path
import random
from models import StabilityApiKey


def get_api_key():
    """
    Get the oldest API key from the database.
    
    Returns:
    - str: A valid API key or None if no key is found
    """
    # Find the oldest available key
    api_key_obj = StabilityApiKey.find_oldest_key()
    
    if api_key_obj:
        print(f"Using API key: {api_key_obj.api_key[:5]}...{api_key_obj.api_key[-4:]}")
        return api_key_obj.api_key
    
    # If we got here, no key was found
    print("No API keys available in the database")
    return None


def text2img(api_key, 
            prompt, 
            negative_prompt="", 
            aspect_ratio="1:1", 
            seed=0, 
            style_preset=None, 
            output_format="png"):
    """
    Generate an image from text using Stability AI's API.
    
    Parameters:
    - api_key (str): Your Stability AI API key
    - prompt (str): Text description of the desired output image
    - negative_prompt (str, optional): Keywords of what you do not wish to see
    - aspect_ratio (str, optional): Aspect ratio of the output image
    - seed (int, optional): Randomness seed for generation
    - style_preset (str, optional): Style preset to guide the image model
    - output_format (str, optional): Format of the output image (png, jpeg, webp)
    
    Returns:
    - bytes: The generated image data
    - dict: Additional information including seed and finish reason
    """
    
    # Validate parameters
    valid_aspect_ratios = ["16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"]
    if aspect_ratio not in valid_aspect_ratios:
        raise ValueError(f"Invalid aspect ratio. Must be one of: {', '.join(valid_aspect_ratios)}")
    
    valid_formats = ["png", "jpeg", "webp"]
    if output_format not in valid_formats:
        raise ValueError(f"Invalid output format. Must be one of: {', '.join(valid_formats)}")
    
    valid_style_presets = [None, "3d-model", "analog-film", "anime", "cinematic", "comic-book", 
                          "digital-art", "enhance", "fantasy-art", "isometric", "line-art", 
                          "low-poly", "modeling-compound", "neon-punk", "origami", 
                          "photographic", "pixel-art", "tile-texture"]
    if style_preset not in valid_style_presets:
        raise ValueError(f"Invalid style preset. Must be one of: {', '.join([str(p) for p in valid_style_presets if p is not None])} or None")
    
    # If no API key is provided, try to get one from the database
    if api_key is None:
        api_key = get_api_key()
        if api_key is None:
            raise ValueError("No API keys available in the database")
    
    # Prepare API endpoint
    host = "https://api.stability.ai/v2beta/stable-image/generate/ultra"
    
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*"
    }
    
    # Prepare form data
    form_data = {
        "prompt": prompt,
        "output_format": output_format,
        "aspect_ratio": aspect_ratio,
        "seed": str(seed)
    }
    
    # Add optional parameters if provided
    if negative_prompt:
        form_data["negative_prompt"] = negative_prompt
    
    if style_preset is not None:
        form_data["style_preset"] = style_preset
    
    # Create dummy file to force multipart/form-data
    # Using an empty bytestring with a placeholder filename
    files = {
        "dummy": ("dummy.txt", b"", "text/plain")
    }
    
    print(f"Sending request to Stability API with headers: {headers}")
    print(f"Form data: {form_data}")
    
    # Send request with multipart/form-data
    response = requests.post(
        host,
        headers=headers,
        data=form_data,
        files=files
    )
    
    print(f"Response status code: {response.status_code}")
    
    # Check for errors
    if response.status_code != 200:
        try:
            error_detail = response.json()
            print(f"Error response: {error_detail}")
            raise Exception(f"API request failed: {response.status_code} - {error_detail}")
        except json.JSONDecodeError:
            print(f"Error response (not JSON): {response.text}")
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
    
    # Extract metadata from headers
    result_info = {
        "finish_reason": response.headers.get("finish-reason"),
        "seed": response.headers.get("seed"),
        "api_key": api_key  # Include the API key used for reference
    }
    
    print(f"Response headers: {dict(response.headers)}")
    
    # Check for content filtering
    if result_info["finish_reason"] == "CONTENT_FILTERED":
        raise Exception("Generation failed due to content filtering")
    
    # Get the image data
    image_data = response.content
    
    # After successful generation and data retrieval, delete the API key from the database
    try:
        # Delete the key
        StabilityApiKey.delete_key(api_key)
        print(f"API key used and deleted from database")
    except Exception as e:
        print(f"Error deleting API key: {e}")
    
    return image_data, result_info


def save_image(image_data, prompt, output_format="png", seed=None):
    """
    Save the generated image to a file.
    
    Parameters:
    - image_data (bytes): The image data to save
    - prompt (str): The prompt used to generate the image
    - output_format (str): Format of the image (png, jpeg, webp)
    - seed (str, optional): Seed used for generation
    
    Returns:
    - str: The path where the image was saved
    """
    # Define the subfolder
    subfolder = Path("images")
    # Create the subfolder if it doesn't exist
    subfolder.mkdir(parents=True, exist_ok=True)
    
    # Clean up prompt to be used as a file name
    safe_prompt = ''.join(c if c.isalnum() else '_' for c in prompt)[:25]
    
    # Generate a filename based on seed
    seed_str = seed if seed is not None else "unknown"
    output_filename = f"sd_ultra_{safe_prompt}_{seed_str}.{output_format}"
    output_path = f"images/{output_filename}"
    
    with open(output_path, "wb") as f:
        f.write(image_data)
    
    return output_path


def generate_image_stability(prompt, testMode, negative_prompt="", aspect_ratio="1:1", 
                           seed=0, style_preset=None, output_format="png"):
    """
    Main function to generate an image using Stability AI's API or return a placeholder in test mode.
    
    Parameters:
    - prompt (str): Text description of the desired output image
    - testMode (bool): Whether to use a placeholder image instead of calling the API
    - negative_prompt (str, optional): Keywords of what you do not wish to see
    - aspect_ratio (str, optional): Aspect ratio of the output image
    - seed (int, optional): Randomness seed for generation (0 means random)
    - style_preset (str, optional): Style preset to guide the image model
    - output_format (str, optional): Format of the output image (png, jpeg, webp)
    
    Returns:
    - str: Path to the generated or placeholder image
    """
    if testMode:
        print("Test Mode is ON. Placeholder images will be used.")
        print("Path of placeholder.jpg: /test_assets/placeholder.jpg")
        return "test_assets/placeholder.jpg"
    
    try:
        # Get API key from the database
        api_key = get_api_key()
        if not api_key:
            print("No API keys available in the database. Using placeholder image.")
            return "test_assets/placeholder.jpg"
        
        # Generate the image
        image_data, result_info = text2img(
            api_key=api_key,
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            style_preset=style_preset,
            output_format=output_format
        )
        
        # Save the image
        generated_image_path = save_image(
            image_data=image_data,
            prompt=prompt,
            output_format=output_format,
            seed=result_info["seed"]
        )
        
        print(f"Generated image saved at: {generated_image_path}")
        return generated_image_path
        
    except Exception as e:
        print(f"Error generating image: {e}")
        return "test_assets/placeholder.jpg" 