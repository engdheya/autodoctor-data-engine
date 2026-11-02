import 'package:flutter/material.dart';

/// A visual identity built for a diagnostic tool: deep graphite surfaces, a single
/// instrument-blue accent, and amber reserved for anything the source has not verified.
class AppPalette {
  const AppPalette._();

  static const Color instrumentBlue = Color(0xFF1B6EF3);
  static const Color instrumentBlueDark = Color(0xFF6EA8FF);
  static const Color graphite = Color(0xFF11161C);
  static const Color graphiteRaised = Color(0xFF1A222B);
  static const Color steel = Color(0xFF5A6875);
  static const Color amber = Color(0xFFC77700);
  static const Color amberDark = Color(0xFFF0A93B);
  static const Color danger = Color(0xFFC0392B);
  static const Color dangerDark = Color(0xFFFF6B5B);
  static const Color success = Color(0xFF1E7F4F);

  static Color riskColor(String? risk, Brightness brightness) {
    final dark = brightness == Brightness.dark;
    switch (risk) {
      case 'critical':
      case 'high':
        return dark ? dangerDark : danger;
      case 'medium':
        return dark ? amberDark : amber;
      case 'low':
        return success;
      default:
        // "the source stated nothing" is not the same as "low risk"; it gets no colour.
        return dark ? steel : steel;
    }
  }
}

class AppTheme {
  const AppTheme._();

  static ThemeData light() => _base(Brightness.light);

  static ThemeData dark() => _base(Brightness.dark);

  static ThemeData _base(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: AppPalette.instrumentBlue,
      brightness: brightness,
    ).copyWith(
      surface: dark ? AppPalette.graphite : const Color(0xFFF7F9FB),
      secondary: dark ? AppPalette.amberDark : AppPalette.amber,
      error: dark ? AppPalette.dangerDark : AppPalette.danger,
    );

    final base = ThemeData(brightness: brightness, colorScheme: scheme, useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: base.textTheme.titleLarge?.copyWith(
          fontWeight: FontWeight.w600,
          letterSpacing: -0.2,
        ),
      ),
      cardTheme: CardTheme(
        color: dark ? AppPalette.graphiteRaised : Colors.white,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: scheme.outlineVariant.withOpacity(0.6)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? AppPalette.graphiteRaised : Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.primary, width: 1.6),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(50),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),
      listTileTheme: const ListTileThemeData(contentPadding: EdgeInsets.symmetric(horizontal: 4)),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant.withOpacity(0.5)),
    );
  }
}
