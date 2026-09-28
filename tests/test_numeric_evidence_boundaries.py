import pytest
from rag.answer import _unsupported_numbers

@pytest.mark.parametrize('evidence,claim',[
    ('The office closes at 17:20.','It closes at 17:20 [S1].'),
    ('The monitor cost GBP 120.','The cost was GBP 120 [S1].'),
    ('The limit is 4.0.','The limit is 4.0 [S1].'),
])
def test_sentence_punctuation_is_not_part_of_numeric_evidence(evidence,claim):
    assert _unsupported_numbers(claim,[{'label':'S1','text':evidence}])==[]

@pytest.mark.parametrize('evidence,claim,unsupported',[
    ('The office closes at 17:20.','It closes at 17:21 [S1].',['21']),
    ('The monitor cost GBP 120.','The cost was GBP 121 [S1].',['121']),
    ('The limit is 4.0.','The limit is 4.1 [S1].',['4.1']),
    ('The limit is 4.05.','The limit is 4 [S1].',['4']),
    ('The limit is 4.05.','The limit is 4.0 [S1].',['4.0']),
])
def test_repair_does_not_accept_changed_or_partial_numbers(evidence,claim,unsupported):
    assert _unsupported_numbers(claim,[{'label':'S1','text':evidence}])==unsupported

def test_numbers_in_an_uncited_source_cannot_support_claim():
    sources=[{'label':'S1','text':'The price is 120.'},{'label':'S2','text':'The price is 121.'}]
    assert _unsupported_numbers('The price is 121 [S1].',sources)==['121']
