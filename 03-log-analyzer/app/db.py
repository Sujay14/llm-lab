import sqlite3,json
from app.config import DB
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 with conn() as c:
  c.execute("CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,filename TEXT,source TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,result TEXT,logs TEXT)")
def save(filename,source,result,logs):
 with conn() as c:
  cur=c.execute("INSERT INTO incidents(filename,source,result,logs) VALUES(?,?,?,?)",(filename,source,json.dumps(result),logs[:500000]))
  return cur.lastrowid
def get(i):
 with conn() as c: r=c.execute("SELECT * FROM incidents WHERE id=?",(i,)).fetchone()
 return dict(r) if r else None
def all():
 with conn() as c: return [dict(x) for x in c.execute("SELECT id,filename,source,created FROM incidents ORDER BY id DESC LIMIT 50")]
