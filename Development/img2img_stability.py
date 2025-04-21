import requests
import base64
import os
import json
from PIL import Image
import io
import argparse
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


def img2img(api_key, 
          prompt, 
          image_path, 
          negative_prompt="", 
          aspect_ratio="1:1", 
          seed=0, 
          style_preset=None, 
          output_format="png", 
          strength=0.7):
    """
    Perform image-to-image transformation using Stability AI's API.
    
    Parameters:
    - api_key (str): Your Stability AI API key
    - prompt (str): Text description of the desired output image
    - image_path (str): Path to the input image file
    - negative_prompt (str, optional): Keywords of what you do not wish to see
    - aspect_ratio (str, optional): Aspect ratio of the output image
    - seed (int, optional): Randomness seed for generation
    - style_preset (str, optional): Style preset to guide the image model
    - output_format (str, optional): Format of the output image (png, jpeg, webp)
    - strength (float, optional): How much influence the input image has (0-1)
    
    Returns:
    - bytes: The generated image data
    - dict: Additional information including seed and finish reason
    """
    
    # Validate parameters
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")
    
    if strength < 0 or strength > 1:
        raise ValueError("Strength must be between 0 and 1")
    
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
    
    # Read and encode the image
    with open(image_path, "rb") as img_file:
        img_data = img_file.read()
    
    # Prepare API endpoint
    host = "https://api.stability.ai/v2beta/stable-image/generate/ultra"
    
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*"
    }
    
    # Prepare multipart form data
    files = {
        "image": (os.path.basename(image_path), img_data, f"image/{output_format}")
    }
    
    # Prepare form fields
    form_data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect_ratio,
        "seed": str(seed),
        "output_format": output_format,
        "strength": str(strength)
    }
    
    # Add style preset if provided
    if style_preset is not None:
        form_data["style_preset"] = style_preset
    
    # Send request with multipart/form-data
    response = requests.post(
        host,
        headers=headers,
        files=files,
        data=form_data
    )
    
    # Check for errors
    if response.status_code != 200:
        try:
            error_detail = response.json()
            raise Exception(f"API request failed: {response.status_code} - {error_detail}")
        except json.JSONDecodeError:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
    
    # Extract metadata from headers
    result_info = {
        "finish_reason": response.headers.get("finish-reason"),
        "seed": response.headers.get("seed"),
        "api_key": api_key  # Include the API key used for reference
    }
    
    # Check for content filtering
    if result_info["finish_reason"] == "CONTENT_FILTERED":
        raise Exception("Generation failed due to content filtering")
    
    # Get the image data first
    image_data = response.content
    
    # After successful generation and data retrieval, delete the API key from the database
    try:
        # Delete the key
        StabilityApiKey.delete_key(api_key)
        print(f"API key used and deleted from database")
    except Exception as e:
        print(f"Error deleting API key: {e}")
    
    return image_data, result_info


def save_image(image_data, output_path=None, seed=None):
    """
    Save the generated image to a file.
    
    Parameters:
    - image_data (bytes): The image data to save
    - output_path (str, optional): Path to save the image to
    - seed (str, optional): Seed used for generation, used in filename if output_path not provided
    
    Returns:
    - str: The path where the image was saved
    """
    if output_path is None:
        # Generate a filename based on seed
        seed_str = seed if seed is not None else "unknown"
        output_path = f"generated_{seed_str}.png"
    
    with open(output_path, "wb") as f:
        f.write(image_data)
    
    return output_path


def display_image(image_path):
    """
    Display the generated image.
    
    Parameters:
    - image_path (str): Path to the image file
    """
    try:
        img = Image.open(image_path)
        img.show()
    except Exception as e:
        print(f"Failed to display image: {e}")


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Image-to-Image generation using Stability AI")
    parser.add_argument("--api-key", help="Your Stability AI API key (optional, will use from database if not provided)")
    parser.add_argument("--prompt", required=True, help="Text description of the desired output image")
    parser.add_argument("--image", required=True, help="Path to the input image file")
    parser.add_argument("--negative-prompt", default="", help="Keywords of what you do not wish to see")
    parser.add_argument("--aspect-ratio", default="1:1", 
                        choices=["16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"],
                        help="Aspect ratio of the output image")
    parser.add_argument("--seed", type=int, default=0, help="Randomness seed for generation")
    parser.add_argument("--style-preset", 
                        choices=["3d-model", "analog-film", "anime", "cinematic", "comic-book", 
                                "digital-art", "enhance", "fantasy-art", "isometric", "line-art", 
                                "low-poly", "modeling-compound", "neon-punk", "origami", 
                                "photographic", "pixel-art", "tile-texture"],
                        help="Style preset to guide the image model")
    parser.add_argument("--output-format", default="png", choices=["png", "jpeg", "webp"],
                        help="Format of the output image")
    parser.add_argument("--strength", type=float, default=0.7, 
                        help="How much influence the input image has (0-1)")
    parser.add_argument("--output", help="Path to save the output image")
    parser.add_argument("--display", action="store_true", help="Display the generated image")
    
    args = parser.parse_args()
    
    try:
        # Generate image
        print("Generating image...")
        
        # If API key is provided, use it; otherwise get one from the database
        api_key = args.api_key
        if not api_key:
            api_key = get_api_key()
            if not api_key:
                print("Error: No API keys available in the database")
                return
        
        image_data, result_info = img2img(
            api_key=api_key,
            prompt=args.prompt,
            image_path=args.image,
            negative_prompt=args.negative_prompt,
            aspect_ratio=args.aspect_ratio,
            seed=args.seed,
            style_preset=args.style_preset,
            output_format=args.output_format,
            strength=args.strength
        )
        
        # Save image
        output_path = save_image(image_data, args.output, result_info["seed"])
        print(f"Image saved to: {output_path}")
        print(f"Seed: {result_info['seed']}")
        
        # Display image if requested
        if args.display:
            display_image(output_path)
            
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()