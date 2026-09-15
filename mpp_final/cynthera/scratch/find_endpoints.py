import sqlite3

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT DISTINCT endpoint FROM raw_response_cache WHERE endpoint LIKE '%CHEMBL682%'")
for row in c.fetchall():
    print("Endpoint:", row[0])

c.execute("SELECT DISTINCT endpoint FROM raw_response_cache WHERE endpoint LIKE '%indication%'")
for row in c.fetchall():
    print("Indication endpoint:", row[0])
