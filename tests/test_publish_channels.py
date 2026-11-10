"""Computed channels preserve immutable ancestry and catalogue atomicity."""

import numpy as np
import pyarrow as pa
import pytest
from terraworkbench_core.survey_store import SurveyStore


def project(tmp_path):
    src=tmp_path/'source.csv'
    src.write_text('x,y,value\n1,2,5\n2,3,6\n3,4,7\n')
    store=SurveyStore(tmp_path/'workspace',create=True)
    db=store.import_file(src)
    return store,db,src


def test_published_multi_channel_lineage_and_nulls(tmp_path):
    store,db,src=project(tmp_path)
    before=src.read_bytes()
    inputs={r['name']:r['version_id'] for r in store.channels(db) if r['name']=='value'}
    result=store.publish_channels(db,{'model':np.array([4.,np.nan,8.]),'sigma':np.ones(3)},
        units={'model':'nT','sigma':'nT'},inputs=inputs,
        provenance={'operation':'independent_calibration','engine':'test closed form'})
    assert result['rows']==3
    data=pa.Table.from_batches(list(store.batches(db,['model','sigma']))).to_pydict()
    assert data=={'model':[4.,None,8.],'sigma':[1.,1.,1.]}
    graph=store.channel_pipeline(db,'model')
    assert len(graph['edges'])==1
    assert graph['nodes'][graph['root']]['provenance']['inputs']==inputs
    assert src.read_bytes()==before


def test_bad_inputs_and_stale_versions_do_not_publish(tmp_path):
    store,db,_=project(tmp_path)
    inputs={r['name']:r['version_id'] for r in store.channels(db) if r['name']=='value'}
    for data in [np.zeros(2),np.array([1,np.inf,3])]:
        with pytest.raises(ValueError):
            store.publish_channels(db,{'new':data},units={'new':'nT'},inputs=inputs,provenance={'operation':'check'})
    with pytest.raises(ValueError,match='byte budget'):
        store.publish_channels(db,{'new':np.ones(3)},units={'new':'nT'},inputs=inputs,provenance={'operation':'check'},max_bytes=1)
    store.derive(db,'intermediate','c("value")+1')
    old={r['name']:r['version_id'] for r in store.channels(db) if r['name']=='intermediate'}
    store.derive(db,'intermediate','c("value")+2')
    with pytest.raises(ValueError,match='versions changed'):
        store.publish_channels(db,{'new':np.ones(3)},units={'new':'nT'},inputs=old,provenance={'operation':'check'})
    assert 'new' not in {r['name'] for r in store.channels(db)}


def test_catalogue_failure_rolls_back_all_output_channels(tmp_path,monkeypatch):
    store,db,_=project(tmp_path)
    initial={r['name'] for r in store.channels(db)}
    inputs={r['name']:r['version_id'] for r in store.channels(db) if r['name']=='value'}
    def fail(*args):raise RuntimeError('injected catalogue failure')
    monkeypatch.setattr(store,'_event',fail)
    with pytest.raises(RuntimeError,match='injected'):
        store.publish_channels(db,{'a':np.ones(3),'b':np.ones(3)},units={'a':'','b':''},
                               inputs=inputs,provenance={'operation':'check'})
    assert {r['name'] for r in store.channels(db)}==initial
    assert len(list((store.root/'databases'/db).glob('*.parquet')))==1
