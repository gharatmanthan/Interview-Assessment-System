import sqlite3
conn = sqlite3.connect('data/app.db')
c = conn.cursor()
c.execute("SELECT job_id, title, is_active FROM job_postings WHERE job_id = '28d92b1c5ce4445aa2913dcd7d8db3f1'")
print(c.fetchall())
conn.close()