# نتائج الاختبارات — review-003 (تقوية اختبار المطابقة + توحيد الوثائق)

مخرجات حقيقية من هذه الجولة، منسوخة كما ظهرت. لا أرقام مقدّرة.

```
$ ruff check .
All checks passed!

$ python -m pytest -o addopts="" -q -rs
SKIPPED [1] tests/test_integration_real_sources.py:38: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:50: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:59: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:67: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
SKIPPED [1] tests/test_integration_real_sources.py:75: set AUTODOCTOR_INTEGRATION=1 (and fetch the sources) to run
259 passed, 5 skipped in 26.76s

$ AUTODOCTOR_INTEGRATION=1 python -m pytest tests/test_integration_real_sources.py -o addopts="" -q
5 passed in 69.49s (0:01:09)

$ python verify_delivery.py .
16 file(s) hashed, 0 problem(s)
```

سبب تخطي الاختبارات الخمسة أعلاه: تحتاج `AUTODOCTOR_INTEGRATION=1` ومصادر منزّلة.
شُغّلت بهذا الشرط في السطر التالي لها، ونجحت الخمسة (69.49 ثانية). أي أن المجموع الفعلي
**264 اختبارًا: 259 + 5، صفر فشل، صفر خطأ**.

## ما أُضيف في هذه الجولة

### 1) `tests/test_classification_parity.py` — أُعيدت كتابته (7 اختبارات)

| # | الاختبار | ما يمنعه |
| --- | --- | --- |
| 1 | `test_parity_between_pack_and_export_by_context_key` | أي اختلاف بين الحزمة والتصدير، والمقارنة على `context_key` لا على `code` |
| 2 | `test_comparator_catches_a_lost_diagnostic_quote` | أن يمرّ فقدان اقتباس تشخيصي حقيقي بصمت (اختبار سلبي: المقارنة يجب أن تفشل) |
| 3 | `test_display_cap_is_reported` | أن يُقصّ العرض بلا إبلاغ: 6 جمل ⇒ 5 معروضة، الإجمالي 6، `quotes_truncated: true` |
| 4 | `test_monitoring_sentence_is_not_a_quoted_check` | إدراج «Ford checks plausibility…» تحت `quoted_checks` |
| 5 | `test_real_check_sentence_is_a_quoted_check` | العكس: أن يُفقد فحص حقيقي |
| 6 | `test_every_quote_carries_a_category` | اقتباس بلا تصنيف أو بقاعدة تصنيف فارغة |
| 7 | `test_classification_helper_is_shared` | تفرّع قواعد التصنيف بين مسارين |

جوهر المقارنة: تُؤخذ الفحوص المتوقعة من التصدير كاملة، ثم تُقارن بالقائمة المعروضة
`expected[:5]` (لا `got ⊆ expected`)، ويُتحقق من `diagnostic_quotes_total` و
`quotes_truncated`، وتُقارن فئات `other_quotes` نصًّا بفئة.

### 2) `tests/test_review_docs_consistency.py` — جديد (6 اختبارات)

يقرأ ملفات الحزمة نفسها ويقارنها بما تدّعيه الوثائق:

- مجاميع README وفئات الاقتباسات = `summary` التصدير المضغوط.
- أعداد الحزمة (كود/اقتباس، المسوّدات) = `summary` الحزمة، ولا اقتباس غير تشخيصي داخل
  `quoted_checks` في الحزمة المسلّمة.
- `TEST_RESULTS.md` و`BEFORE_AFTER.md` مذكوران **مرة واحدة** في جدول الملفات.
- كل ملف يذكره الجدول موجود فعلًا في الحزمة.
- عمود «بعد» في `BEFORE_AFTER.md` = أعداد التصدير الحالية.
- نسخة `docs/REVIEW_003_NOTES.md` مطابقة بايتًا ببايت لـ `README.md` في الحزمة

هذا الاختبار كان سيفشل على الحزمة السابقة: `README.md` كان يقول 5,930 اقتباسًا بينما
التصدير يقول 5,981، وكان `TEST_RESULTS.md` مكرّرًا في الجدول.
