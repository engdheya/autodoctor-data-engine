import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/constants/app_info.dart';
import 'core/l10n/app_strings.dart';
import 'core/routing/app_router.dart';
import 'core/settings/app_settings.dart';
import 'core/theme/app_theme.dart';
import 'providers.dart';

final Provider<GoRouter> routerProvider = Provider<GoRouter>((Ref ref) => buildRouter());

class AutoDoctorApp extends ConsumerWidget {
  const AutoDoctorApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppSettings settings = ref.watch(settingsProvider);
    final GoRouter router = ref.watch(routerProvider);
    final Locale locale = Locale(settings.language.code);

    return MaterialApp.router(
      title: AppInfo.name,
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      locale: locale,
      supportedLocales: <Locale>[
        for (final AppLanguage language in AppLanguage.values) Locale(language.code),
      ],
      localizationsDelegates: const <LocalizationsDelegate<Object>>[
        AppStringsDelegate(),
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: settings.themeMode,
      builder: (BuildContext context, Widget? child) {
        // The locale decides the direction; the whole tree follows it, including the
        // router pages, so RTL is a property of the app and not of each screen.
        return Directionality(
          textDirection: settings.language.direction,
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
