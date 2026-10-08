import json
from flask import Blueprint, jsonify, request, Response, abort
from core.database import db_cursor, now

bp=Blueprint('project',__name__,url_prefix='/api/project')

def dump_project():
    tables=['characters','personas','conversations','messages','conversation_memories','character_memories','lorebook_entries','image_generations']
    out={'format':'newair-project','version':1,'exported_at':now(),'tables':{}}
    with db_cursor() as cur:
        for t in tables:
            cur.execute(f'SELECT * FROM {t}')
            out['tables'][t]=[dict(r) for r in cur.fetchall()]
    return out

@bp.get('/export')
def export_project():
    data=json.dumps(dump_project(),ensure_ascii=False,indent=2)
    return Response(data,mimetype='application/json',headers={'Content-Disposition':'attachment; filename=newair_project.json'})

@bp.get('/stats')
def stats():
    with db_cursor() as cur:
        result={}
        for t in ('characters','personas','conversations','messages','image_generations'):
            cur.execute(f'SELECT COUNT(*) AS n FROM {t}'); result[t]=cur.fetchone()['n']
    return jsonify(result)

@bp.post('/import')
def import_project():
    data=request.get_json(force=True) or {}
    if data.get('format')!='newair-project': abort(400,'not a newAIr project export')
    tables=data.get('tables') or {}
    with db_cursor() as cur:
        # Import only portable user-owned records. Existing IDs are retained when possible.
        for table in ('personas','characters'):
            for row in tables.get(table,[]):
                if table=='characters' and int(row.get('id',-1))==0: continue
                cols=[c for c in row if c not in ('id',)]
                vals=[row[c] for c in cols]
                cur.execute(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})',vals)
    return jsonify({'ok':True,'message':'Characters and personas imported. Conversations and generation history were left untouched to avoid ID collisions.'})
