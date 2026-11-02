# نتائج الاختبارات — review-003

```
$ ruff check .
All checks passed!

$ python -m pytest -o addopts="" -q -rs
...................................                                      [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/test_integration_real_sources.py:38: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:50: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:59: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:67: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:75: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
246 passed, 5 skipped in 4.73s

$ AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -o addopts="" -q
.....                                                                    [100%]
5 passed in 52.46s
```

سبب تخطي الاختبارات الخمسة: تحتاج AUTODOCTOR_INTEGRATION=1 ومصادر منزّلة؛ شُغّلت بهذا الشرط ونجحت الخمسة، فالتغطية الكلية 251 اختبارًا بلا فشل.
