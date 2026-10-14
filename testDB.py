from database import get_connection

print("Testing database connection...")

try:
    conn = get_connection()
    print("✅ DATABASE CONNECTION OK")
    print("Server:", conn.server_host)
    print("Database:", conn.database)
    conn.close()

except Exception as e:
    print("❌ DATABASE CONNECTION FAILED")
    print(type(e).__name__)
    print(e)