# Stability AI Integration

This document provides information on how the Stability AI API is integrated into our application for both text-to-image and image-to-image generation.

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

The following aspect ratios are supported:

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

## API Response Format

The Stability AI API returns the generated image directly in the response body. Additional metadata is provided in the response headers, including:

- `finish-reason`: The reason the generation finished (e.g., "SUCCESS", "CONTENT_FILTERED")
- `seed`: The seed used for generation, useful for reproducibility 