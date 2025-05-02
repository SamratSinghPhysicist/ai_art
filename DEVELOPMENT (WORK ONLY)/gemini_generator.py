#Generate Script for the given input title

from google import genai
import traceback

# GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"

def generate_gemini(prompt, api_key_gemini):
    try:
        # Initialize the Gemini client with the API key
        client = genai.Client(api_key=api_key_gemini)
        
        # Call the Gemini API to generate content
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        
        # Check if we got a valid response
        if hasattr(response, 'text'):
            return response.text
        else:
            # If response doesn't have text attribute, try to extract content in a different way
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                if hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts'):
                    return str(response.candidates[0].content.parts[0].text)
            
            # If we couldn't extract the content, return a fallback message
            print("Warning: Could not extract text from Gemini response")
            return "I was unable to enhance the prompt. Please try again with a different description."
            
    except Exception as e:
        print(f"Error in generate_gemini: {str(e)}")
        print(traceback.format_exc())
        return "An error occurred while enhancing the prompt. Please try again."

# print(script_generator("2 Space facts I bet you didn't know!", False, "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"))