# AI Art Generator

An AI-powered application that generates eye-catching images using Pollinations.ai, Google's Gemini API, and Stability AI's image-to-image API.

## Features

- Generate images based on text descriptions
- Transform existing images with AI (using Stability AI)
- User authentication and image management
- API endpoints for integration with other services

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB

### Setup

1. Clone the repository:
```bash
git clone https://github.com/SamratSinghPhysicist/ai_art_website_real.git
cd ai_art_website_real
```

2. Install dependencies:
```bash
pip install -r requirements.txt
npm install
```

3. Set up your environment variables in `.env`:
```
MONGO_URI=your_mongodb_connection_string
SECRET_KEY=your_flask_secret_key
STABILITY_API_KEY=your_stability_ai_api_key
```

4. Run the application:
```bash
python app.py
```

## Using the Image-to-Image Feature

The image-to-image transformation feature allows you to upload an existing image and transform it based on a text prompt. Here's how to use it:

1. Navigate to the home page and select the "Image to Image" tab
2. Upload an image from your device
3. Enter a prompt describing how you want to transform the image
4. Optionally, add a negative prompt to specify elements to avoid
5. Adjust the transformation strength slider (lower = subtle changes, higher = stronger transformation)
6. Click "Transform Image" to generate your new image