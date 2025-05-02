# Firebase Authentication Setup Guide

This guide will walk you through setting up Firebase Authentication for the AI Art application, covering both local development and deployment on Render.

## Table of Contents
- [Firebase Project Setup](#firebase-project-setup)
- [Authentication Configuration](#authentication-configuration)
- [Client Configuration](#client-configuration)
- [Admin SDK Configuration](#admin-sdk-configuration)
- [Local Development Setup](#local-development-setup)
- [Deployment on Render](#deployment-on-render)

## Firebase Project Setup

1. **Create a Firebase Project**:
   - Go to the [Firebase Console](https://console.firebase.google.com/)
   - Click "Add project"
   - Enter a project name (e.g., "AI Art Generator")
   - Choose whether to enable Google Analytics (recommended)
   - Accept the terms and click "Create project"

2. **Register Your Web App**:
   - From your Firebase project dashboard, click the web icon (`</>`)
   - Give your app a nickname (e.g., "AI Art Web App")
   - Click "Register app"
   - Firebase will display configuration details - you'll need these in the next steps
   - Click "Continue to console"

## Authentication Configuration

1. **Enable Authentication Methods**:
   - In the Firebase console, go to "Authentication" → "Sign-in method"
   - Enable "Email/Password"
   - Enable "Google"
   - For Google authentication, select a project support email (usually your email)
   - Save changes

## Client Configuration

The client configuration is used for user-facing authentication operations like login and signup. You have two options:

### Option 1: JSON File (Recommended)

1. Create a file named `firebase-config.json` in the root directory of your project
2. Copy the configuration snippet Firebase provided when you registered your web app
3. Your file should look like this:
   ```json
   {
     "apiKey": "YOUR_FIREBASE_API_KEY",
     "authDomain": "YOUR_PROJECT_ID.firebaseapp.com",
     "projectId": "YOUR_PROJECT_ID",
     "storageBucket": "YOUR_PROJECT_ID.appspot.com",
     "messagingSenderId": "YOUR_MESSAGING_SENDER_ID",
     "appId": "YOUR_APP_ID",
     "databaseURL": "YOUR_DATABASE_URL (optional)"
   }
   ```
4. Replace the placeholder values with your actual Firebase configuration values

### Option 2: Environment Variables

Set the following environment variables in your `.env` file:
```
FIREBASE_API_KEY=your_api_key
FIREBASE_AUTH_DOMAIN=your_project_id.firebaseapp.com
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_STORAGE_BUCKET=your_project_id.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_messaging_sender_id
FIREBASE_APP_ID=your_app_id
FIREBASE_DATABASE_URL=your_database_url (optional)
```

## Admin SDK Configuration

The Admin SDK is used for server-side operations like verifying tokens and accessing Firebase services with administrative privileges.

### Option 1: Service Account JSON File (Recommended)

1. **Generate a Service Account Key**:
   - In the Firebase console, go to "Project settings" → "Service accounts"
   - Click "Generate new private key"
   - Save the downloaded JSON file as `firebase-service-account.json` in the root directory of your project
   - **IMPORTANT**: Never commit this file to version control!

### Option 2: Environment Variables

If you prefer not to use the JSON file directly, you can extract the values and set them as environment variables in your `.env` file:

```
FIREBASE_TYPE=service_account
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_PRIVATE_KEY_ID=your_private_key_id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=your_client_email
FIREBASE_CLIENT_ID=your_client_id
FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token
FIREBASE_AUTH_PROVIDER_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
FIREBASE_CLIENT_CERT_URL=your_client_cert_url
```

**Note**: The `FIREBASE_PRIVATE_KEY` value must preserve all newlines with `\n` characters and be enclosed in quotes.

## Local Development Setup

For local development, follow these steps:

1. **Service Account Configuration**:
   - Option 1 (Recommended): Place the `firebase-service-account.json` file in the project root
   - Option 2: Add the service account details to your `.env` file

2. **Client Configuration**:
   - Option 1 (Recommended): Create `firebase-config.json` in the project root
   - Option 2: Add the client configuration details to your `.env` file

3. **Environment Variables**:
   - If using JSON files (recommended approach), add these to your `.env`:
     ```
     # Specify paths to your config files (default paths shown)
     FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
     FIREBASE_CONFIG_PATH=./firebase-config.json
     ```

4. **Run the Application**:
   ```bash
   python app.py
   ```

## Deployment on Render

Render makes it easy to securely manage your Firebase configuration:

### Using Secret Files (Recommended)

1. **Prepare Your Files**:
   - Keep your `firebase-service-account.json` and `firebase-config.json` files locally
   - Make sure they're listed in your `.gitignore`

2. **Add Secret Files in Render**:
   - Go to your Render dashboard and select your web service
   - Navigate to "Environment" → "Secret Files"
   - Add the two files:
     - Mount Path: `/etc/secrets/firebase-service-account.json`, File Content: *paste content of your service account json*
     - Mount Path: `/etc/secrets/firebase-config.json`, File Content: *paste content of your firebase config json*

3. **Set Environment Variables in Render**:
   - In the "Environment Variables" section, add:
     ```
     FIREBASE_SERVICE_ACCOUNT_PATH=/etc/secrets/firebase-service-account.json
     FIREBASE_CONFIG_PATH=/etc/secrets/firebase-config.json
     ```

### Using Environment Variables Only

If you prefer not to use secret files, you can add all the required environment variables directly in Render's "Environment Variables" section:

1. Add all the variables listed in the "Client Configuration" and "Admin SDK Configuration" sections above
2. For the `FIREBASE_PRIVATE_KEY`, make sure to:
   - Include the entire key including the BEGIN and END markers
   - Preserve all newlines as `\n`
   - Enclose in quotes if using Render's interface allows

## Verifying Your Setup

To verify your Firebase configuration is working correctly:

1. Start the application
2. Try to sign up with a new email account
3. Verify your email using the verification email sent
4. Log in with the verified account
5. Try Google sign-in

## Troubleshooting

### Private Key Issues

If you encounter errors related to the private key deserialization, ensure:

1. The entire private key is preserved, including the BEGIN and END markers
2. All newlines in the key are properly handled
3. If using environment variables, the key is properly quoted

### Authentication Issues

- Check Firebase console Authentication section to see if users are being created
- Verify your Firebase rules aren't blocking the operations
- Look for errors in your application logs
- Ensure your Firebase project has the appropriate billing plan for your usage

### Deployment Issues

- For Render, check the deployment logs for errors 
- Ensure your secret files are correctly mounted at the paths specified
- Verify all environment variables are set correctly 