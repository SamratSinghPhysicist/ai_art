# AI Art Generator

An AI-powered application that generates eye-catching images using Pollinations.ai, Google's Gemini API, and Stability AI's image-to-image API.

## Features

- Generate images based on text descriptions
- Transform existing images with AI (using Stability AI)
- User authentication and image management with Firebase Authentication
- API endpoints for integration with other services

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB
- Firebase project (for authentication)

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

# If using Firebase config files (recommended)  --- Only for DEVELOPMENT:
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
FIREBASE_CONFIG_PATH=./firebase-config.json

# If using Firebase config files (recommended)  --- Only for PRODUCTION in render (See FIREBASE_SETUP.md for more details):
FIREBASE_SERVICE_ACCOUNT_PATH=/etc/secrets/firebase-service-account.json
FIREBASE_CONFIG_PATH=/etc/secrets/firebase-config.json
```

4. Set up Firebase Authentication:
   - Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Email/Password and Google authentication methods
   - Follow the detailed Firebase setup guide in [FIREBASE_SETUP.md](FIREBASE_SETUP.md)

5. Run the application:
```bash
python app.py
```

## Firebase Authentication

This project uses Firebase Authentication to provide secure user management:

- Email/Password authentication with email verification
- Google Sign-in integration
- Password reset functionality
- User data synchronization with MongoDB

**For detailed setup instructions, please see [FIREBASE_SETUP.md](FIREBASE_SETUP.md).**

## Using the Image-to-Image Feature

The image-to-image transformation feature allows you to upload an existing image and transform it based on a text prompt. Here's how to use it:

1. Navigate to the home page and select the "Image to Image" tab
2. Upload an image from your device
3. Enter a prompt describing how you want to transform the image
4. Optionally, add a negative prompt to specify elements to avoid
5. Adjust the transformation strength slider (lower = subtle changes, higher = stronger transformation)
6. Click "Transform Image" to generate your new image