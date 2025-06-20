# Stability AI Integration

This document provides information on how the Stability AI API is integrated into our application for text-to-image, image-to-image, and image-to-video generation.

## Stability AI Ultra API

Our application uses the Stability AI Ultra API, which provides high-quality image generation capabilities. The API is accessed via a REST endpoint and requires an API key for authentication.

## API Key Management

API keys are managed through the database and are used in a rotating fashion. Once an API key is used, it is removed from the database to prevent overuse.

To add API keys to the database, use the API key management page in the admin interface.

## Text-to-Image Generation

Text-to-image generation is implemented in the `text2img_stability.py` file. The main function to use is `generate_image_stability()`, which takes the following parameters:

- `prompt` (str, required): Text description of the desired image
- `testMode` (bool, required): Whether to use a placeholder image instead of calling the API
- `negative_prompt` (str, optional): Text description of what to exclude from the image
- `aspect_ratio` (str, optional): Aspect ratio of the output image (default: "1:1")
- `seed` (int, optional): Seed for reproducible results (0 means random)
- `style_preset` (str, optional): Style preset to guide the image model
- `output_format` (str, optional): Format of the output image (png, jpeg, webp)

Example usage:

```python
from text2img_stability import generate_image_stability

# Generate an image
image_path = generate_image_stability(
    prompt="A beautiful mountain landscape with a sunset",
    testMode=False,
    aspect_ratio="16:9",
    output_format="png"
)
```

## Image-to-Image Generation

Image-to-image generation is implemented in the `img2img_stability.py` file. The main function to use is `img2img()`, which takes the following parameters:

- `api_key` (str): Your Stability AI API key
- `prompt` (str): Text description of the desired output image
- `image_path` (str): Path to the input image file
- `negative_prompt` (str, optional): Keywords of what you do not wish to see
- `aspect_ratio` (str, optional): Aspect ratio of the output image
- `seed` (int, optional): Randomness seed for generation
- `style_preset` (str, optional): Style preset to guide the image model
- `output_format` (str, optional): Format of the output image (png, jpeg, webp)
- `strength` (float, optional): How much influence the input image has (0-1)

Example usage:

```python
from img2img_stability import img2img

# Transform an image
image_data, result_info = img2img(
    api_key=None,  # Will get from database
    prompt="A mountain landscape with a sunset",
    image_path="input_image.jpg",
    strength=0.7,
    aspect_ratio="16:9"
)
```

## Image-to-Video Generation

Image-to-video generation is implemented in the `img2video_stability.py` file. The generation process is asynchronous, meaning you start a generation and then poll for results. The main functions to use are:

1. `img2video()` - Starts a video generation:
   - `api_key` (str): Your Stability AI API key
   - `image_path` (str): Path to the input image file
   - `seed` (int, optional): Randomness seed for generation (0 means random)
   - `cfg_scale` (float, optional): How strongly the video sticks to the original image (0.0-10.0)
   - `motion_bucket_id` (int, optional): Controls the amount of motion (1-255)

2. `get_video_result()` - Checks the status of a generation and retrieves results:
   - `api_key` (str): Your Stability AI API key
   - `generation_id` (str): The ID of the generation to check

3. `generate_video_from_image()` - Complete process that handles generation, polling, and saving:
   - `image_path` (str): Path to the input image
   - `output_directory` (str): Directory to save the output video
   - `seed` (int, optional): Seed for generation randomness
   - `cfg_scale` (float, optional): How strongly the video adheres to the image
   - `motion_bucket_id` (int, optional): Amount of motion in the video
   - `timeout` (int, optional): Maximum time to wait for generation in seconds

Example usage:

```python
from img2video_stability import generate_video_from_image

# Generate a video from an image
video_path, generation_id = generate_video_from_image(
    image_path="input_image.jpg",
    output_directory="./processed_videos",
    seed=0,  # Random seed
    cfg_scale=1.5,  # Default value
    motion_bucket_id=127  # Default value
)

if video_path:
    print(f"Video generated successfully: {video_path}")
```

For more control over the process, you can use the individual functions:

```python
from img2video_stability import img2video, get_video_result, save_video
import time

# Start generation
generation_id = img2video(
    api_key=None,  # Will get from database
    image_path="input_image.jpg"
)

# Poll for results (every 5 seconds)
while True:
    time.sleep(5)
    result = get_video_result(api_key=None, generation_id=generation_id)
    
    if result["status"] == "complete":
        # Save the video
        video_path = save_video(
            video_data=result["video"],
            output_directory="./processed_videos",
            filename_prefix="my_video"
        )
        print(f"Video saved to: {video_path}")
        break
```

## Available Style Presets

Both text-to-image and image-to-image functions support the following style presets:

- 3d-model
- analog-film
- anime
- cinematic
- comic-book
- digital-art
- enhance
- fantasy-art
- isometric
- line-art
- low-poly
- modeling-compound
- neon-punk
- origami
- photographic
- pixel-art
- tile-texture

## Available Aspect Ratios

The following aspect ratios are supported for image generation:

- 16:9
- 1:1
- 21:9
- 2:3
- 3:2
- 4:5
- 5:4
- 9:16
- 9:21

## Testing

You can test the text-to-image functionality using the `test_stability_text2img.py` script:

```bash
python test_stability_text2img.py --prompt "A beautiful sunset over mountains" --aspect-ratio "16:9" --display
```

For image-to-image testing, you can use:

```bash
python img2img_stability.py --prompt "Transform this into a winter scene" --image "input.jpg" --strength 0.7 --display
```

For image-to-video testing, you can use:

```bash
python test_img2video.py --image "input.jpg" --cfg_scale 1.5 --motion 127
```

## API Response Format

The Stability AI API returns generated images directly in the response body. Additional metadata is provided in the response headers, including:

- `finish-reason`: The reason the generation finished (e.g., "SUCCESS", "CONTENT_FILTERED")
- `seed`: The seed used for generation, useful for reproducibility 

For video generation, the initial API call returns a generation ID, and subsequent calls to the result endpoint will return the video data once complete. 