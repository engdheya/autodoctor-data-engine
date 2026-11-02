/// Typed, dependency-free localisation.
///
/// ARB code generation is deliberately avoided in phase 1: it adds a build step that has
/// to run before `flutter analyze`, and nothing here needs plural rules yet. Every key is
/// declared once in [AppStrings.keys], so a translation that forgets a key fails a test
/// instead of rendering an empty label in front of a user.
library;

import 'package:flutter/widgets.dart';

enum AppLanguage {
  en('en', 'English', TextDirection.ltr),
  ar('ar', 'العربية', TextDirection.rtl);

  const AppLanguage(this.code, this.label, this.direction);

  final String code;
  final String label;
  final TextDirection direction;

  static AppLanguage fromCode(String? code) {
    return AppLanguage.values.firstWhere(
      (value) => value.code == code,
      orElse: () => AppLanguage.en,
    );
  }
}

class AppStrings {
  const AppStrings(this._values);

  final Map<String, String> _values;

  /// Every key the application can ask for. A language must define all of them.
  static const List<String> keys = <String>[
    'appName',
    'appTagline',
    'actionContinue',
    'actionSkip',
    'actionRetry',
    'splashPreparing',
    'splashVerifying',
    'splashOpening',
    'splashFailedTitle',
    'onboardingTitle1',
    'onboardingBody1',
    'onboardingTitle2',
    'onboardingBody2',
    'onboardingTitle3',
    'onboardingBody3',
    'homeTitle',
    'homeSearchHint',
    'homeSearchSubtitle',
    'homeDatabaseCard',
    'homeDatabaseVersion',
    'homeDatabaseSchema',
    'homeDatabaseCodes',
    'homeDatabaseQuotes',
    'homeDatabaseApprovedProcedures',
    'homeApprovedProceduresNone',
    'homePhaseNote',
    'settingsTitle',
    'settingsLanguage',
    'settingsAppearance',
    'settingsThemeSystem',
    'settingsThemeLight',
    'settingsThemeDark',
    'settingsDatabase',
    'settingsAbout',
    'settingsVersion',
    'settingsPrivacy',
    'settingsPrivacyBody',
    'sourceDisclosure',
    'severityUnknown',
    'procedureNotApproved',
  ];

  /// The same keys, in both languages. Tests assert they match [keys] exactly.
  static const Map<String, String> enValues = <String, String>{
    'appName': 'AutoDoctor AI',
    'appTagline': 'Intelligent vehicle diagnostics',
    'actionContinue': 'Continue',
    'actionSkip': 'Skip',
    'actionRetry': 'Try again',
    'splashPreparing': 'Preparing the diagnostic database…',
    'splashVerifying': 'Verifying the database signature…',
    'splashOpening': 'Opening the database…',
    'splashFailedTitle': 'The database could not be opened',
    'onboardingTitle1': 'Understand the code, not just the number',
    'onboardingBody1':
        'Every code is shown with its source, its verification status and the exact '
            'vehicle context it was written for.',
    'onboardingTitle2': 'No invented causes or procedures',
    'onboardingBody2':
        'Causes and symptoms appear only when a licensed source states them. Inspection '
            'procedures appear only when a qualified technician has approved them.',
    'onboardingTitle3': 'Works without a connection',
    'onboardingBody3':
        'The whole diagnostic database is stored on the device. Nothing is sent anywhere '
            'unless you export a report yourself.',
    'homeTitle': 'Diagnostics',
    'homeSearchHint': 'Search a code or a fault, e.g. P0301',
    'homeSearchSubtitle': 'Search is delivered in phase 2 — this build verifies the database',
    'homeDatabaseCard': 'Diagnostic database',
    'homeDatabaseVersion': 'Version',
    'homeDatabaseSchema': 'Schema',
    'homeDatabaseCodes': 'Codes',
    'homeDatabaseQuotes': 'Quoted source sentences',
    'homeDatabaseApprovedProcedures': 'Approved inspection procedures',
    'homeApprovedProceduresNone':
        'No approved inspection procedure exists in this database yet. The app will never '
            'show a draft or a quoted sentence as if it were an approved procedure.',
    'homePhaseNote':
        'Phase 1: the reference database is verified and opened read-only. Search, details '
            'and the garage arrive in the next phases.',
    'settingsTitle': 'Settings',
    'settingsLanguage': 'Language',
    'settingsAppearance': 'Appearance',
    'settingsThemeSystem': 'System',
    'settingsThemeLight': 'Light',
    'settingsThemeDark': 'Dark',
    'settingsDatabase': 'Diagnostic database',
    'settingsAbout': 'About',
    'settingsVersion': 'App version',
    'settingsPrivacy': 'Privacy',
    'settingsPrivacyBody':
        'No account, no analytics and no network permission in this build. Everything you '
            'save stays in a local database on this device.',
    'sourceDisclosure': 'Source-stated information',
    'severityUnknown': 'Not stated by the source',
    'procedureNotApproved': 'Not approved',
  };

  static const Map<String, String> arValues = <String, String>{
    'appName': 'AutoDoctor AI',
    'appTagline': 'تشخيص ذكي لأعطال السيارة',
    'actionContinue': 'متابعة',
    'actionSkip': 'تخطٍّ',
    'actionRetry': 'إعادة المحاولة',
    'splashPreparing': 'جارٍ تهيئة قاعدة البيانات التشخيصية…',
    'splashVerifying': 'جارٍ التحقق من بصمة قاعدة البيانات…',
    'splashOpening': 'جارٍ فتح قاعدة البيانات…',
    'splashFailedTitle': 'تعذّر فتح قاعدة البيانات',
    'onboardingTitle1': 'افهم العطل لا الرمز وحده',
    'onboardingBody1':
        'كل كود يظهر مع مصدره وحالة توثيقه والسياق الذي كُتب من أجله تحديدًا.',
    'onboardingTitle2': 'لا أسباب ولا إجراءات مُختلقة',
    'onboardingBody2':
        'الأسباب والأعراض تظهر فقط عندما يذكرها مصدر مرخّص. وإجراءات الفحص تظهر فقط بعد '
            'اعتمادها من فني مؤهل.',
    'onboardingTitle3': 'يعمل بلا إنترنت',
    'onboardingBody3':
        'قاعدة البيانات التشخيصية كاملة على الجهاز، ولا يُرسل شيء إلى أي جهة إلا إذا صدّرت '
            'تقريرًا بنفسك.',
    'homeTitle': 'التشخيص',
    'homeSearchHint': 'ابحث بكود أو باسم العطل، مثال P0301',
    'homeSearchSubtitle': 'البحث يُسلَّم في المرحلة الثانية — هذا البناء يتحقق من القاعدة',
    'homeDatabaseCard': 'قاعدة البيانات التشخيصية',
    'homeDatabaseVersion': 'الإصدار',
    'homeDatabaseSchema': 'المخطط',
    'homeDatabaseCodes': 'الأكواد',
    'homeDatabaseQuotes': 'جُمل مقتبسة من المصدر',
    'homeDatabaseApprovedProcedures': 'إجراءات فحص معتمدة',
    'homeApprovedProceduresNone':
        'لا يوجد إجراء فحص معتمد في هذه القاعدة بعد. ولن يعرض التطبيق مسوّدة أو اقتباسًا '
            'بوصفه إجراءً معتمدًا.',
    'homePhaseNote':
        'المرحلة الأولى: التحقق من قاعدة المرجع وفتحها للقراءة فقط. البحث والتفاصيل '
            'والمرآب في المراحل التالية.',
    'settingsTitle': 'الإعدادات',
    'settingsLanguage': 'اللغة',
    'settingsAppearance': 'المظهر',
    'settingsThemeSystem': 'حسب النظام',
    'settingsThemeLight': 'فاتح',
    'settingsThemeDark': 'داكن',
    'settingsDatabase': 'قاعدة البيانات التشخيصية',
    'settingsAbout': 'حول التطبيق',
    'settingsVersion': 'إصدار التطبيق',
    'settingsPrivacy': 'الخصوصية',
    'settingsPrivacyBody':
        'لا حساب ولا تحليلات ولا صلاحية شبكة في هذا البناء. كل ما تحفظه يبقى في قاعدة '
            'محلية على جهازك.',
    'sourceDisclosure': 'معلومة صرّح بها المصدر',
    'severityUnknown': 'غير مذكورة في المصدر',
    'procedureNotApproved': 'غير معتمد',
  };

  static const AppStrings en = AppStrings(enValues);
  static const AppStrings ar = AppStrings(arValues);

  static AppStrings of(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    return language == AppLanguage.ar.code ? ar : en;
  }

  String _get(String key) =>
      _values[key] ?? enValues[key] ?? key;

  String get appName => _get('appName');
  String get appTagline => _get('appTagline');
  String get actionContinue => _get('actionContinue');
  String get actionSkip => _get('actionSkip');
  String get actionRetry => _get('actionRetry');
  String get splashPreparing => _get('splashPreparing');
  String get splashVerifying => _get('splashVerifying');
  String get splashOpening => _get('splashOpening');
  String get splashFailedTitle => _get('splashFailedTitle');
  String get onboardingTitle1 => _get('onboardingTitle1');
  String get onboardingBody1 => _get('onboardingBody1');
  String get onboardingTitle2 => _get('onboardingTitle2');
  String get onboardingBody2 => _get('onboardingBody2');
  String get onboardingTitle3 => _get('onboardingTitle3');
  String get onboardingBody3 => _get('onboardingBody3');
  String get homeTitle => _get('homeTitle');
  String get homeSearchHint => _get('homeSearchHint');
  String get homeSearchSubtitle => _get('homeSearchSubtitle');
  String get homeDatabaseCard => _get('homeDatabaseCard');
  String get homeDatabaseVersion => _get('homeDatabaseVersion');
  String get homeDatabaseSchema => _get('homeDatabaseSchema');
  String get homeDatabaseCodes => _get('homeDatabaseCodes');
  String get homeDatabaseQuotes => _get('homeDatabaseQuotes');
  String get homeDatabaseApprovedProcedures => _get('homeDatabaseApprovedProcedures');
  String get homeApprovedProceduresNone => _get('homeApprovedProceduresNone');
  String get homePhaseNote => _get('homePhaseNote');
  String get settingsTitle => _get('settingsTitle');
  String get settingsLanguage => _get('settingsLanguage');
  String get settingsAppearance => _get('settingsAppearance');
  String get settingsThemeSystem => _get('settingsThemeSystem');
  String get settingsThemeLight => _get('settingsThemeLight');
  String get settingsThemeDark => _get('settingsThemeDark');
  String get settingsDatabase => _get('settingsDatabase');
  String get settingsAbout => _get('settingsAbout');
  String get settingsVersion => _get('settingsVersion');
  String get settingsPrivacy => _get('settingsPrivacy');
  String get settingsPrivacyBody => _get('settingsPrivacyBody');
  String get sourceDisclosure => _get('sourceDisclosure');
  String get severityUnknown => _get('severityUnknown');
  String get procedureNotApproved => _get('procedureNotApproved');

  Map<String, String> get entries => Map<String, String>.unmodifiable(_values);
}

class AppStringsDelegate extends LocalizationsDelegate<AppStrings> {
  const AppStringsDelegate();

  @override
  bool isSupported(Locale locale) =>
      locale.languageCode == AppLanguage.en.code || locale.languageCode == AppLanguage.ar.code;

  @override
  Future<AppStrings> load(Locale locale) async =>
      locale.languageCode == AppLanguage.ar.code ? AppStrings.ar : AppStrings.en;

  @override
  bool shouldReload(AppStringsDelegate old) => false;
}
