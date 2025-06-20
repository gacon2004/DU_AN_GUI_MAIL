import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

def get_connection():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        port=int(os.getenv("DB_PORT")),  # Thêm dòng này
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    return conn
# mysql://root:kjsdziATJUhZtuGpJlYCInSGmkCmJvks@switchback.proxy.rlwy.net:10072/railway