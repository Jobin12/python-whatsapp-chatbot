import google.generativeai as genai
from flask import current_app
import logging

def generate_response(message_body):
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        logging.error("GEMINI_API_KEY not found in configuration")
        return "Sorry, I am not configured correctly (missing API key)."

    try:
        genai.configure(api_key=api_key)
        # Using the model name as requested by the user
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        response = model.generate_content(message_body)
        return response.text
    except Exception as e:
        logging.error(f"Error generating response from Gemini: {e}")
        return "I'm having trouble thinking right now. Please try again later."
