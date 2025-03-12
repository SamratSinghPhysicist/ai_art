#Generate Script for the given input title

from google import genai

# GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"

def generate_gemini(prompt, api_key_gemini):
    client = genai.Client(api_key=api_key_gemini)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents= prompt,
    )
    # title = response.text
    print(response.text)
    return response.text

# print(script_generator("2 Space facts I bet you didn't know!", False, "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"))