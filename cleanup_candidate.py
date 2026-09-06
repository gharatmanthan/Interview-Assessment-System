import sqlite3

conn = sqlite3.connect('D:/Majorrrr/interview-assessment-system/data/app.db')

# Delete the candidate with recruiter email (data issue)
candidate_id = '1788354239176'
conn.execute('DELETE FROM candidates WHERE candidate_id = ?', (candidate_id,))
conn.commit()

# Verify
cursor = conn.execute('SELECT candidate_id, email FROM candidates WHERE email = "atharvshigwan1142@gmail.com"')
print('Remaining candidates with recruiter email:', cursor.fetchall())

conn.close()
print('Cleaned up candidate with recruiter email')