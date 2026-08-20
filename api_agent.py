from flask import request, jsonify
from agent import PropIntelAgent

agent = PropIntelAgent()

def register_agent_routes(app):
    @app.post('/api/agent/missions')
    def create_mission():
        body=request.get_json(silent=True) or {}; objective=(body.get('objective') or '').strip()
        if not objective:return jsonify({'error':'objective is required'}),400
        return jsonify(agent.create_mission(objective))

    @app.post('/api/agent/missions/<mission_id>/plan')
    def plan_mission(mission_id):
        return jsonify({'mission_id':mission_id,'plan':agent.plan(mission_id)})

    @app.post('/api/agent/missions/<mission_id>/ingest')
    def ingest(mission_id):
        body=request.get_json(silent=True) or {}; props=body.get('properties') or []
        unique=agent.ingest(mission_id,props); ranked=agent.rank(mission_id,unique)
        return jsonify({'mission_id':mission_id,'raw_count':len(props),'unique_count':len(unique),'prospects':[{'score':s,'property':p} for s,p in ranked[:50]]})

    @app.post('/api/agent/missions/<mission_id>/decide')
    def decide(mission_id):
        return jsonify({'mission_id':mission_id,'decision':agent.decide_next(mission_id),'mission':agent.get_mission(mission_id)})

    @app.get('/api/agent/missions/<mission_id>')
    def mission(mission_id):
        m=agent.get_mission(mission_id)
        return jsonify(m) if m else (jsonify({'error':'not found'}),404)

    @app.get('/api/agent/missions/<mission_id>/events')
    def events(mission_id): return jsonify(agent.events(mission_id))

    return app
