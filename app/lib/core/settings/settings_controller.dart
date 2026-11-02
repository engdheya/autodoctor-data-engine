import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'preferences_provider.dart';
import '../l10n/app_strings.dart';
import 'app_settings.dart';

const String _kLanguage = 'settings.language';
const String _kThemeMode = 'settings.theme_mode';
const String _kOnboarding = 'settings.onboarding_complete';

class SettingsController extends Notifier<AppSettings> {
  SharedPreferences get _prefs => ref.read(sharedPreferencesProvider);

  @override
  AppSettings build() {
    final String? language = _prefs.getString(_kLanguage);
    final String? theme = _prefs.getString(_kThemeMode);
    return AppSettings(
      language: AppLanguage.fromCode(language),
      themeMode: switch (theme) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      },
      onboardingComplete: _prefs.getBool(_kOnboarding) ?? false,
    );
  }

  Future<void> setLanguage(AppLanguage language) async {
    await _prefs.setString(_kLanguage, language.code);
    state = state.copyWith(language: language);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    await _prefs.setString(_kThemeMode, mode.name);
    state = state.copyWith(themeMode: mode);
  }

  Future<void> completeOnboarding() async {
    await _prefs.setBool(_kOnboarding, true);
    state = state.copyWith(onboardingComplete: true);
  }
}
