import requests
import os
import json
import time
from models import StabilityApiKey
from PIL import Image
import io


def resize_image_to_supported_dimensions(image_path):
    """
    Resize an image to one of the supported dimensions for Stability API:
    - 1024×576 (16:9 landscape)
    - 576×1024 (9:16 portrait)
    - 768×768 (1:1 square)
    
    Parameters:
    - image_path (str): Path to the input image
    
    Returns:
    - bytes: Resized image data as bytes
    - str: New dimensions as string (e.g., "1024x576")
    """
    try:
        # Open the image
        with Image.open(image_path) as img:
            # Convert to RGB if it's RGBA or has an alpha channel
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # Convert to RGB to ensure compatibility
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                # Convert any other mode to RGB
                img = img.convert('RGB')
            
            original_width, original_height = img.size
            
            # Calculate aspect ratio
            aspect_ratio = original_width / original_height
            
            # Determine best target dimensions based on aspect ratio
            if aspect_ratio > 1.5:  # Wide landscape
                target_dimensions = (1024, 576)
            elif aspect_ratio < 0.67:  # Tall portrait
                target_dimensions = (576, 1024)
            else:  # Near square
                target_dimensions = (768, 768)
            
            # Resize the image while preserving aspect ratio (fit within target dimensions)
            try:
                img = img.resize(target_dimensions, Image.LANCZOS)
            except AttributeError:
                # Fallback for older PIL versions that might not have LANCZOS
                img = img.resize(target_dimensions, Image.ANTIALIAS if hasattr(Image, 'ANTIALIAS') else Image.BICUBIC)
            
            # Convert the resized image to bytes
            img_byte_arr = io.BytesIO()
            
            # Save in JPEG format for maximum compatibility with Stability API
            img.save(img_byte_arr, format='JPEG', quality=95)
            img_byte_arr.seek(0)
            
            # Return resized image data and dimensions string
            return img_byte_arr.getvalue(), f"{target_dimensions[0]}x{target_dimensions[1]}"
    
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        raise ValueError(f"Failed to process the image: {str(e)}")


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


def img2video(api_key, 
             image_path, 
             seed=0, 
             cfg_scale=1.5, 
             motion_bucket_id=127):
    """
    Generate a video from an image using Stability AI's image-to-video API.
    
    Parameters:
    - api_key (str): Your Stability AI API key
    - image_path (str): Path to the input image file
    - seed (int, optional): Randomness seed for generation (0 means random)
    - cfg_scale (float, optional): How strongly the video sticks to the original image (0.0-10.0)
    - motion_bucket_id (int, optional): Controls the amount of motion (1-255)
    
    Returns:
    - str: The generation ID to poll for results
    - str: Resized dimensions string (if resizing was done)
    - str: API key used (for later deletion)
    """
    
    # Validate parameters
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")
    
    if cfg_scale < 0 or cfg_scale > 10:
        raise ValueError("cfg_scale must be between 0 and 10")
    
    if motion_bucket_id < 1 or motion_bucket_id > 255:
        raise ValueError("motion_bucket_id must be between 1 and 255")
    
    # If no API key is provided, try to get one from the database
    if api_key is None:
        api_key = get_api_key()
        if api_key is None:
            raise ValueError("No API keys available in the database")
    
    try:
        # Resize image to supported dimensions
        img_data, dimensions = resize_image_to_supported_dimensions(image_path)
        print(f"Image resized to {dimensions}")
        
        # Prepare API endpoint
        host = "https://api.stability.ai/v2beta/image-to-video"
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        # Do NOT set Content-Type header here - requests will set it automatically with boundary
        
        # Prepare form data with parameters
        form_data = {}
        
        # Add optional parameters if provided
        if seed != 0:
            form_data["seed"] = str(seed)
        
        if cfg_scale != 1.5:  # Default value
            form_data["cfg_scale"] = str(cfg_scale)
            
        if motion_bucket_id != 127:  # Default value
            form_data["motion_bucket_id"] = str(motion_bucket_id)
        
        # Prepare files
        files = {
            "image": (os.path.basename(image_path), img_data)
        }
        
        print(f"Sending request to Stability API img2video endpoint with API key: {api_key[:5]}...{api_key[-4:]}")
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
                
                # Check for 402 Payment Required (insufficient credits)
                if response.status_code == 402:
                    print(f"API key has insufficient credits, marking as invalid")
                    # Mark this key as invalid in the database
                    StabilityApiKey.delete_key(api_key)
                    
                    # Try to get another key
                    new_api_key = get_api_key()
                    if new_api_key:
                        print(f"Retrying with a different API key")
                        # Recursive call with new API key
                        return img2video(
                            api_key=new_api_key,
                            image_path=image_path,
                            seed=seed,
                            cfg_scale=cfg_scale,
                            motion_bucket_id=motion_bucket_id
                        )
                
                raise Exception(f"API request failed: {response.status_code} - {error_detail}")
            except json.JSONDecodeError:
                print(f"Error response (not JSON): {response.text}")
                raise Exception(f"API request failed: {response.status_code} - {response.text}")
        
        # Parse the response JSON
        resp_json = response.json()
        
        # Get generation ID for polling
        generation_id = resp_json.get("id")
        
        if not generation_id:
            raise Exception("No generation ID returned from the API")
        
        print(f"Generation started with ID: {generation_id}")
        
        # Do NOT delete the API key yet - we need it for polling
        # Instead, return it with the generation ID so it can be deleted after the video is retrieved
        
        return generation_id, dimensions, api_key
    except Exception as e:
        print(f"Error in img2video: {str(e)}")
        # Don't delete the API key on error, as we might want to retry
        raise e


def get_video_result(api_key, generation_id):
    """
    Check the status of a video generation and retrieve the result when complete.
    
    Parameters:
    - api_key (str): Your Stability AI API key
    - generation_id (str): The ID of the generation to check
    
    Returns:
    - dict: Status information with keys:
        - 'status': str - 'in-progress' or 'complete'
        - 'video': bytes - Video data (if complete)
    """
    # If no API key is provided, try to get one from the database
    if api_key is None:
        api_key = get_api_key()
        if api_key is None:
            raise ValueError("No API keys available in the database")
    
    # Prepare API endpoint
    host = f"https://api.stability.ai/v2beta/image-to-video/result/{generation_id}"
    
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "video/*"  # Request video data directly
    }
    
    try:
        # Send request
        response = requests.get(host, headers=headers)
        
        # Check for progress status
        if response.status_code == 202:
            return {"status": "in-progress"}
        
        # Check for errors
        if response.status_code != 200:
            try:
                error_detail = response.json()
                print(f"Error response: {error_detail}")
                
                # Check for 402 Payment Required (insufficient credits)
                if response.status_code == 402:
                    print(f"API key has insufficient credits, marking as invalid")
                    # Mark this key as invalid in the database
                    StabilityApiKey.delete_key(api_key)
                    
                    # Try to get another key
                    new_api_key = get_api_key()
                    if new_api_key:
                        print(f"Retrying with a different API key")
                        # Recursive call with new API key
                        return get_video_result(new_api_key, generation_id)
                
                raise Exception(f"API request failed: {response.status_code} - {error_detail}")
            except json.JSONDecodeError:
                print(f"Error response (not JSON): {response.text}")
                raise Exception(f"API request failed: {response.status_code} - {response.text}")
        
        # If we got here, the video is ready
        video_data = response.content
        
        # Get headers for additional info
        finish_reason = response.headers.get("finish-reason", "SUCCESS")
        seed_used = response.headers.get("seed", "unknown")
        
        # After successfully retrieving the video, delete the API key
        try:
            # Delete the key - it's been fully used now
            StabilityApiKey.delete_key(api_key)
            print(f"API key used and deleted from database")
        except Exception as e:
            print(f"Error deleting API key: {e}")
        
        return {
            "status": "complete",
            "video": video_data,
            "finish_reason": finish_reason,
            "seed": seed_used
        }
    except Exception as e:
        print(f"Error checking video status: {str(e)}")
        # Don't delete the API key on error, as we might want to retry
        raise Exception(f"Failed to check video status: {str(e)}")


def save_video(video_data, output_directory, filename_prefix=None, seed=None):
    """
    Save the generated video to disk.
    
    Parameters:
    - video_data (bytes): The generated video data
    - output_directory (str): Directory to save the video
    - filename_prefix (str, optional): Prefix for the filename
    - seed (str, optional): Seed used for generation to include in filename
    
    Returns:
    - str: Path to the saved video file
    """
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create a unique filename
    if filename_prefix:
        # Sanitize the prefix
        safe_prefix = ''.join(c if c.isalnum() else '_' for c in filename_prefix)[:25]
    else:
        safe_prefix = 'img2video'
    
    # Include seed if provided
    if seed:
        filename = f"{safe_prefix}_{seed}.mp4"
    else:
        timestamp = int(time.time())
        filename = f"{safe_prefix}_{timestamp}.mp4"
    
    # Full path
    output_path = os.path.join(output_directory, filename)
    
    # Save the video
    with open(output_path, 'wb') as f:
        f.write(video_data)
    
    print(f"Video saved to: {output_path}")
    return output_path


def generate_video_from_image(image_path, output_directory, seed=0, cfg_scale=1.5, motion_bucket_id=127, timeout=600):
    """
    Complete process to generate a video from an image and save it to disk.
    Handles the API call, polling for results, and saving the video.
    
    Parameters:
    - image_path (str): Path to the input image
    - output_directory (str): Directory to save the output video
    - seed (int, optional): Seed for generation randomness (0 = random)
    - cfg_scale (float, optional): How strongly the video sticks to the original image
    - motion_bucket_id (int, optional): Amount of motion in the video (1-255)
    - timeout (int, optional): Maximum time to wait for generation in seconds
    
    Returns:
    - str: Path to the saved video or None if generation failed
    - str: Generation ID for reference
    - str: Error message if generation failed, None otherwise
    """
    try:
        # Get API key
        api_key = get_api_key()
        if not api_key:
            error_msg = "No API keys available. Cannot generate video."
            print(error_msg)
            return None, None, error_msg
        
        # Start the video generation
        try:
            generation_id, dimensions, api_key = img2video(
                api_key=api_key,
                image_path=image_path,
                seed=seed,
                cfg_scale=cfg_scale,
                motion_bucket_id=motion_bucket_id
            )
        except Exception as e:
            error_str = str(e)
            if "402" in error_str and "credits" in error_str.lower():
                # This is already handled in img2video with key deletion and retry
                # But if we still got the error here, it means we've run out of valid keys
                error_msg = "Insufficient credits on all available API keys. Please add a new API key with sufficient credits."
                print(error_msg)
                return None, None, error_msg
            else:
                # Other error occurred
                error_msg = f"Error starting video generation: {e}"
                print(error_msg)
                return None, None, error_msg
        
        # Calculate end time for timeout
        end_time = time.time() + timeout
        
        # Poll for results
        while time.time() < end_time:
            # Wait 5 seconds between polls
            time.sleep(5)
            
            # Check generation status
            try:
                result = get_video_result(api_key, generation_id)
                
                if result["status"] == "complete":
                    # Get filename from input image
                    filename_prefix = os.path.splitext(os.path.basename(image_path))[0]
                    
                    # Save the video
                    video_path = save_video(
                        video_data=result["video"],
                        output_directory=output_directory,
                        filename_prefix=filename_prefix,
                        seed=result.get("seed")
                    )
                    
                    return video_path, generation_id, None
                
                print(f"Generation in progress, waiting... ({int(end_time - time.time())} seconds remaining)")
            
            except Exception as e:
                error_str = str(e)
                if "402" in error_str and "credits" in error_str.lower():
                    # This is a payment required error, which has already been handled in get_video_result
                    # If we still got the error here, we need to check if we can get a new API key
                    new_api_key = get_api_key()
                    if new_api_key:
                        print(f"Trying with a new API key for polling: {new_api_key[:5]}...{new_api_key[-4:]}")
                        api_key = new_api_key
                        continue  # Try again with the new key
                    else:
                        error_msg = "Insufficient credits on all available API keys. Please add a new API key with sufficient credits."
                        print(error_msg)
                        return None, generation_id, error_msg
                
                print(f"Error checking generation status: {e}")
                # Continue polling despite errors
        
        # If we got here, we timed out
        error_msg = f"Generation timed out after {timeout} seconds"
        print(error_msg)
        return None, generation_id, error_msg
        
    except Exception as e:
        error_msg = f"Error generating video: {e}"
        print(error_msg)
        return None, None, error_msg


if __name__ == "__main__":
    # Example usage
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate a video from an image using Stability AI")
    parser.add_argument("--image", required=True, help="Path to the input image")
    parser.add_argument("--output", default="./processed_videos", help="Output directory for the video")
    parser.add_argument("--seed", type=int, default=0, help="Seed for generation (0 = random)")
    parser.add_argument("--cfg_scale", type=float, default=1.5, help="How strongly the video sticks to the image (0-10)")
    parser.add_argument("--motion", type=int, default=127, help="Amount of motion (1-255)")
    args = parser.parse_args()
    
    video_path, generation_id, error = generate_video_from_image(
        image_path=args.image,
        output_directory=args.output,
        seed=args.seed,
        cfg_scale=args.cfg_scale,
        motion_bucket_id=args.motion
    )
    
    if video_path:
        print(f"Video generated successfully: {video_path}")
        print(f"Generation ID: {generation_id}")
    else:
        print(f"Video generation failed: {error}") 