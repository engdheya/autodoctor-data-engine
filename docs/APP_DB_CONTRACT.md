# عقد قاعدة البيانات بين AutoDoctor Data Engine وتطبيق Flutter

هذا الملف هو المرجع الوحيد الذي يُبنى عليه `data/database/` في تطبيق Flutter.
كل استعلام هنا مُشغَّل ومقيس على الملف الحقيقي، ولا يُفترض أي اسم جدول أو عمود.

## 1. الملف

| البند | القيمة |
| --- | --- |
| اسم الملف | `autodoctor-app-0.9.1-public.sqlite` |
| الحجم | 65,884,160 بايت |
| SHA‑256 | `4741b4c6ac385c9f90e39cdf4c5e3fa89f8ba879ed88a5b998721c41237df98c` |
| إصدار القاعدة | `0.9.1` (من `db_versions.version`) |
| إصدار المخطط | `4` (من `db_versions.schema_version`) |
| `integrity_check` | `ok` |
| `foreign_key_check` | 0 مخالفة |
| Views | 16 |

يُفتح **للقراءة فقط** (`OpenDatabaseOptions(readOnly: true)`)، ويُتحقق من SHA‑256 قبل أول فتح.
بيانات المستخدم في ملف منفصل تمامًا (`autodoctor_user.db`).

## 2. الجداول التي يقرأها التطبيق

| الجدول | الصفوف | الاستخدام |
| --- | --- | --- |
| `dtc_codes` | 19,089 | الهوية (`context_key`)، النوع، الشركة، التصنيف |
| `dtc_definitions` | 37,871 | العنوان/الوصف (`language='en' AND is_canonical=1`) |
| `dtc_causes` / `dtc_cause_texts` | 28,456 / 56,912 | الأسباب المحتملة |
| `dtc_symptoms` / `dtc_symptom_texts` | 26,454 / 52,908 | الأعراض |
| `dtc_repairs` | 9,533 | تقديرات الإصلاح (بلا نص) |
| `dtc_related_codes` | 32,934 | الأكواد المرتبطة |
| `dtc_evidence_sources` | 33,221 | المصادر والمراجع |
| `dtc_flags` | 9,533 | MIL، الانبعاثات، limp mode، الخطورة |
| `conflicts` | 393 | «المصادر تختلف» — كلها `needs_review` |
| `manufacturers` | 33 | قائمة الشركات في Garage |
| `pids` | 132 | أساس OBD-II المستقبلي |
| `provenance_summary` | 163,569 | شارة المصدر لكل تعريف |
| `dtc_tests` | **0** | فارغ ⇒ «لا يوجد إجراء فحص معتمد» |

### جداول المخطط 4 (جديدة)

| الجدول | الصفوف | المعنى |
| --- | --- | --- |
| `source_quotes` | 6,495 | جُمل حرفية من `description`، مصنّفة بأربع فئات. **ليست إجراءات** |
| `procedure_scope` | 4,484 | نطاق الاقتباس وتحذير التطبيق: `applicability='unverified'`، `approval_status='not_approved'` |
| `translation_drafts` | 100 | مسوّدات عربية `reviewed = 0` |
| `dtc_priority` | 19,089 | `tier` (1–4)، `score`، أسباب الترتيب، `open_conflicts`, `critical_conflicts` |

## 3. الـViews المتاحة للعميل

```
v_dtc_search · v_dtc_lookup · v_dtc_summary · v_dtc_causes · v_dtc_symptoms
v_dtc_repairs · v_dtc_tests · v_dtc_related · v_dtc_provenance · v_dtc_conflicts
v_manufacturers · v_pids · v_vehicles
v_dtc_source_quotes · v_dtc_priority · v_translation_drafts
```

## 4. الاستعلامات المعتمدة (منسوخة كما تُنفَّذ)

### 4.1 فتح القاعدة والتحقق

```sql
SELECT version, schema_version, source_set, test_status FROM db_versions;
-- يجب: schema_version = '4' و test_status = 'passed'
```

### 4.2 البحث أثناء الكتابة (سريع، مفهرس)

```sql
-- تطبيع المُدخل في Dart: UPPER(REPLACE(input, ' ', ''))
SELECT c.id, c.code, c.context_key, c.context_type, m.name AS manufacturer,
       d.title, p.tier, f.risk_level
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id
LEFT JOIN dtc_priority p ON p.dtc_code_id = c.id
JOIN dtc_definitions d
  ON d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1
WHERE c.code LIKE :prefix          -- 'P030%'
   OR d.title LIKE :contains       -- '%misfire%'
ORDER BY (c.code = :exact) DESC, p.tier ASC, c.code ASC
LIMIT 25 OFFSET :page;
```

> **لا تستخدم `v_dtc_search` في القوائم.** قياس على الملف الحقيقي: البحث الحرفي عبر الـView
> = 11.52 ms (SCAN كامل) مقابل 0.08 ms على `dtc_codes` بالفهرس.

### 4.3 تفاصيل كود واحد

```sql
-- 1) الهوية والسياق
SELECT c.*, m.name AS manufacturer, f.mil, f.emissions_relevant,
       f.limp_mode_possible, f.risk_level, f.drive_cycle_required
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id
WHERE c.context_key = ?;

-- 2) كل سياقات الكود نفسه (940 كودًا لها أكثر من سياق، حتى 22)
SELECT code, context_key, context_type, manufacturer_id FROM dtc_codes
WHERE code = (SELECT code FROM dtc_codes WHERE context_key = ?);

-- 3) التعريف
SELECT title, description, verification_status, confidence
FROM dtc_definitions
WHERE dtc_code_id = ? AND language = 'en' AND is_canonical = 1;

-- 4) الأسباب / الأعراض / التقدير / المرتبط / المصادر / التعارض
SELECT t.label FROM dtc_causes x
JOIN dtc_cause_texts t ON t.cause_id = x.id AND t.language = 'en'
WHERE x.dtc_code_id = ? ORDER BY x.id;

SELECT t.text FROM dtc_symptoms x
JOIN dtc_symptom_texts t ON t.symptom_id = x.id AND t.language = 'en'
WHERE x.dtc_code_id = ? ORDER BY x.id;

SELECT difficulty, diy_possible, cost_min, cost_max, currency,
       hours_min, hours_max, verification_status
FROM dtc_repairs WHERE dtc_code_id = ?;

SELECT related_code, relation_type FROM dtc_related_codes WHERE dtc_code_id = ?;

SELECT url, kind, label FROM dtc_evidence_sources
WHERE dtc_code_id = ?
ORDER BY CASE kind WHEN 'reference' THEN 0 ELSE 1 END, url;

SELECT summary, status FROM conflicts WHERE dtc_code_id = ?
ORDER BY id;
```

### 4.4 الاقتباسات (شاشة «ما يقوله المصدر»)

```sql
SELECT text_en, category, classification_rule, quote_status,
       approval_status, applicability
FROM v_dtc_source_quotes
WHERE dtc_code_id = ?
ORDER BY ordinal;
```

قواعد إلزامية في الواجهة:

1. يُقرأ أولًا `SELECT COUNT(*) FROM dtc_tests WHERE dtc_code_id = ?` — إن كان صفرًا
   (وهو صفر لكل الكودات في 0.9.1) تُعرض رسالة «لا يوجد إجراء فحص معتمد» قبل أي اقتباس.
2. الاقتباس يُعرض باسم «ما يقوله المصدر»، مع شارة فئته الأربعة، ولا يُوضع أبدًا تحت
   عنوان «إجراءات معتمدة»، ولا يُرفق بزر تنفيذ.
3. `approval_status` و`applicability` يُعرضان كما هما (`not_approved` / `unverified`).

### 4.5 المسوّدات العربية

```sql
SELECT title, description, context_ar, reviewed, source_url
FROM v_translation_drafts
WHERE dtc_code_id = ? AND language = 'ar';
```

`reviewed` دائمًا `0` في هذا الإصدار ⇒ شارة «مسوّدة ترجمة — لم تُراجَع بشريًا»، ويُعرض
العنوان الإنجليزي دائمًا إلى جانبها.

### 4.6 ترتيب الطبقات والحرج

```sql
SELECT tier, COUNT(*) FROM v_dtc_priority GROUP BY tier;
-- 1: 2,696 · 2: 5,342 · 3: 8,512 · 4: 2,539

SELECT c.code, p.critical_conflicts FROM v_dtc_priority p
JOIN dtc_codes c ON c.id = p.dtc_code_id
WHERE p.critical_conflicts > 0;
-- 14 صفًا: تعارض حرج غير محسوم، تُعرض شارة حمراء ولا يُعرض معنى واحد
```

## 5. قواعد الإصدار والترحيل

- التطبيق يرفض العمل إذا `schema_version < '4'` أو غابت أي من الـ16 View، ويعرض شاشة
  خطأ صريحة («قاعدة البيانات غير متوافقة، حدّث التطبيق»).
- تحديث القاعدة = استبدال الملف المرجعي بالكامل بعد التحقق من SHA‑256، لا تعديل موضعي.
- قاعدة المستخدم لها ترحيلات مستقلة عبر `PRAGMA user_version`.
- أي إضافة لاحقة (مثل `dtc_tests` عند اعتماد إجراءات) ترفع `schema_version` وتُوثَّق هنا
  قبل أن يعتمدها التطبيق.

## 6. الأخطاء المعروفة التي يجب أن تتعامل معها الواجهة

| الحالة | العدد | السلوك |
| --- | --- | --- |
| كود بلا أسباب | 9,556 هوية | قسم «الأسباب» يختفي، مع ملاحظة «المصدر لا يذكر أسبابًا» |
| كود بلا أعراض | 11,551 هوية | نفس المنطق |
| `risk_level` فارغ | 942 | «غير محددة» وليس «منخفضة» |
| تعارض مفتوح | 393 | شارة «المصادر تختلف» + لا حسم |
| بلا إجراءات فحص | 19,089 | رسالة صريحة |
| بلا عربية | 18,989 | يعرض EN فقط بلا شارة |
