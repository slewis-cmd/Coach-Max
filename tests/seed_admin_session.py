"""Seed a session token directly into mongo for the super admin and print it."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load env
from dotenv import load_dotenv
load_dotenv(Path('/app/backend/.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
SUPER_ADMIN_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', '').lower().strip()


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    user = await db.users.find_one({"email": SUPER_ADMIN_EMAIL})
    if not user:
        # create
        user_id = f"user_{uuid.uuid4().hex}"
        user = {
            "user_id": user_id,
            "email": SUPER_ADMIN_EMAIL,
            "name": "Super Admin",
            "role": "super_admin",
            "picture": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        # Make sure role is super_admin
        if user.get("role") != "super_admin":
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "super_admin"}})

    token = f"sess_{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "created_at": datetime.now(timezone.utc),
    })
    print(token)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
