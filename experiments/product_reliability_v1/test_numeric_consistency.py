import copy
import importlib.util
import os
from pathlib import Path

import pytest

if os.environ.get('PRODUCT_REPAIR_CANDIDATE') == '1':
    spec = importlib.util.spec_from_file_location('candidate_tables', Path(__file__).with_name('candidate_tables.py'))
    tables = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tables)
else:
    from rag import tables


@pytest.mark.parametrize('scores', [[24, 30], ['24', '30'], [' 24.0 ', 30]])
def test_numeric_representation_does_not_change_comparison(scores):
    table = {'name': 'Measurements', 'columns': ['ID', 'Score'], 'records': [
        {'ID': 'ITEM001', 'Score': scores[0]}, {'ID': 'ITEM002', 'Score': scores[1]}]}
    before = copy.deepcopy(table)
    plan = tables.bind_selection_request({'operation': 'select', 'columns': table['columns'],
        'filters': [{'column': 'ID', 'operator': 'in', 'value': ['ITEM001', 'ITEM002']}]}, table,
        'Compare ITEM001 and ITEM002; 25 is the pass mark.')
    result = tables.execute_query(table, plan)
    assert result['comparison']['field_maxima'] == [{'column': 'Score', 'maximum': 30, 'identities': ['ITEM002']}]
    assert result['comparison']['pass_counts'] == [
        {'identity': 'ITEM001', 'passed': 0, 'assessments': 1},
        {'identity': 'ITEM002', 'passed': 1, 'assessments': 1}]
    assert table == before


@pytest.mark.parametrize('value', ['Infinity', float('inf'), True])
def test_nonfinite_and_boolean_values_are_not_numeric_scores(value):
    table = {'name': 'Measurements', 'columns': ['ID', 'Score'], 'records': [
        {'ID': 'ITEM001', 'Score': value}, {'ID': 'ITEM002', 'Score': 30}]}
    result = tables.execute_query(table, {'operation': 'count', 'columns': [],
        'filters': [{'column': 'Score', 'operator': 'gte', 'value': 0}]})
    assert result['value'] == 1
