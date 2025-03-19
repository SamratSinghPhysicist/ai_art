import requests
import re
import base64
from base64 import b64decode
from pathlib import Path
import random
import os
from urllib.parse import quote

from gemini_generator import generate_gemini
from image_editor import process_image
# Note: image_analyzer is imported dynamically in main_image_function when needed


def image_generate_prompt_pollinations(video_thumbnail_description, api_key_gemini):
    # Base prompt
    prompt = f"""You are an expert YouTube thumbnail designer and prompt engineer for Pollinations.ai. I need a prompt that will generate a realistic, eye-catching, and highly click-worthy YouTube thumbnail.

    Here's the context for the video thumbnail: [{video_thumbnail_description}]

    Key elements I want to emphasize in the thumbnail are: [List 2-3 key visual elements or emotions you want to convey. For example: "Success, a close-up of a giant pumpkin, and a surprised face," or "Sharp details, vibrant colors, and a sense of cutting-edge technology," or "Intricate details, a sense of fantasy, and a time-lapse effect."]

    Consider these factors for a clicky thumbnail:

    Realism: Aim for a photorealistic or highly detailed style.
    Eye-Catching: Use vibrant colors, strong contrasts, and compelling compositions.
    Click-Worthy: Evoke curiosity, excitement, or a sense of urgency.
    Clarity: Ensure the main subject is clear and easily recognizable.
    Generate a detailed prompt for Pollinations.ai that includes:

    A clear description of the subject matter.
    Specific keywords related to the desired style (e.g., photorealistic, hyperrealistic, cinematic lighting, dramatic shadows).
    Instructions for composition (e.g., close-up, wide shot, rule of thirds).
    Desired color palette and lighting effects.
    Any facial expressions that are needed.
    Instructions to make the image "click worthy"

    Pay special attention to: {video_thumbnail_description}
    """
    prompt += """

    Provide the Pollinations.ai prompt in a single, concise paragraph that can be directly copied and pasted.

    Don't say/write anything other than the prompt as I will directly give your response to pollinations.ai via code. So make sure that you just give the prompt.
    """

    image_generate_prompt = generate_gemini(prompt, api_key_gemini)

    image_generate_prompt = image_generate_prompt.replace('\\', ' ')
    image_generate_prompt = image_generate_prompt.replace('\n', ' ')

    return image_generate_prompt

def generate_image_pollinations_ai(prompt, testMode, width=1920, height=1080, seed=random.randint(1,100000), model='flux-realism', style=None):
    if testMode == False:
        # Define the subfolder and filename
        subfolder = Path("images")
        # Create the subfolder if it doesn't exist
        subfolder.mkdir(parents=True, exist_ok=True)

        # Clean up prompt to be used as a file name
        for char in [' ', ',', '/', '\\', '!', '\n', '.', ';', '?', ':', '\'', '"', '`', '~', '@', '#', '$', '%', '^', '&', '*', '=', '>', '<']:
            prompt = prompt.replace(char, '_')
        
        # Define the full file path where the image will be saved
        filepath = f"images/{prompt}.jpg"
        # Make sure the filename is not overly long
        safe_filepath = f"{filepath[:25]}.jpg"
        image_path = safe_filepath

        def download_image(image_url, image_path):
            try:
                response = requests.get(image_url)
            except Exception as e:
                print("Error during requests.get:", e)
                print("Using test_assests/placeholder.jpg")
                return "test_assets/placeholder.jpg"

            # Check if the request was successful
            if response.status_code == 200 and response.content:
                with open(image_path, 'wb') as file:
                    file.write(response.content)
                
                # Verify the file size is reasonable (i.e., not an empty or near-empty file)
                file_size = Path(image_path).stat().st_size
                if file_size < 1:  # adjust this threshold if needed
                    print("Downloaded image is too small (likely invalid). Using placeholder image.")
                    return "test_assets/placeholder.jpg"
                else:
                    print("Download Completed")
                    return image_path
            else:
                print("Failed to download image for this scene. Using test_assests/placeholder.jpg")
                return "test_assets/placeholder.jpg"

        # URL encode the prompt for the API request
        encoded_prompt = quote(prompt)
        
        
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&model={model}"
        path_of_downloaded_image = download_image(image_url, image_path)
        return path_of_downloaded_image

    else:
        print("Test Mode is ON. Placeholder images will be used.")
        print("Path of placeholder.jpg: /test_assets/placeholder.jpg")
        return "test_assets/placeholder.jpg"

def main_image_function(video_description, testMode, api_key_gemini):
    if testMode == False:
        try:
            # Generate the prompt
            image_prompt = image_generate_prompt_pollinations(video_description, api_key_gemini)
            
            generated_image_path = generate_image_pollinations_ai(image_prompt, testMode)
            
            # Process the image to remove the watermark
            processed_image_path = process_image(generated_image_path)

            return f"{processed_image_path}"

        except Exception as e:
            print("Error in generating Image:", e)
    else:
        print("Test Mode is ON")
        print("Skipping the image search and download process, and using placeholder images")
        print("To turn off the Test Mode, change the testMode variable to False in main_image_function()")

        return f"test_assets/placeholder.jpg"
