from dotenv import load_dotenv
load_dotenv()
from app import app
from db.mongo import mongo
with app.app_context():
    ad = mongo.db.ads.find_one()
    print(ad)
