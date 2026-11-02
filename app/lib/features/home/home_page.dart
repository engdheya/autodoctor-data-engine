import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/l10n/app_strings.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/info_card.dart';
import '../../domain/entities/database_summary.dart';
import '../../providers.dart';

/// Phase 1 home: proves the bundle is open and reports what it contains.
///
/// The search field is intentionally not wired: showing a working-looking box that returns
/// nothing would be the fake UI this project forbids. It is disabled and says why.
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppStrings strings = AppStrings.of(context);
    final AsyncValue<DatabaseSummary> library = ref.watch(librarySummaryProvider);
    // Latin digits on purpose: the counts must match the manifest, the reports and the
    // SQL the support engineer reads, in both languages.
    final NumberFormat numbers = NumberFormat.decimalPattern('en');

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.homeTitle),
        actions: <Widget>[
          IconButton(
            tooltip: strings.settingsTitle,
            onPressed: () => context.push(AppRoutes.settings),
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: <Widget>[
            Text(
              strings.appName,
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.6,
                  ),
            ),
            const SizedBox(height: 6),
            Text(
              strings.appTagline,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 20),
            const _SearchPlaceholder(),
            const SizedBox(height: 20),
            library.when(
              data: (DatabaseSummary summary) => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  _DatabaseCard(summary: summary, numbers: numbers),
                  const SizedBox(height: 16),
                  _ProceduresCard(strings: strings, summary: summary),
                ],
              ),
              loading: () => const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (Object error, StackTrace stack) => InfoCard(
                title: strings.splashFailedTitle,
                accent: AppPalette.danger,
                child: SelectableText('$error'),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              strings.homePhaseNote,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                    height: 1.5,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SearchPlaceholder extends StatelessWidget {
  const _SearchPlaceholder();

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = AppStrings.of(context);
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        TextField(
          enabled: false,
          decoration: InputDecoration(
            hintText: strings.homeSearchHint,
            prefixIcon: const Icon(Icons.search),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: <Widget>[
            const Icon(Icons.info_outline, size: 15),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                strings.homeSearchSubtitle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _DatabaseCard extends StatelessWidget {
  const _DatabaseCard({required this.summary, required this.numbers});

  final DatabaseSummary summary;
  final NumberFormat numbers;

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = AppStrings.of(context);
    return InfoCard(
      title: strings.homeDatabaseCard,
      accent: AppPalette.instrumentBlue,
      trailing: DisclosureChip(label: summary.sourceSet),
      child: Column(
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
        ],
      ),
    );
  }
}

class _ProceduresCard extends StatelessWidget {
  const _ProceduresCard({required this.strings, required this.summary});

  final AppStrings strings;
  final DatabaseSummary summary;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool hasProcedures = summary.hasApprovedProcedures;
    return InfoCard(
      title: strings.homeDatabaseApprovedProcedures,
      accent: hasProcedures ? AppPalette.success : AppPalette.amber,
      trailing: DisclosureChip(
        label: hasProcedures ? strings.sourceDisclosure : strings.procedureNotApproved,
        kind: hasProcedures ? DisclosureKind.sourceStated : DisclosureKind.unverified,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                '${summary.approvedProcedures}',
                style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            strings.homeApprovedProceduresNone,
            style: theme.textTheme.bodySmall?.copyWith(
              height: 1.5,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
