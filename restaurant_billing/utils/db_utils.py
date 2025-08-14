import sqlite3 as s
import os
import pandas as pd

def create_folders():
    os.makedirs("db", exist_ok=True)

def initialize_database():
    conn = s.connect("db/restaurant.db")
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            category TEXT,
            price REAL NOT NULL,
            gst REAL DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            mode TEXT,
            payment_method TEXT,
            subtotal REAL,
            gst REAL,
            discount REAL,
            total REAL,
            timestamp TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            item_name TEXT,
            quantity INTEGER,
            price REAL,
            gst REAL DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()

def load_menu_from_csv(csv_path="data/menu.csv"):
    conn = s.connect("db/restaurant.db")
    cursor = conn.cursor()
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        cursor.execute('''
            INSERT OR IGNORE INTO menu (item_name, category, price, gst)
            VALUES (?, ?, ?, ?)
        ''', (row['item_name'], row['category'], row['price'], row['gst']))
    conn.commit()
    conn.close()

def fetch_menu_items():
    conn = s.connect("db/restaurant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price, gst FROM menu")
    items = cursor.fetchall()
    conn.close()
    return items
