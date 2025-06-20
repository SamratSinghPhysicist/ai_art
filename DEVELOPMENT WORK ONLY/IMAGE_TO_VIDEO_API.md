# Image-to-Video API Documentation

This document explains how to use the Image-to-Video API endpoint that leverages Stability AI's API to generate a short video based on a single still image.

## Overview

The Image-to-Video generation uses Stability AI's Stable Video Diffusion model to animate a still image into a short video. The process is asynchronous:

1. You submit an image and receive a generation ID
2. You poll a separate endpoint with the generation ID to check status and get the result when ready

## API Endpoints

### Start Video Generation

**Endpoint:** `/api/img2video`

**Method:** `POST`

**Content-Type:** `multipart/form-data`

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| image | File | Yes | The source image to animate |
| seed | Integer | No | Seed for random generation (0 = random) |
| cfg_scale | Float | No | How strongly the video sticks to the original image (0-10, default: 1.5) |
| motion_bucket_id | Integer | No | Controls the amount of motion (1-255, default: 127) |

**Response:**

Success (200):
```json
{
  "success": true,
  "id": "a1b2c3d4e5f6...",
  "message": "Video generation started. Poll for results using the returned ID."
}
```

Error (400/500):
```json
{
  "error": "Error message details"
}
```

### Poll for Results

**Endpoint:** `/api/img2video/result/{id}`

**Method:** `GET`

**Path Parameters:**

| Parameter | Description |
|-----------|-------------|
| id | The generation ID returned from the initial request |

**Response:**

In Progress (202):
```json
{
  "status": "in-progress",
  "message": "Video generation is still in progress. Try again in a few seconds."
}
```

Complete (200):
```json
{
  "status": "complete",
  "video_url": "/processed_videos/video_a1b2c3d4_12345.mp4",
  "finish_reason": "SUCCESS",
  "seed": "12345"
}
```

Error (404/500):
```json
{
  "error": "Error message details"
}
```

## Example Usage

### Python

```python
import requests
import time
import os

# API endpoint to start generation
upload_url = "http://your-website.com/api/img2video"

# Path to image file
image_path = "path/to/your/image.jpg"

# Optional parameters
params = {
    "seed": 0,  # random seed
    "cfg_scale": 1.5,  # default value
    "motion_bucket_id": 127  # default value
}

# Prepare the file for upload
files = {
    "image": (os.path.basename(image_path), open(image_path, "rb"))
}

# Start generation
response = requests.post(upload_url, files=files, data=params)
generation_data = response.json()

if not response.ok:
    print(f"Error starting generation: {generation_data.get('error')}")
    exit(1)

# Get the generation ID
generation_id = generation_data["id"]
print(f"Generation started with ID: {generation_id}")

# Poll for results
result_url = f"http://your-website.com/api/img2video/result/{generation_id}"

# Poll every 5 seconds for up to 10 minutes
max_attempts = 120
for attempt in range(max_attempts):
    print(f"Checking status... (attempt {attempt+1}/{max_attempts})")
    response = requests.get(result_url)
    
    if response.status_code == 202:
        # Still in progress
        time.sleep(5)
        continue
    
    if response.status_code == 200:
        # Complete
        result = response.json()
        print(f"Video generation complete!")
        print(f"Video URL: http://your-website.com{result['video_url']}")
        print(f"Finish reason: {result['finish_reason']}")
        print(f"Seed: {result['seed']}")
        break
    
    # Error
    print(f"Error checking status: {response.text}")
    break
else:
    print("Generation timed out after 10 minutes")
```

### JavaScript (Browser)

```javascript
async function generateVideo() {
  const imageInput = document.getElementById('imageInput');
  const statusDiv = document.getElementById('status');
  
  if (!imageInput.files.length) {
    statusDiv.innerHTML = 'Please select an image file';
    return;
  }
  
  // Create form data
  const formData = new FormData();
  formData.append('image', imageInput.files[0]);
  formData.append('seed', 0); // Use random seed
  formData.append('cfg_scale', 1.5); // Default value
  formData.append('motion_bucket_id', 127); // Default value
  
  statusDiv.innerHTML = 'Starting video generation...';
  
  try {
    // Start generation
    const response = await fetch('/api/img2video', {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Unknown error');
    }
    
    const data = await response.json();
    const generationId = data.id;
    
    statusDiv.innerHTML = `Generation started with ID: ${generationId}<br>Polling for results...`;
    
    // Poll for results
    const maxAttempts = 120; // 10 minutes at 5-second intervals
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      // Wait 5 seconds between checks
      await new Promise(resolve => setTimeout(resolve, 5000));
      
      statusDiv.innerHTML = `Checking status... (attempt ${attempt+1}/${maxAttempts})`;
      
      const resultResponse = await fetch(`/api/img2video/result/${generationId}`);
      
      if (resultResponse.status === 202) {
        // Still in progress
        continue;
      }
      
      if (resultResponse.status === 200) {
        // Complete
        const result = await resultResponse.json();
        statusDiv.innerHTML = `
          <p>Video generation complete!</p>
          <video controls src="${result.video_url}" style="max-width: 100%;"></video>
          <p>Finish reason: ${result.finish_reason}</p>
          <p>Seed: ${result.seed}</p>
        `;
        break;
      }
      
      // Error
      const error = await resultResponse.json();
      throw new Error(error.error || 'Unknown error');
    }
  } catch (error) {
    statusDiv.innerHTML = `Error: ${error.message}`;
  }
}
```

## Parameters Explanation

### cfg_scale

`cfg_scale` controls how strictly the video adheres to the input image. Lower values (closer to 0) give the model more freedom, potentially creating more dramatic motion but possibly less faithful to the original image. Higher values (up to 10) force the video to stay closer to the input image in terms of content and composition.

Default: 1.5

### motion_bucket_id

`motion_bucket_id` controls the intensity of motion in the generated video. Lower values (closer to 1) result in subtle, minimal movement. Higher values (up to 255) create more dramatic, exaggerated motion throughout the video.

Default: 127

### seed

`seed` is a value that controls the randomness of the generation. Using the same seed with the same input image and parameters will produce similar (though not necessarily identical) results. Use 0 for a random seed each time, or specify a specific value for more reproducible results.

Default: 0 (random)

## Notes

- The generated videos are typically a few seconds long
- Results are stored for 24 hours before being automatically deleted
- Each successful generation costs 20 credits
- Generation typically takes between 10-30 seconds depending on server load
- Maximum file size for input images is 10MB
- Supported image formats: JPEG and PNG
- Supported image dimensions: 1024x576, 576x1024, 768x768 pixels

## Troubleshooting

If you receive a 400 error, check that:
- The image file is properly formatted (JPG or PNG)
- The parameters are within valid ranges

If you receive a 500 error:
- The API key may be invalid
- The server may be experiencing issues
- There might be internal quota limitations

If generation appears stuck:
- Some generations can take longer than others
- After 10 minutes, you may want to restart the generation 