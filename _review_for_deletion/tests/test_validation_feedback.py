from router.validation_feedback import failure_fingerprint

def test_traceback_location_does_not_hide_repeated_actual_exception():
    first='Traceback:\n  File "/output/one.py", line 2\nTypeError: unsupported input'
    second='Traceback:\n  File "/output/two.py", line 9\nTypeError: unsupported input'
    assert failure_fingerprint(first)==failure_fingerprint(second)
    assert failure_fingerprint(second)!=failure_fingerprint('TypeError: missing input')

def test_observation_digest_does_not_hide_repeated_error():
    assert failure_fingerprint('Validation failed '+('a'*64)+': AssertionError')==failure_fingerprint('Validation failed '+('b'*64)+': AssertionError')
