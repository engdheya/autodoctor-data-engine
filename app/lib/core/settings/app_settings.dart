import 'package:flutter/material.dart';

import '../l10n/app_strings.dart';

/// How the app is configured on this device. Stored in SharedPreferences, never in the
/// diagnostic bundle and never on a server.
class AppSettings {
  const AppSettings({
    this.language = AppLanguage.ar,
    this.themeMode = ThemeMode.system,
    this.onboardingComplete = false,
  });

  final AppLanguage language;
  final ThemeMode themeMode;
  final bool onboardingComplete;

  AppSettings copyWith({
    AppLanguage? language,
    ThemeMode? themeMode,
    bool? onboardingComplete,
  }) {
    return AppSettings(
      language: language ?? this.language,
      themeMode: themeMode ?? this.themeMode,
      onboardingComplete: onboardingComplete ?? this.onboardingComplete,
    );
  }
}
