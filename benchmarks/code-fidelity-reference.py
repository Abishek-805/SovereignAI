"""Independent positive controls, never included in evaluated-model context."""
def bodies():
 return {
 'ledger':'''    if any(type(x) is not int for x in entries): raise TypeError()
    return sum(entries)''',
 'ranges':'''    result=[]
    for a,b in sorted(intervals):
        if a>b: raise ValueError()
        if result and a<=result[-1][1]: result[-1]=(result[-1][0],max(b,result[-1][1]))
        else: result.append((a,b))
    return result''',
 'paths':'''    from collections.abc import Mapping
    value=data
    for key in path:
        if not isinstance(value,Mapping): raise TypeError()
        value=value[key]
    return value''',
 'csvrows':'''    import csv,io
    rows=list(csv.reader(io.StringIO(text)))
    if len(rows)>1: raise ValueError()
    return rows[0] if rows else []''',
 'money':'''    if count<=0 or total<0: raise ValueError()
    base,extra=divmod(total,count)
    return [base+(i<extra) for i in range(count)]''',
 'topology':'''    pending={k:set(v) for k,v in dependencies.items()}
    for node in set().union(set(pending),*(pending.values())): pending.setdefault(node,set())
    result=[]
    while pending:
        ready=sorted(k for k,v in pending.items() if not v)
        if not ready: raise ValueError()
        node=ready[0];result.append(node);del pending[node]
        for values in pending.values(): values.discard(node)
    return result''',
 'inventory':'''    result=dict(stock)
    for key,n in requests.items():
        if key not in result: raise KeyError(key)
        if type(n) is not int: raise TypeError()
        if n<0 or n>result[key]: raise ValueError()
        result[key]-=n
    return result''',
 'escaping':'''    mapping={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',chr(39):'&#x27;'}
    return ''.join(mapping.get(c,c) for c in text)''',
 'pagination':'''    if number<1 or size<1: raise ValueError()
    return list(items[(number-1)*size:number*size])''',
 'versions':'''    def parse(value):
        parts=value.split('.')
        if any(not p or not p.isascii() or not p.isdecimal() for p in parts): raise ValueError()
        out=[int(p) for p in parts]
        while out and out[-1]==0: out.pop()
        return out
    a,b=parse(left),parse(right)
    return (a>b)-(a<b)''',
 'rle':'''    result=[]
    for value,count in runs:
        if type(count) is not int: raise TypeError()
        if count<0: raise ValueError()
        result.extend([value]*count)
    return result''',
 'dedup':'''    seen=set();result=[]
    for record in records:
        value=record[key]
        if value not in seen: seen.add(value);result.append(record)
    return result''',
 'dates':'''    import datetime,re
    def parse(value):
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value): raise ValueError()
        return datetime.date.fromisoformat(value)
    return (parse(end)-parse(start)).days''',
 'polynomial':'''    result=0
    for coefficient in coefficients: result=result*x+coefficient
    return result''',
 'histogram':'''    from collections import Counter
    return dict(Counter(w for token in text.casefold().split() if (w:=token.strip('.,!?;:'))))''',
 'queues':'''    pending=[iter(s) for s in sequences];result=[]
    while pending:
        active=[]
        for source in pending:
            try: result.append(next(source));active.append(source)
            except StopIteration: pass
        pending=active
    return result''',
 'statistics':'''    if not values: raise ValueError()
    ordered=sorted(values);n=len(ordered);mid=n//2
    return ordered[mid] if n%2 else (ordered[mid-1]+ordered[mid])/2''',
 'transitions':'''    result=dict(state)
    for key,delta in events:
        value=result.get(key,0)+delta
        if value<0: raise ValueError()
        result[key]=value
    return result''',
 'network':'''    seen=set();pending=[start]
    while pending:
        node=pending.pop()
        if node in seen: continue
        seen.add(node);pending.extend(edges.get(node,()))
    return sorted(seen)''',
 'formatting':'''    def escape(value):
        return value.replace(chr(92),chr(92)*2).replace('|',chr(92)+'|').replace(chr(10),chr(92)+'n')
    return chr(10).join('|'.join(map(escape,row)) for row in rows)''',
 }

def files(case):
 result=dict(case['context']['initial_files'])
 name=case['id'];path=name+'.py'
 result[path]=result[path].replace('    raise NotImplementedError',bodies()[name])
 symbol=case['required_symbols'][path][0]
 signature=result['service.py'].split('def run(',1)[1].split('):',1)[0]
 result['service.py']=result['service.py'].replace('    raise NotImplementedError',f'    return {symbol}({signature})')
 return result
