FROM node:18 as build-stage

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

# Create a simple tailwind config if it doesn't exist
RUN if [ ! -f tailwind.config.js ]; then echo "export default { content: ['./templates/**/*.html'], theme: { extend: {} }, plugins: [] };" > tailwind.config.js; fi

# Create a simple postcss config if it doesn't exist
RUN if [ ! -f postcss.config.js ]; then echo "export default { plugins: { tailwindcss: {}, autoprefixer: {} } };" > postcss.config.js; fi

# Build the CSS directly with tailwindcss CLI
RUN npx tailwindcss -i ./static/css/tailwind.css -o ./static/css/styles.css --minify

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy built assets from the build stage
COPY --from=build-stage /app/static/css/styles.css /app/static/css/styles.css

# Copy Python files and templates
COPY requirements.txt .
COPY *.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY test_assets/ ./test_assets/

# Create directories for images
RUN mkdir -p images processed_images logs

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 8080

# Make sure your Dockerfile includes this line to load environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]