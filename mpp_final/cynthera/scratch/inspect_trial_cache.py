import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables:", tables)

for t in tables:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cursor.fetchone()[0]
        print(f"Table {t}: {cnt} rows")
    except Exception as e:
        print(f"Table {t}: {e}")

# Search for NCT02313909
cursor.execute("SELECT source_name, cache_key, length(response_json) FROM raw_response_cache WHERE response_json LIKE '%NCT02313909%'")
matches = cursor.fetchall()
print("Matches in raw_response_cache for NCT02313909:", len(matches))

if matches:
    cursor.execute("SELECT response_json FROM raw_response_cache WHERE cache_key = ?", (matches[0][1],))
    raw_str = cursor.fetchone()[0]
    data = json.loads(raw_str)
    # find NCT02313909 in studies
    for study in data.get("studies", []):
        proto = study.get("protocolSection", {})
        nct = proto.get("identificationModule", {}).get("nctId", "")
        if nct == "NCT02313909":
            print("\nFound NCT02313909!")
            print("Keys in protocolSection:", list(proto.keys()))
            print("identificationModule:", json.dumps(proto.get("identificationModule", {}), indent=2))
            print("statusModule:", json.dumps(proto.get("statusModule", {}), indent=2))
            print("designModule:", json.dumps(proto.get("designModule", {}), indent=2))
            print("armsInterventionsModule:", json.dumps(proto.get("armsInterventionsModule", {}), indent=2))
            break
