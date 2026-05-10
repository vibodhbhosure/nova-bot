import sqlite3
import os

db_conn = sqlite3.connect('nova.db')
cursor = db_conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS sys_settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS webauthn_credentials (id BLOB PRIMARY KEY, public_key BLOB, sign_count INTEGER)''')
db_conn.commit()
