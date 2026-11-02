# AutoDoctor AI — تطبيق Flutter

قاعدة التشخيص تُقرأ من حزمة `autodoctor-data-engine` (SQLite) المرفقة مع التطبيق.
هذا الملف يشرح ما هو مبني الآن، وكيف يُشغَّل ويُختبر ويُبنى.

## الحالة الحالية (المرحلة 1)

مبني ومختبَر:

- هيكل Clean Architecture بخمس طبقات: `core` · `domain` · `data` · `features` · `services`.
- فتح حزمة التشخيص **للقراءة فقط** بعد التحقق من SHA‑256 المُولَّد من الملف نفسه.
- رفض الحزمة التالفة أو الأقدم من المخطط 4 أو الناقصة الـView برسالة صريحة، بلا رجوع صامت.
- قاعدة مستخدم منفصلة (`autodoctor_user.sqlite`) بترحيلات عبر `PRAGMA user_version`.
- Riverpod للحالة، GoRouter للمسارات، Material 3 بثيم فاتح/داكن، عربي/إنجليزي مع RTL.
- شاشات: Splash (تحقق وفتح) · Onboarding · Home (أرقام حقيقية من القاعدة) · Settings.
- اختبارات معمارية تفشل البناء إذا خرج SQL عن `lib/data/datasources` أو استوردت
  `features`/`domain` حزمة `sqflite`، أو ظهر `print()`.
- عقد OBD‑II وAI كواجهات فقط، بلا تنفيذ ولا أوامر على السيارة.

غير مبني بعد (المراحل 2–6): البحث، تفاصيل العطل، المرآب، السجل، المفضلة، التقارير.

## بناء APK عبر CI

سير العمل جاهز في `ci/flutter-build.yml`. تفعيله:

```bash
mkdir -p .github/workflows && cp ci/flutter-build.yml .github/workflows/
```

(النسخ مطلوب لأن توكن الأتمتة في هذا المستودع لا يملك صلاحية `workflows`.)
ثم من تبويب Actions: `Flutter app` → Run workflow. الناتج `autodoctor-debug-apk` مع
`apk-sha256.txt`.

## المتطلبات

- Flutter 3.24.5 (stable) · Dart 3.5 · JDK 17 · Android SDK 35.

## التشغيل

```bash
# 1) جهّز الحزمة (من جذر المستودع، بعد build-db --source-set public)
python3 app/tool/stage_reference_db.py

# 2) المكتبات والتحليل والاختبارات
cd app
flutter pub get
flutter analyze
flutter test

# 3) مجلد Android ثم البناء
bash tool/bootstrap_android.sh
flutter build apk --debug
```

`assets/db/*.sqlite` غير مُتعقَّب في Git (65 MB). يُنسخ بالخطوة الأولى، وملف
`assets/db/db_manifest.json` **مُتعقَّب** لأنه يحمل الـSHA‑256 المتوقع.

## الاختبارات

| الملف | ما يثبته |
| --- | --- |
| `test/architecture/layer_guard_test.dart` | لا SQL خارج طبقة البيانات، لا `sqflite` في الواجهات، لا `print` |
| `test/data/database_hasher_test.dart` | التوافق مع `sha256sum` وسلوك تغيّر بايت واحد |
| `test/data/db_manifest_test.dart` | رفض البيان الناقص أو غير الرقمي |
| `test/data/reference_database_test.dart` | فتح الحزمة الحقيقية، الأعداد الحقيقية، رفض الملف المُحرَّف، ومنع الكتابة |
| `test/features/home_page_test.dart` | الأرقام في الواجهة، حقل البحث معطّل مع سبب، RTL/LTR |
| `test/core/strings_test.dart` | تطابق مفاتيح العربية والإنجليزية وعدم وجود نص فارغ |

اختبارات الحزمة الحقيقية تُتخطّى تلقائيًا إذا لم تُجهَّز الأصول.
