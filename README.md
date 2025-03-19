# AI Thumbnail Generator

An AI-powered application that generates eye-catching thumbnails for YouTube videos using Pollinations.ai and Google's Gemini API.

## Features

- Generate thumbnails based on video descriptions
- Use reference images to guide the style
- User authentication and thumbnail management
- API endpoints for integration with other services

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB

### Setup

1. Clone the repository:
```bash
git clone https://github.com/SamratSinghPhysicist/ai_thumbnail_generator.git
cd ai_thumbnail_generator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
npm install
```

3. Configure the environment variables in the `.env` file:
```
MONGO_URI=your_mongodb_connection_string
SECRET_KEY=your_secret_key
SHRINKEARN_API_KEY=your_shrinkearn_api_key
```

## Monetization with Shrinkearn

This application includes integration with Shrinkearn URL shortener service to monetize download links. When users click on the download button for generated images, they'll be redirected through a Shrinkearn monetized link.

### Setup Instructions

1. Create an account on [Shrinkearn.com](https://shrinkearn.com/)
2. Complete account verification and setup PayPal payment method
3. Generate your API key from your Shrinkearn dashboard
4. Add your API key to the `.env` file
5. Restart the application

### How It Works

- Each time a user generates an image, the direct download link is automatically converted to a Shrinkearn shortened URL
- When users click the download button, they are redirected through the Shrinkearn link, generating ad revenue
- You earn money from each download link click through Shrinkearn's advertising system
- Minimum payout is just $4, which is processed via PayPal (available in India)
- Earn up to $20 per 1000 views, making it one of the highest paying URL shortening services

## Running the Application

```bash
python app.py
```

## Features

- Generate thumbnails based on video descriptions
- Use reference images to guide the style
- User authentication and thumbnail management
- API endpoints for integration with other services
