FROM node:18 as build-stage

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

# Set up Vite with Tailwind CSS
RUN npm install -g vite
RUN npm install --save-dev tailwindcss postcss autoprefixer
RUN npx tailwindcss init -p

# Create a simple Vite config
RUN echo "import { defineConfig } from 'vite'; export default defineConfig({});" > vite.config.js

# Create a simple CSS file for Vite to process
RUN echo "@import './static/css/tailwind.css';" > style.css

# Build the CSS with Vite
RUN npx vite build --outDir dist

FROM python:3.11-slim

WORKDIR /app

# Copy built assets from the build stage
COPY --from=build-stage /app/dist/assets/*.css /app/static/css/styles.css

# Copy Python files and templates
COPY requirements.txt .
COPY *.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY test_assets/ ./test_assets/

# Create necessary directories
RUN mkdir -p images processed_images

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 8080

# Make sure your Dockerfile includes this line to load environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]