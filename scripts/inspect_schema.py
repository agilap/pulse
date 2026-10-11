import psycopg

conn = psycopg.connect("postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse")
cur = conn.cursor()

cur.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version")
print("--- migrations ---")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns WHERE table_name='monitors'
    ORDER BY ordinal_position
""")
print("--- monitors columns ---")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name='check_results'
    ORDER BY ordinal_position
""")
print("--- check_results columns ---")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT indexname, indexdef FROM pg_indexes
    WHERE tablename IN ('monitors','check_results')
    ORDER BY indexname
""")
print("--- indexes ---")
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
