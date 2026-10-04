"""Explorer polling cannot race the metadata update during project migration."""
from concurrent.futures import ThreadPoolExecutor
from workflows.coding_workspace import CodingWorkspace


def test_concurrent_catalog_reads_share_migration_metadata_lock(tmp_path):
    data=tmp_path/'data'
    legacy=CodingWorkspace(data)
    wid=legacy.create('Migration test')['workspace_id']
    legacy.write(wid,'notes.txt','Keep these exact bytes.')
    work=CodingWorkspace(data,project_root=tmp_path/'Documents'/'Projects')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:work.get(wid),range(64)))
    assert len({item['host_path'] for item in results})==1
    assert all(item['files']==[{'name':'notes.txt','bytes':23}] for item in results)
    assert work.read(wid,'notes.txt')['content']=='Keep these exact bytes.'
    assert len(list(work.project_root.iterdir()))==1
