"""Bounded model-authored deliverable contract, carried by the existing plan."""
def validate_contract(contract):
    # Old cached plans and direct literal edits predate this optional envelope.
    if contract is None:return None
    if not isinstance(contract,dict) or set(contract)!={'deliverable','requirements','entrypoint'}:
        raise ValueError('Invalid request contract')
    requirements=contract['requirements']
    if (contract['deliverable'] not in {'application','library','document','edit'} or
        not isinstance(requirements,list) or not 1<=len(requirements)<=12 or
        any(not isinstance(item,str) or not item.strip() or len(item)>400 for item in requirements) or
        not isinstance(contract['entrypoint'],str) or len(contract['entrypoint'])>240 or
        (contract['deliverable']=='application' and not contract['entrypoint'].strip())):
        raise ValueError('Incomplete or oversized request contract')
    return {'deliverable':contract['deliverable'],'requirements':list(requirements),'entrypoint':contract['entrypoint']}
