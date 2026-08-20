import os, json, sqlite3, uuid
from datetime import datetime

DB_PATH = os.getenv('PROPINTEL_DB', 'propintel.db')

class PropIntelAgent:
    """Mission engine. External actions are adapters; no hidden sending is performed."""
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _db(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        db=self._db(); c=db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS missions (
          id TEXT PRIMARY KEY, objective TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, state TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS agent_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL,
          event TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS prospects (
          id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, property_data TEXT NOT NULL,
          score INTEGER NOT NULL, status TEXT NOT NULL, next_action TEXT, updated_at TEXT NOT NULL)''')
        db.commit(); db.close()

    def _event(self, mission_id, event, payload=None):
        db=self._db(); db.execute('INSERT INTO agent_events(mission_id,event,payload,created_at) VALUES(?,?,?,?)',
            (mission_id,event,json.dumps(payload or {},ensure_ascii=False),datetime.utcnow().isoformat())); db.commit(); db.close()

    def create_mission(self, objective):
        mid=str(uuid.uuid4()); now=datetime.utcnow().isoformat()
        state={'step':'plan','target':self._infer_target(objective),'completed_actions':0,'meetings':0}
        db=self._db(); db.execute('INSERT INTO missions VALUES(?,?,?,?,?,?)',(mid,objective,'running',now,now,json.dumps(state))); db.commit(); db.close()
        self._event(mid,'mission.created',{'objective':objective}); return self.get_mission(mid)

    def _infer_target(self, objective):
        import re
        m=re.search(r'(\d+)\s*(?:rendez[- ]?vous|rdv|mandat)', objective.lower())
        return int(m.group(1)) if m else 3

    def plan(self, mission_id):
        plan=['collect','deduplicate','analyze_market','detect_sellers','rank','act','observe','decide_next']
        self._event(mission_id,'plan.created',{'steps':plan})
        self._set_state(mission_id,'collect'); return plan

    def _set_state(self, mission_id, step, **extra):
        db=self._db(); row=db.execute('SELECT state FROM missions WHERE id=?',(mission_id,)).fetchone()
        state=json.loads(row[0]); state.update(extra); state['step']=step
        db.execute('UPDATE missions SET state=?,updated_at=? WHERE id=?',(json.dumps(state),datetime.utcnow().isoformat(),mission_id)); db.commit(); db.close()
        self._event(mission_id,'state.changed',state)

    def ingest(self, mission_id, properties):
        self._set_state(mission_id,'deduplicate',raw_count=len(properties))
        seen=set(); unique=[]
        for p in properties:
            key=(str(p.get('district','')).strip().lower(),str(p.get('surface','')).strip(),str(p.get('price','')).strip())
            if key in seen: continue
            seen.add(key); unique.append(p)
        self._set_state(mission_id,'analyze_market',unique_count=len(unique)); return unique

    def score(self, p):
        try: price=float(p.get('price',0)); area=float(p.get('surface',0)); ppm=price/area if area else 999999
        except: ppm=999999
        s=35
        if ppm<10000:s+=25
        elif ppm<13000:s+=18
        elif ppm<16000:s+=10
        yes=lambda x:str(x).lower() in ('oui','yes','true','1')
        if yes(p.get('garage')):s+=7
        if yes(p.get('elevator')):s+=5
        if yes(p.get('terrace')):s+=5
        if str(p.get('seller_type','')).lower() in ('particulier','private','particulier probable'):s+=13
        if yes(p.get('price_drop')):s+=10
        return min(100,s)

    def rank(self, mission_id, properties):
        ranked=sorted([(self.score(p),p) for p in properties], key=lambda x:x[0], reverse=True)
        db=self._db()
        for score,p in ranked:
            pid=str(uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(p,sort_keys=True,ensure_ascii=False)))
            action='qualify_seller' if score>=75 else 'watch'
            db.execute('INSERT OR REPLACE INTO prospects VALUES(?,?,?,?,?,?,?)',
              (pid,mission_id,json.dumps(p,ensure_ascii=False),score,'queued',action,datetime.utcnow().isoformat()))
        db.commit(); db.close(); self._set_state(mission_id,'act',prospects=len(ranked)); self._event(mission_id,'prospects.ranked',{'count':len(ranked)}); return ranked

    def decide_next(self, mission_id):
        m=self.get_mission(mission_id); state=m['state']; target=state.get('target',3); meetings=state.get('meetings',0)
        decision='continue_prospecting' if meetings<target else 'close_mission'
        self._set_state(mission_id,'decide_next',decision=decision)
        if decision=='close_mission':
            db=self._db(); db.execute('UPDATE missions SET status="completed",updated_at=? WHERE id=?',(datetime.utcnow().isoformat(),mission_id)); db.commit(); db.close()
        self._event(mission_id,'decision',{'decision':decision,'meetings':meetings,'target':target}); return decision

    def get_mission(self, mission_id):
        db=self._db(); row=db.execute('SELECT * FROM missions WHERE id=?',(mission_id,)).fetchone(); db.close()
        if not row:return None
        return {'id':row[0],'objective':row[1],'status':row[2],'created_at':row[3],'updated_at':row[4],'state':json.loads(row[5])}

    def events(self, mission_id):
        db=self._db(); rows=db.execute('SELECT event,payload,created_at FROM agent_events WHERE mission_id=? ORDER BY id DESC',(mission_id,)).fetchall(); db.close()
        return [{'event':r[0],'payload':json.loads(r[1] or '{}'),'created_at':r[2]} for r in rows]
