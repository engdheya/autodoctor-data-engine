# المرحلة 1 — أساس تطبيق Flutter

> حالة هذه المرحلة: **مكتوبة بالكامل، غير مُصرَّفة هنا.** لا يوجد Flutter SDK ولا وصول إلى
> pub.dev في بيئة العمل، لذلك `flutter analyze` و`flutter test` وبناء APK تُنفَّذ في GitHub
> Actions عبر `.github/workflows/flutter-build.yml`، ونتائجها تُنشر كما هي بلا تقدير.
> ما أمكن التحقق منه هنا فعليًا: بنية الحزمة، والتحقق من SHA‑256، وعقد الـ16 View،
> والـSQL المُنفَّذ على القاعدة الحقيقية، واختبارات بايثون للبيانات (267 اختبارًا).

## 1. ما بُني

```
app/
  pubspec.yaml                  حزم مثبّتة، بلا حزم غير مستخدمة
  analysis_options.yaml         strict-casts + strict-raw-types + قواعد صارمة
  assets/db/db_manifest.json    مُتعقَّب: sha256 المتوقع + الإصدار + الـViews المطلوبة
  assets/db/*.sqlite            غير مُتعقَّب (65.9 MB) — يُنسخ بـ tool/stage_reference_db.py
  lib/
    core/    constants · errors · settings · l10n · routing · theme · widgets
    domain/  entities · repositories (abstract) · usecases
    data/    database · datasources · repositories
    features/ splash · onboarding · home · settings
    services/ obd (واجهة) · ai (واجهة)
  test/      architecture · core · data · features
  tool/      stage_reference_db.py · bootstrap_android.sh · patch_android.py
```

### الطبقات وقاعدة الفصل

| الطبقة | تحتوي | ممنوع فيها |
| --- | --- | --- |
| `core` | ثيم، لغات، مسارات، إعدادات، أخطاء، ودجت مشتركة | SQL، `sqflite`، منطق تشخيص |
| `domain` | كيانات + عقود مستودعات + حالات استخدام | أي استيراد من `data` |
| `data` | فتح القاعدتين، SQL، تحويل الصفوف، تنفيذ العقود | قواعد عرض أو نصوص واجهة |
| `features` | شاشات + مزوّدات واجهة فقط | `sqflite`، `openDatabase`، `rawQuery` |
| `services` | عقود OBD‑II والمساعد الذكي | أي تنفيذ فعلي في هذه المرحلة |

`test/architecture/layer_guard_test.dart` يفحص الشيفرة نصًّا ويفشل إن خُرقت هذه القاعدة:
SQL خارج `lib/data`، أو استيراد `sqflite` من `features`/`domain`/`core`، أو `openDatabase`
داخل شاشة، أو أي `print()`.

### فتح قاعدة البيانات (المسار الحقيقي)

1. `assets/db/db_manifest.json` يُقرأ ويُتحقق من حقوله (`version`, `schema_version`,
   `sha256`, `bytes`, `required_views`). بيان ناقص ⇒ `AppFailure(schemaUnsupported)`.
2. عند أول تشغيل تُنسخ الحزمة إلى `getDatabasesPath()` ثم تُفتح
   `OpenDatabaseOptions(readOnly: true)`.
3. `SHA-256` يُحسب بالتدفق (chunked) على الملف كاملًا ويُقارن بالبيان؛ اختلاف ⇒
   `AppFailure(checksumMismatch)` ولا فتح.
4. يُتحقق من `db_versions.schema_version ≥ 4` ومن وجود الـ16 View؛ النقص ⇒
   `AppFailure(viewsMissing)` برسالة تسمّي الـView الغائب.
5. تُقرأ الأعداد الحقيقية (`dtc_codes`, `source_quotes`, `dtc_tests`) وتُعرض في Home.

لا يوجد أي مسار بديل «يفتح قاعدة فارغة ليعمل التطبيق». الفشل يظهر بشاشة تحمل السبب وزر
إعادة المحاولة.

### قاعدة المستخدم

`autodoctor_user.sqlite` منفصلة تمامًا، `version: 1`، وفيها `vehicles`,
`diagnosis_records`, `favorites`, `notes` مع فهارس على `context_key`، و`PRAGMA
foreign_keys = ON`. الترقية تُضاف كبلوك جديد في `onUpgrade` ولا تُعدَّل بلوكات قديمة.

### الواجهة

- Material 3، ثيم فاتح/داكن، لون أساسي أزرق أدوات القياس، وكهرماني محفوظ لما لم يوثّقه المصدر.
- عربي/إنجليزي بتبديل فوري و`Directionality` يتبع اللغة (RTL/LTR مختبَر).
- شاشات المرحلة: Splash (تحقق وفتح) · Onboarding (3 شرائح، قابل للتخطي) · Home · Settings.
- **حقل البحث معطّل بقصد** مع سبب ظاهر: لا نعرض صندوق بحث لا يُرجع شيئًا. يُفعَّل في المرحلة 2.
- بطاقة «إجراءات فحص معتمدة» تعرض `0` ورسالة صريحة بأن التطبيق لا يعرض اقتباسًا أو مسوّدة
  كإجراء معتمد.

## 2. الاختبارات المكتوبة

| الملف | العدد | ما يثبته |
| --- | --- | --- |
| `test/architecture/layer_guard_test.dart` | 4 | فصل الطبقات، منع SQL خارج `data`، منع `print` |
| `test/core/strings_test.dart` | 4 | تطابق مفاتيح ar/en، لا نص فارغ، أغلبية النص العربي عربية |
| `test/data/database_hasher_test.dart` | 2 | التوافق مع `sha256sum` (متجه `abc`) وتغيّر بايت واحد |
| `test/data/db_manifest_test.dart` | 3 | رفض البيان الناقص/غير الرقمي وتطبيع الـhash |
| `test/data/reference_database_test.dart` | 3 | الحزمة الحقيقية: 19,089 كودًا · 6,495 اقتباسًا · 0 إجراء · منع الكتابة · رفض التلاعب |
| `test/features/home_page_test.dart` | 4 | الأرقام الحقيقية، حالة «0 إجراءات»، تعطيل البحث، RTL/LTR |

اختبارات الحزمة الحقيقية تُتخطّى تلقائيًا إذا لم تُجهَّز الأصول، وتعمل في CI بعد بناء القاعدة.

## 3. ما يحتاج تشغيلًا خارجيًا (ولن يُدَّعى قبل حدوثه)

1. `flutter pub get` — يحتاج pub.dev.
2. `flutter analyze` — يحتاج SDK.
3. `flutter test` — يحتاج SDK (اختبارات الحزمة تحتاج `sqflite_common_ffi`).
4. `flutter build apk` — يحتاج SDK + JDK 17 + Android SDK.
5. تشغيل فعلي على جهاز — غير متاح هنا إطلاقًا.

سير العمل `ci/flutter-build.yml` ينفّذ: بناء القاعدة العامة (مع تجاوز D012
الموسوم «CI verification bundle; not for publication») ← stage ← pub get ← analyze ←
test ← bootstrap Android ← build debug APK ← رفع APK + SHA‑256 كـ artifact.

**تفعيله:** توكن الأتمتة المستخدم لهذا المستودع لا يملك صلاحية `workflows`، لذلك رُفض دفع
الملف إلى `.github/workflows/` (رسالة GitHub: *refusing to allow a GitHub App to create or
update workflow … without `workflows` permission*). الحل بسطر واحد — إمّا منح الصلاحية، أو:

```bash
mkdir -p .github/workflows && cp ci/flutter-build.yml .github/workflows/
```

الملف نفسه لا يحتاج أي تعديل لأن كل مساراته نسبة إلى جذر المستودع.

## 4. أوامر التشغيل محليًا

```bash
# من جذر المستودع
python3 app/tool/stage_reference_db.py
cd app
flutter pub get && flutter analyze && flutter test
bash tool/bootstrap_android.sh
flutter build apk --debug
```

`python3 app/tool/stage_reference_db.py` يقرأ أحدث `data/exports/autodoctor-app-*.sqlite`،
يتحقق من `integrity_check`، ينسخه إلى `assets/db/`، ويكتب البيان من الملف نفسه (الإصدار،
المخطط، الحجم، SHA‑256، وقائمة الـViews من `sqlite_master`). لا قيمة مكتوبة بيد.

## 5. المرحلة التالية (2)

البحث الحقيقي (كود/عنوان/تصفية/اقتراحات) + شاشة تفاصيل العطل بكل أقسامها + محدد السياقات
المتعددة (940 كودًا) + شارات المصدر والتوثيق + شاشة «ما يقوله المصدر» مع الفئات الأربع،
مع اختبارات أداء على جهاز متوسط المستوى.
