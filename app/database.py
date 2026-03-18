import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Check your .env file.")

client = AsyncIOMotorClient(MONGO_URI)
db = client["lakshya_crm"]

clients_col       = db["clients"]
users_col         = db["users"]          # client login credentials
leads_col         = db["leads"]
conversations_col = db["conversations"]
appointments_col  = db["appointments"]