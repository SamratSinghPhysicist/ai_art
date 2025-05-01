# Firebase Authentication Setup Guide

This guide walks through setting up Firebase Authentication for the AI Art website.

## 1. Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project"
3. Enter a project name (e.g., "ai-art-website")
4. Follow the setup wizard (enable Google Analytics if desired)
5. Click "Create project"

## 2. Set Up Authentication

1. In the Firebase Console, select your project
2. Go to "Authentication" in the left sidebar
3. Click "Get started"
4. Enable the "Email/Password" provider
5. Optional: Enable other providers like Google, Facebook, etc.
6. Save changes

## 3. Add a Web App to Your Project

1. In the Firebase Console, click the gear icon next to "Project Overview"
2. Select "Project settings"
3. Scroll down to "Your apps" section
4. Click the web icon (</>) to add a web app
5. Register your app with a nickname (e.g., "AI Art Web")
6. Optional: Set up Firebase Hosting if desired
7. Click "Register app"
8. Copy the Firebase configuration object (you'll need it in the next step)

## 4. Set Environment Variables

Add the following environment variables to your `.env` file:

```
# Firebase Authentication
FIREBASE_API_KEY=your_firebase_api_key
FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id
FIREBASE_DATABASE_URL=https://your-project-id.firebaseio.com
```

## 5. Generate a Service Account Key

For the Firebase Admin SDK to work on the server:

1. In Firebase Console, go to "Project settings"
2. Go to the "Service accounts" tab
3. Click "Generate new private key"
4. Save the JSON file securely
5. Add the path to your `.env` file:

```
# Option 1: Path to service account JSON file
FIREBASE_SERVICE_ACCOUNT_PATH=path/to/serviceAccountKey.json
```

OR add the entire JSON content (escape all quotes and newlines):

```
# Option 2: JSON content of service account
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key_id":"...","private_key":"...","client_email":"...","client_id":"...","auth_uri":"...","token_uri":"...","auth_provider_x509_cert_url":"...","client_x509_cert_url":"..."}
```

## 6. Test Authentication

After setting up Firebase and updating your environment variables:

1. Restart your Flask application
2. Try to create a new account using the signup page
3. Test logging in with the created account
4. Verify in Firebase Console that new users appear in the Authentication section

## 7. Account Migration (For Existing Users)

Existing users will be prompted to migrate their accounts the next time they log in. This process:

1. Creates a new Firebase user with their email and password
2. Links their existing database records to the Firebase UID
3. Provides enhanced security features like password reset

## Security Best Practices

1. Store your Firebase configuration in environment variables, never in version control
2. Keep your Service Account key secure and never expose it publicly
3. Set up Firebase Security Rules to protect your data
4. Enable Email Verification for new users
5. Consider implementing rate limiting for authentication attempts
6. Regularly monitor your Firebase Console for unusual authentication activity 