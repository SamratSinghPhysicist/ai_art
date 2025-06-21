from googletrans import Translator

def translate_to_english(text):
    """
    Translates a given text to English.

    Args:
        text (str): The text to be translated.

    Returns:
        str: The translated text in English.
    """
    try:
        # Initialize the translator
        translator = Translator()
        
        # Translate the text
        # The `dest` parameter specifies the destination language
        translation = translator.translate(text, dest="en")
        
        return translation.text
    except Exception as e:
        return f"An error occurred during translation: {e}"

if __name__ == '__main__':
    # Example usage of the translator
    
    # --- Test with a Spanish sentence ---
    spanish_text = "Hola, ¿cómo estás?"
    translated_text_spanish = translate_to_english(spanish_text)
    print(f"Original (Spanish): {spanish_text}")
    print(f"Translated to English: {translated_text_spanish}")
    print("-" * 20)

    # --- Test with a French sentence ---
    french_text = "Bonjour, comment ça va ?"
    translated_text_french = translate_to_english(french_text)
    print(f"Original (French): {french_text}")
    print(f"Translated to English: {translated_text_french}")
    print("-" * 20)

    # --- Test with a German sentence ---
    german_text = "Guten Tag, wie geht es Ihnen?"
    translated_text_german = translate_to_english(german_text)
    print(f"Original (German): {german_text}")
    print(f"Translated to English: {translated_text_german}")
    print("-" * 20)

    # --- Test with an English sentence (should remain the same) ---
    english_text = "Hello, how are you?"
    translated_text_english = translate_to_english(english_text)
    print(f"Original (English): {english_text}")
    print(f"Translated to English: {translated_text_english}")
    print("-" * 20)

    # --- Test with a user-provided sentence ---
    try:
        user_input = input("Enter a sentence in any language to translate to English: ")
        translated_user_input = translate_to_english(user_input)
        print(f"Original (User Input): {user_input}")
        print(f"Translated to English: {translated_user_input}")
    except KeyboardInterrupt:
        print("\nTranslation cancelled by user.")
