FROM node:18 as build-stage

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Install tailwindcss CLI globally to ensure it's available
RUN npm install -g tailwindcss postcss autoprefixer
# Run the build:css command explicitly
RUN npm tailwindcss -i ./static/css/tailwind.css -o ./static/css/styles.css

FROM python:3.11-slim

WORKDIR /app

# Copy built assets from the build stage
COPY --from=build-stage /app/static/css/styles.css /app/static/css/styles.css

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

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]

# Make sure your Dockerfile includes this line to load environment variables
ENV PYTHONUNBUFFERED=1