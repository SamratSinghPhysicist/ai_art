# GitHub Actions for Stability AI API Key Generation

This repository includes a GitHub Actions workflow to automatically generate Stability AI API keys every 15 minutes and store them in MongoDB.

## Setup Instructions

### 1. MongoDB Setup

Make sure you have a MongoDB instance set up and accessible from GitHub Actions. This could be:
- MongoDB Atlas cloud database
- Self-hosted MongoDB server with public access

### 2. Configure GitHub Secrets

To allow the workflow to connect to your MongoDB database, you need to set up a GitHub Secret:

1. Go to your GitHub repository
2. Navigate to Settings > Secrets and variables > Actions
3. Click "New repository secret"
4. Create a secret with the name `MONGO_URI` and the value of your MongoDB connection string
   - Example format: `mongodb+srv://username:password@cluster.mongodb.net/ai_image_generator`

### 3. Workflow Details

The workflow will:
- Run every 15 minutes automatically
- Generate a new Stability AI API key using Selenium
- Store the key in your MongoDB database
- Update credits information for existing keys

### 4. Manual Triggering

You can also manually trigger the workflow by:
1. Going to the Actions tab in your GitHub repository
2. Selecting the "Generate Stability API Keys" workflow
3. Clicking "Run workflow"

## Troubleshooting

If the workflow fails, check:
1. GitHub Actions logs for detailed error information
2. Ensure your MongoDB connection string is correct
3. Verify that your MongoDB instance is accessible from GitHub's IP ranges
4. Check if Stability AI has changed their website structure (which might require updates to the script)

## Security Note

The workflow uses GitHub Secrets to securely store your MongoDB connection string. Never commit sensitive credentials directly to your repository. 