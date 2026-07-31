import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY").strip()  # Strip whitespace to avoid issues with accidental spaces/newlines

if not api_key:
    print("❌ API Key not found in .env file")
else:
    client = OpenAI(api_key=api_key)
    try:
        client.models.list()
        print("✅ API Key is WORKING")
    except Exception as e:
        print("❌ Error:", e)