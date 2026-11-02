import 'package:autodoctor_app/core/l10n/app_strings.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('both languages define exactly the declared keys', () {
    expect(AppStrings.enValues.keys.toSet(), AppStrings.keys.toSet());
    expect(AppStrings.arValues.keys.toSet(), AppStrings.keys.toSet());
  });

  test('no translation is empty', () {
    for (final MapEntry<String, String> entry in AppStrings.enValues.entries) {
      expect(entry.value.trim(), isNotEmpty, reason: 'en.${entry.key} is empty');
    }
    for (final MapEntry<String, String> entry in AppStrings.arValues.entries) {
      expect(entry.value.trim(), isNotEmpty, reason: 'ar.${entry.key} is empty');
    }
  });

  test('the Arabic strings are actually Arabic', () {
    final RegExp arabic = RegExp(r'[\u0600-\u06FF]');
    final int withArabic =
        AppStrings.arValues.values.where((String value) => arabic.hasMatch(value)).length;
    // Brand and technical terms stay in Latin script, so a few values legitimately do not
    // contain Arabic letters; the majority must.
    expect(withArabic / AppStrings.arValues.length, greaterThan(0.8));
  });

  test('a missing key never renders as empty text', () {
    const AppStrings broken = AppStrings(<String, String>{});
    expect(broken.settingsTitle, AppStrings.enValues['settingsTitle']);
  });
}
