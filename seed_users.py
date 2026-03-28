from app import app
from db.mongo import mongo
from werkzeug.security import generate_password_hash

admins = [
    {"username": "Harsh", "password": "H@rsh@wif", "role": "admin"},
    {"username": "Harshil", "password": "H@rshil@wif", "role": "admin"}
]

with app.app_context():
    # Remove existing to avoid duplicates if re-run
    mongo.db.users.delete_many({"username": {"$in": ["Harsh", "Harshil"]}})
    
    for admin in admins:
        hashed_pw = generate_password_hash(admin["password"])
        mongo.db.users.insert_one({
            "username": admin["username"],
            "password": hashed_pw,
            "role": admin["role"]
        })
        print(f"User {admin['username']} created successfully!")

print("Done sealing users.")
