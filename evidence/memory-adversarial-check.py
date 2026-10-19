"""Independent audit: synthetic data, isolated SQLite, no provider or authentication."""
import os, tempfile, sqlite3
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import memory, evaluation as ev
from backend.app import app
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'REPLIQUE_DATA_DIR': tmp}), TestClient(app,base_url='http://127.0.0.1:8000') as client:
    headers={'X-Replique-Request':'1'}
    assert client.get('/api/memory/export',headers={'Sec-Fetch-Site':'same-site'}).status_code==403
    assert client.get('/api/memory',headers=headers).status_code==200
    assert not memory.db_path().exists()
    payload={'reply':"'; DROP TABLE items; --",'conversation':'x'*1450,'intent':'clarifier','rating':'positive','validated':True,'consent':True,'reviewed':True}
    ids=[]
    for i in range(3):
        response=client.post('/api/memory/items',json=payload,headers=headers)
        assert response.status_code==200,response.text
        ids.append(response.json()['id'])
    before=memory.select_context('clarifier','naturel','fr_neutre')
    with memory.transaction() as db:
        candidate=ev.create_version(db,{'max_examples':1,'max_context_chars':4500},ids)['id']
    after=memory.select_context('clarifier','naturel','fr_neutre')
    assert before==after,'Evaluation initialization changed builtin context'
    with memory.transaction() as db:
        dataset={'origin':'synthetic','purpose':'heldout_evaluation_only','cases':[{'id':'synthetic-audit','input':'Different synthetic input'}]}
        outputs={v:{'synthetic-audit':'Synthetic answer'} for v in ['builtin',candidate]}
        ratings={'reviewer':'SYNTHETIC CONTRACT FIXTURE','human_reviewed':True,'output_origin':'saved_model','scores':{v:{'synthetic-audit':dict.fromkeys(ev.DIMENSIONS,4)} for v in outputs},'generation_metadata':{v:{'model':'synthetic','prompt_hash':'synthetic','generated_at':'synthetic'} for v in outputs}}
        report=ev.evaluate(db,'builtin',candidate,dataset,outputs,ratings)
        ev.promote(db,candidate,report['id'],approved=True)
    selected=memory.select_context('clarifier','naturel','fr_neutre')
    assert len(selected['examples'])==1
    assert selected['revision']>after['revision']
    with memory.transaction() as db: ev.rollback(db,approved=True)
    rolled=memory.select_context('clarifier','naturel','fr_neutre')
    assert len(rolled['examples'])==3
    assert rolled['revision']>selected['revision']
    assert client.delete('/api/memory/items/'+ids[0],headers=headers).status_code==200
    with memory.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM eval_versions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM eval_runs').fetchone()[0]==0
        try: ev.get_version(db,candidate)
        except ValueError: pass
        else: raise AssertionError('Deleted version resurrected')
    assert client.delete('/api/memory',headers=headers).status_code==200
    with memory.transaction() as db:
        for table in ['items','profile','feedback','eval_versions','eval_runs','eval_history','eval_active']:
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0,table
    print('PASS: isolated no-create reads, same-site export block, SQL literal safety, builtin stability, real retrieval promotion/rollback + consent revision, source cascade, full derivative deletion.')
