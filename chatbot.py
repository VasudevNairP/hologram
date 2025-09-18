import google.generativeai as genai # pyright: ignore[reportMissingImports]

GOOGLE_API_KEY = "Your api key"
MODEL_NAME = "gemini-1.5-flash"
system_instruction = "You are a helpful and friendly AI assistant named Laila. Your goal is to provide accurate, concise, and useful information to the user's voice commands."

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
chat = model.start_chat(history=[])

def get_bot_response(command):
    response = chat.send_message(command)
    return response.text.strip()
