"""Separate realistic three-module parcel-manifest integration task."""
def tasks():
 files={
 'shipping.py':'def validate_items(items: list) -> None:\n    raise NotImplementedError\n\ndef quote(items: list, rates: dict) -> dict:\n    raise NotImplementedError\n\ndef price_unit() -> str:\n    return "cents"\n',
 'presentation.py':'def render_quote(summary: dict) -> str:\n    raise NotImplementedError\n\ndef format_version() -> int:\n    return 3\n',
 'manifest.py':'import shipping\nimport presentation\n\ndef build_manifest(items: list, rates: dict) -> str:\n    raise NotImplementedError\n',
 'protected.py':'def retained():\n    return "protected-d"\n'}
 requirements=[
 'Items are mappings with sku and quantity. validate_items rejects non-int quantity including bool with TypeError, quantity <= 0 with ValueError, and missing sku/quantity with KeyError. Return None on valid input.',
 'quote must call validate_items once, then sum quantity * integer cent rate per sku. Missing rate raises KeyError, never returns an exception object. Return a fresh mapping containing units and total_cents; never mutate items or rates.',
 'render_quote returns exactly units=<units>; total_cents=<total_cents> with no newline. build_manifest must call shipping.quote and presentation.render_quote once each, returning that string.',
 'Preserve all existing signatures, annotations, price_unit() == "cents", and format_version() == 3. Only shipping.py, presentation.py, manifest.py may change; protected.py must stay byte-identical.']
 reference=dict(files)
 reference['shipping.py']='''def validate_items(items: list) -> None:
    for item in items:
        item['sku']; quantity=item['quantity']
        if type(quantity) is not int: raise TypeError()
        if quantity <= 0: raise ValueError()

def quote(items: list, rates: dict) -> dict:
    validate_items(items)
    return {'units':sum(item['quantity'] for item in items),'total_cents':sum(item['quantity']*rates[item['sku']] for item in items)}

def price_unit() -> str:
    return 'cents'
'''
 reference['presentation.py']='''def render_quote(summary: dict) -> str:
    return f"units={summary['units']}; total_cents={summary['total_cents']}"

def format_version() -> int:
    return 3
'''
 reference['manifest.py']=files['manifest.py'].replace('    raise NotImplementedError','    return presentation.render_quote(shipping.quote(items,rates))')
 oracle='''import shipping,presentation,manifest,inspect,copy
def raises(kind,call):
 try:call()
 except kind:return
 raise AssertionError('required exception absent')
items=[{'sku':'alpha','quantity':2},{'sku':'beta','quantity':1}];rates={'alpha':75,'beta':20}
before=copy.deepcopy((items,rates))
assert manifest.build_manifest(items,rates)=='units=3; total_cents=170'
assert (items,rates)==before
raises(TypeError,lambda:shipping.quote([{'sku':'alpha','quantity':True}],rates))
raises(ValueError,lambda:shipping.quote([{'sku':'alpha','quantity':0}],rates))
raises(KeyError,lambda:shipping.quote([{'sku':'unknown','quantity':1}],rates))
raises(KeyError,lambda:shipping.validate_items([{'sku':'alpha'}]))
assert shipping.price_unit()=='cents' and presentation.format_version()==3
assert str(inspect.signature(shipping.quote))=='(items: list, rates: dict) -> dict'
assert str(inspect.signature(manifest.build_manifest))=='(items: list, rates: dict) -> str'
called=[]
shipping.quote=lambda *a: called.append('quote') or {'units':9,'total_cents':8}
presentation.render_quote=lambda s: called.append('render') or 'forwarded'
assert manifest.build_manifest(items,rates)=='forwarded' and called==['quote','render']
'''
 return [{'id':'parcel_manifest_integration','category':'complex_contract','complexity':'complex','request':'Finish the selected parcel manifest project using its existing annotated interfaces. '+' '.join(requirements),'requirements':requirements,'allowed_change_paths':['shipping.py','presentation.py','manifest.py'],'context':{'initial_files':files,'active_file':'manifest.py'},'required_symbols':{'shipping.py':['validate_items','quote','price_unit'],'presentation.py':['render_quote','format_version'],'manifest.py':['build_manifest'],'protected.py':['retained']},'oracle':{'kind':'trusted_tests','trusted_files':{'check.py':oracle},'command':['python','check.py'],'expected_exit_code':0},'private_reference':reference}]
