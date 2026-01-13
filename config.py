# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")
VIEWS_DIR = os.path.join(BASE_DIR, "views")
MOBILE_VIEWS_DIR = os.path.join(BASE_DIR, "mobile_views")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIEWS_DIR, exist_ok=True)
os.makedirs(MOBILE_VIEWS_DIR, exist_ok=True)

MOBILE_URL = "http://192.168.0.30:8000/mobile"

DUMMY_IMAGE_PATH = os.path.join(IMAGE_DIR, "dummy.png")

DB_CONFIG = {
    "host": "localhost",
    "user": "wawi_user",
    "password": "poke",
    "database": "wawi_b7",
}
