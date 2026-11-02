# AutoDoctor AI — مناقشة القرارات قبل التنفيذ (D1–D8)

> مبني على قياس الملفات الفعلية. لا يوجد رقم هنا بلا مصدر: إمّا قاعدة
> `autodoctor-app-0.9.0-public.sqlite` أو تصدير `procedures-quoted.yaml` أو مسوّدات
> `data/translations/ar/`. القرارات التي أجبت عنها (D1, D2, D5) مكتوبة هنا بتفصيلها
> التنفيذي، والباقي (D3, D4, D6, D7, D8) ينتظر كلمتك.

---

## D1 — اقتباسات المصدر داخل التطبيق (اخترت: نعم)

### ما قِيس أولًا (وهو ما يحسم القرار)

فحصت كل اقتباس من الـ**5,981** ومقارنته حرفيًا بنص الوصف الإنجليزي لنفس `context_key`
داخل قاعدة البيانات:

```
quotes verbatim in imported description: 5981
not found:                                0
```

**النتيجة: 100% من الاقتباسات موجودة أصلًا داخل التطبيق** كجزء من `dtc_definitions.description`
(المصدَّرة من OBDex CC0‑1.0 وWal33D MIT). أي أن D1 **لا يضيف أي سطح ترخيص جديد**؛
هو إعادة تنظيم لعرض نص موجود، لا استيراد محتوى من PDF‑ات Ford/GM/SAE.

### التصميم

جداول جديدة في **حزمة التطبيق** تُبنى من نفس مسار `procedures.py` (مصدر تصنيف واحد):

```sql
CREATE TABLE source_quotes (
    id                    INTEGER PRIMARY KEY,
    dtc_code_id           INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    ordinal               INTEGER NOT NULL,
    text_en               TEXT    NOT NULL,
    category              TEXT    NOT NULL
                          CHECK (category IN ('diagnostic_check','monitoring_description',
                                              'technical_explanation','non_procedure')),
    classification_rule   TEXT    NOT NULL,
    classification_status TEXT    NOT NULL,   -- rule_based_unreviewed
    verbatim              INTEGER NOT NULL DEFAULT 1 CHECK (verbatim IN (0,1)),
    measurements_json     TEXT,
    quote_status          TEXT    NOT NULL,   -- quoted_unreviewed
    UNIQUE (dtc_code_id, ordinal)
);

CREATE TABLE procedure_scope (
    dtc_code_id       INTEGER PRIMARY KEY REFERENCES dtc_codes(id) ON DELETE CASCADE,
    definition_scope  TEXT,
    applicability     TEXT NOT NULL,   -- always 'unverified' in this build
    applicability_note TEXT,
    approval_status   TEXT NOT NULL    -- always 'not_approved' in this build
);

CREATE VIEW v_dtc_source_quotes AS
SELECT c.context_key, c.code, q.ordinal, q.text_en, q.category,
       q.classification_rule, q.classification_status, q.quote_status
FROM source_quotes q JOIN dtc_codes c ON c.id = q.dtc_code_id;
```

### ما يعرضه التطبيق (بترتيب صريح لا يقبل اللبس)

1. أعلى الشاشة: **«لا يوجد إجراء فحص معتمد لهذا الكود»** — تُقرأ من `dtc_tests` (0 صف)
   و`procedure_scope.approval_status` (`not_approved`)، ولا تُخفى أبدًا.
2. تحتها: قسم موسوم **«ما يقوله المصدر»** — كل اقتباس بشارة فئته:
   `فحص تشخيصي محتمل` · `وصف مراقبة` · `شرح تقني` · `ليس إجراءً`.
3. سطر ثابت لكل اقتباس: «مقتطف حرفي من المصدر، غير مُعتمد كإجراء، ولم تُثبت صلاحيته
   لسيارة/محرك محدد».
4. لا زر «ابدأ الفحص»، ولا علامات صح، ولا قيم قياس — لأن `tools/limits/nominal_values`
   فارغة في التصدير لكل الكودات.

### الحجم والأثر

- النص كله **749,785 بايت** (≈0.75 MB) — لا يغيّر حجم الحزمة جوهريًا.
- التغطية: 4,009 كودًا من 19,089 (21%)، كلها في **Tier‑1 (1,589 كودًا من 2,696)**
  و**Tier‑2 (2,420 من 5,342)**.
- 415 اقتباسًا فقط مصنّف `diagnostic_check` موزّعة على 412 كودًا؛ الباقي (5,566) وصف/شرح.
  هذا يعني عمليًا: **410 كودًا من أصل 19,089** سترى فيها جملة تشبه خطوة فحص.

### الخطر والمعالجة

| الخطر | المعالجة |
| --- | --- |
| المستخدم يقرأ الاقتباس كإجراء معتمد | ترتيب الشاشة أعلاه + وسوم إلزامية + اختبار Widget يفشل إن ظهر اقتباس تحت ودجت «الإجراءات المعتمدة» |
| تصنيف `diagnostic_check` خاطئ | التصنيف `rule_based_unreviewed` ويُعرض كما هو؛ لا يُعاد تسميته إلى «معتمد» |
| تطابق النص مع المصدر مستقبلًا | العمود `verbatim` مع فحص استيراد يقارن الاقتباس بنص الوصف ويُفشل البناء عند عدم التطابق (نفس الفحص الذي أثبت الـ5,981) |

---

## D2 — المسوّدات العربية (اخترت: نعم بشارة صريحة)

### الوقائع

- القاعدة: `language` يحتوي `en` (28,338) و`de` (9,533) فقط، و`translations` = **0 صف**.
- المسوّدات: **100** مدخلًا في `data/translations/ar/priority-00[1-5].yaml`، كلها
  `reviewed: false` و`translator: ""`، وكل أكوادها موجودة في القاعدة (100/100 في سياق generic).
- التغطية الناتجة: **100 كودًا من 19,089 (0.52%)** — لذلك الواجهة يجب أن تتعامل مع
  «عربي متاح/غير متاح» لكل كود، لا مع «التطبيق عربي».

### التصميم

```sql
CREATE TABLE translation_drafts (
    dtc_code_id  INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    language     TEXT    NOT NULL DEFAULT 'ar',
    title        TEXT,
    description  TEXT,
    context_ar   TEXT,
    reviewed     INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0,1)),
    translator   TEXT,
    reviewer     TEXT,
    source_url   TEXT,
    created_at   TEXT    NOT NULL,
    PRIMARY KEY (dtc_code_id, language)
);
```

قواعد العرض الملزمة:

- العربية **لا تُعرض كعنوان أساسي**: العنوان الإنجليزي يبقى ظاهرًا دائمًا، والعربي تحته
  بشارة **«مسوّدة ترجمة — لم تُراجَع بشريًا»** (لون تحذيري، ليست نفس نمط النص المعتمد).
- إن كان الكود بلا مسوّدة: لا فراغ ولا «—»، بل الواجهة تعرض الإنجليزي فقط بلا شارة.
- `context_ar` (سياق المصدر، مثل «Ford/GM تحديدًا») يُعرض داخل صندوق السياق، لأنه يمنع
  تعميم العطل على كل السيارات — وهو مطلب سابق مثبت في المسوّدات.
- البحث العربي: يعمل على الـ100 عنوان عربي فقط، ويُصرَّح بذلك في شاشة البحث
  («البحث العربي متاح لـ100 كود مراجَع كمسوّدة»).

**لماذا لا نسمّيها ترجمة معتمدة:** القاعدة الثابتة في المشروع أن MT لا يُوسم مراجَعًا.
هذه المسوّدات مولّدة آليًا و`reviewer` فارغ؛ تبقى `reviewed = 0` في القاعدة والواجهة معًا.

---

## D5 — بناء APK عبر GitHub Actions (اخترت: نعم)

### الوقائع

```
flutter: غير موجود   dart: غير موجود   java: غير موجود   gradle: غير موجود
pub.dev: غير متاح من هذه البيئة (المتاح: github.com, api.github.com, npm, pypi)
```

لا يمكن إنتاج APK هنا. الحل المقترح سير عمل يبنيه على GitHub:

```yaml
name: flutter-build
on: { workflow_dispatch: {}, push: { paths: ["app/**"] } }
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "17" }
      - uses: subosito/flutter-action@v2
        with: { flutter-version: "3.24.5", channel: stable, cache: true }
      - run: flutter pub get
        working-directory: app
      - run: flutter analyze
        working-directory: app
      - run: flutter test --coverage
        working-directory: app
      - run: flutter build apk --debug --target-platform android-arm64
        working-directory: app
      - uses: actions/upload-artifact@v4
        with: { name: autodoctor-debug-apk, path: app/build/app/outputs/flutter-apk/*.apk }
```

- `--debug` يُنتج APK **قابلًا للتثبيت** بلا مفاتيح توقيع (وهو ما تحتاجه للاختبار).
- نسخة `--release` تحتاج keystore؛ لن أُنشئ مفتاحًا ولن أخزّنه في المستودع. عند الحاجة:
  توقيع على جهازك أو أسرار GitHub (`KEYSTORE_BASE64`, `KEY_PASSWORD`) — قرارك لاحقًا.
- الملفات الناتجة تبقى 90 يومًا كـ artifact؛ وسأوثّق SHA‑256 لكل APK في `docs/`.

### الخطر الوحيد

دفع `.github/workflows/` يحتاج صلاحية `workflow` في التوكن. سأحاول؛ إن رُفض الدفع
سأضع الملف في `ci/flutter-build.yml` وأخبرك بالسطر الوحيد الذي تضيفه (أو تمنح الصلاحية).

---

## D3 — تمييز التعارضات الحرجة (يحتاج كلمتك)

الواقع: جدول `conflicts` في حزمة التطبيق فيه **393** صفًا كلها `needs_review`، **بلا عمود
حرج**. لكن القاعدة المستخدمة في `priority.py` — وهي قاعدة مُوثَّقة ومختبَرة — تحسبها
حتميًا:

```sql
open     = conflicts WHERE dtc_code_id=c.id AND status='needs_review'
critical = open AND similarity < 0.75 AND risk_level IN ('high','critical')
```

توصيتي: تجميد هذه القيم وقت البناء في جدول واحد:

```sql
CREATE TABLE dtc_priority (
    dtc_code_id        INTEGER PRIMARY KEY REFERENCES dtc_codes(id) ON DELETE CASCADE,
    tier               INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    score              REAL    NOT NULL,
    reasons_json       TEXT    NOT NULL,
    open_conflicts     INTEGER NOT NULL DEFAULT 0,
    critical_conflicts INTEGER NOT NULL DEFAULT 0
);
```

**لماذا هذا الجدول ضروري أيضًا (سبب لم يكن في تقرير الأمس):** حزمة التطبيق **لا تحتوي**
`provenance_claims` ولا `source_records` التي يعتمد عليها `priority_index()`؛ فالتطبيق
لا يستطيع حساب الـTier بنفسه. بدون `dtc_priority` لن تعمل «فلترة الطبقة» ولا ترتيب
«الأهم أولًا» في شاشة البحث. المقاسات محسوبة ومتاحة (Tier‑1 2,696 · Tier‑2 5,342 ·
Tier‑3 8,512 · Tier‑4 2,539، ومجموعها 19,089 = كل الهويات في الحزمة، فلا سجل مفقود).

---

## D4 — عرض تقديرات الإصلاح (يحتاج كلمتك)

الواقع: 9,533 صفًا في `dtc_repairs`، كلها `repair_key='repair_estimate'`، وفيها
`difficulty` (easy/medium/hard/shop_only) و`cost_min/cost_max` بعملة **EUR** و
`hours_min/hours_max`، و`dtc_repair_texts` = **0** (لا نص توصية).

توصيتي: تُعرض كبطاقة **«تقدير مصدري»** لا كتسعير:

- «التكلفة التقديرية: 30–800 EUR (وفق المصدر، تقدير عام لا يشمل تشخيصًا أو أجرة ورشة محلية)».
- «الوقت التقديري: 0.3–4.0 ساعة».
- «الصعوبة: سهلة» مع `diy_possible` إن وُجد.
- شارة `source_reported` بجانب كل رقم، وفق `verification_status`.

البديل الأكثر تحفظًا (لا أرقام إطلاقًا) يفقد قيمة عملية كبيرة للمستخدم، والبيانات موجودة
ومصدرها معروف، فلا أرى مبررًا لإخفائها — لكن القرار قرارك لأن الأرقام قد تُقرأ كالتزام.

---

## D6 — تقسيم العمل إلى PRs (يحتاج كلمتك)

توصيتي: **6 PRs**، واحد لكل مرحلة، كل واحد مع اختباراته الخضراء قبل التالي:

1. هيكل + ثيم + لغات + فتح القاعدة للقراءة فقط + تحقق SHA + حارس معماري.
2. البحث + التفاصيل + السياقات + المصادر.
3. Garage + History + Favorites.
4. الإجراءات (فارغة صريحة) + الاقتباسات + التقارير PDF.
5. الإعدادات + RTL + الوضع الداكن + قياس الأداء.
6. البناء والتوثيق والتسليم (APK + README + الحزم وإصداراتها).

بديل «PR واحد كبير» يجعل المراجعة والحسم أصعب، ولا يتيح اختبار كل مرحلة قبل التالية كما طلبت.

---

## D7 — إصدار قاعدة البيانات (يحتاج كلمتك)

إضافة الجداول الأربعة والـViews يعني تغيير **العقد**، لا مجرد إضافة بيانات:

- `schema_version`: **3 → 4**، وإصدار القاعدة **0.9.0 → 0.9.1** (حزمة تطبيق جديدة).
- التطبيق يتحقق عند الفتح: `db_versions.version` و`schema_version`، ويرفض العمل على
  مخطط غير مدعوم برسالة صريحة بدل أخطاء SQL غامضة.
- ملف `assets/db/db_manifest.json` يُحدَّث بـ`sha256` الجديد وحجم الملف.
- إعادة تشغيل كامل: `fetch-sources` → `import --all` → `build-db` → اختبارات →
  `deliveries/` جديدة بـ`SHA256SUMS`. (~20–30 دقيقة قياسًا على الجولات السابقة)

---

## D8 — معرّف التطبيق

`applicationId = "ai.autodoctor.diagnostics"` · `namespace` نفسه · اسم العرض
«AutoDoctor AI» · `minSdk 24` (Android 7) · `targetSdk 35` · `compileSdk 35`.

---

## خلاصة ما تبقّى من قرارات

| القرار | التوصية | الأثر إن رُفض |
| --- | --- | --- |
| D3 تمييز الحرج + جدول `dtc_priority` | نعم | لا فلترة طبقات ولا تحذير مميّز للحرج |
| D4 تقديرات التكلفة | تُعرض موسومة | فقدان قيمة عملية كبيرة |
| D6 ستة PRs | نعم | مراجعة أصعب |
| D7 رفع الإصدار إلى 0.9.1 / schema 4 | نعم | لا يمكن إضافة الاقتباسات والعربية إطلاقًا |
| D8 المعرّف أعلاه | نعم | تغييره لاحقًا يكلّف إعادة نشر |

بعد إجابتك أبدأ التنفيذ من D7 (بناء 0.9.1) في نفس المسار، ثم المرحلة 1 من التطبيق،
لأن التطبيق لا يمكن أن يُختبر اختبارًا حقيقيًا قبل أن تحمل الحزمة الجداول التي يقرأها.
