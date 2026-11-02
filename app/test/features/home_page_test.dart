import 'package:autodoctor_app/core/l10n/app_strings.dart';
import 'package:autodoctor_app/core/settings/settings_controller.dart';
import 'package:autodoctor_app/domain/entities/database_summary.dart';
import 'package:autodoctor_app/features/home/home_page.dart';
import 'package:autodoctor_app/providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const DatabaseSummary _summary = DatabaseSummary(
  version: '0.9.1',
  schemaVersion: 4,
  sourceSet: 'public',
  fileBytes: 65884160,
  codeCount: 19089,
  quoteCount: 6495,
  approvedProcedures: 0,
);

class _Shell extends ConsumerWidget {
  const _Shell();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final Locale locale = Locale(ref.watch(settingsProvider).language.code);
    return MaterialApp(
      locale: locale,
      supportedLocales: const <Locale>[Locale('en'), Locale('ar')],
      localizationsDelegates: const <LocalizationsDelegate<Object>>[
        AppStringsDelegate(),
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const HomePage(),
    );
  }
}

Future<void> _pump(WidgetTester tester, {AppLanguage language = AppLanguage.ar}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{
    'settings.language': language.code,
    'settings.onboarding_complete': true,
  });
  final SharedPreferences preferences = await SharedPreferences.getInstance();

  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        sharedPreferencesProvider.overrideWithValue(preferences),
        librarySummaryProvider.overrideWith((Ref ref) async => _summary),
      ],
      child: const _Shell(),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the real counts of the opened bundle', (WidgetTester tester) async {
    await _pump(tester);
    expect(find.text('0.9.1'), findsOneWidget);
    expect(find.text('19,089'), findsOneWidget);
    expect(find.text('6,495'), findsOneWidget);
  });

  testWidgets('states that no approved procedure exists', (WidgetTester tester) async {
    await _pump(tester);
    expect(find.text(AppStrings.ar.homeApprovedProceduresNone), findsOneWidget);
  });

  testWidgets('the search field is disabled and says why', (WidgetTester tester) async {
    await _pump(tester);
    final TextField field = tester.widget<TextField>(find.byType(TextField));
    expect(field.enabled, isFalse, reason: 'a search box that returns nothing is fake UI');
    expect(find.text(AppStrings.ar.homeSearchSubtitle), findsOneWidget);
  });

  testWidgets('renders right-to-left in Arabic and left-to-right in English',
      (WidgetTester tester) async {
    await _pump(tester);
    final BuildContext arabic = tester.element(find.byType(HomePage));
    expect(Directionality.of(arabic), TextDirection.rtl);

    await _pump(tester, language: AppLanguage.en);
    final BuildContext english = tester.element(find.byType(HomePage));
    expect(Directionality.of(english), TextDirection.ltr);
  });
}
