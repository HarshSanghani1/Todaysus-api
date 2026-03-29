from dotenv import load_dotenv
load_dotenv()
from app import app
from db.mongo import mongo
with app.app_context():
    horo = mongo.db.horoscopes.find_one()
    print(horo)
