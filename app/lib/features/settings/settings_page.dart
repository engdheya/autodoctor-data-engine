import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/constants/app_info.dart';
import '../../core/l10n/app_strings.dart';
import '../../core/settings/app_settings.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/info_card.dart';
import '../../domain/entities/database_summary.dart';
import '../../providers.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppStrings strings = AppStrings.of(context);
    final AppSettings settings = ref.watch(settingsProvider);
    final AsyncValue<DatabaseSummary> library = ref.watch(librarySummaryProvider);
    // Latin digits on purpose: the counts must match the manifest, the reports and the
    // SQL the support engineer reads, in both languages.
    final NumberFormat numbers = NumberFormat.decimalPattern('en');

    return Scaffold(
      appBar: AppBar(title: Text(strings.settingsTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: <Widget>[
            InfoCard(
              title: strings.settingsLanguage,
              accent: AppPalette.instrumentBlue,
              child: SegmentedButton<AppLanguage>(
                segments: <ButtonSegment<AppLanguage>>[
                  for (final AppLanguage language in AppLanguage.values)
                    ButtonSegment<AppLanguage>(value: language, label: Text(language.label)),
                ],
                selected: <AppLanguage>{settings.language},
                onSelectionChanged: (Set<AppLanguage> selection) {
                  ref.read(settingsProvider.notifier).setLanguage(selection.first);
                },
              ),
            ),
            const SizedBox(height: 16),
            InfoCard(
              title: strings.settingsAppearance,
              child: SegmentedButton<ThemeMode>(
                segments: <ButtonSegment<ThemeMode>>[
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.system,
                    label: Text(strings.settingsThemeSystem),
                  ),
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.light,
                    label: Text(strings.settingsThemeLight),
                  ),
                  ButtonSegment<ThemeMode>(
                    value: ThemeMode.dark,
                    label: Text(strings.settingsThemeDark),
                  ),
                ],
                selected: <ThemeMode>{settings.themeMode},
                onSelectionChanged: (Set<ThemeMode> selection) {
                  ref.read(settingsProvider.notifier).setThemeMode(selection.first);
                },
              ),
            ),
            const SizedBox(height: 16),
            InfoCard(
              title: strings.settingsDatabase,
              child: library.when(
                data: (DatabaseSummary summary) => Column(
                  children: <Widget>[
                    MetricRow(
                      label: strings.homeDatabaseVersion,
                      value: summary.version,
                      hint: '${strings.homeDatabaseSchema} ${summary.schemaVersion}',
                    ),
                    const Divider(height: 18),
                    MetricRow(
                      label: strings.homeDatabaseCodes,
                      value: numbers.format(summary.codeCount),
                    ),
                    const Divider(height: 18),
                    MetricRow(
                      label: strings.homeDatabaseQuotes,
                      value: numbers.format(summary.quoteCount),
                    ),
                    const Divider(height: 18),
                    MetricRow(
                      label: strings.homeDatabaseApprovedProcedures,
                      value: numbers.format(summary.approvedProcedures),
                    ),
                  ],
                ),
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (Object error, StackTrace stack) => Text('$error'),
              ),
            ),
            const SizedBox(height: 16),
            InfoCard(
              title: strings.settingsAbout,
              child: Column(
                children: <Widget>[
                  MetricRow(label: strings.settingsVersion, value: AppInfo.versionLabel),
                  const Divider(height: 18),
                  MetricRow(
                    label: strings.settingsPrivacy,
                    value: '',
                    hint: strings.settingsPrivacyBody,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
