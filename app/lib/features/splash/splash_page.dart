import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_failure.dart';
import '../../core/l10n/app_strings.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/app_theme.dart';
import '../../domain/entities/database_summary.dart';
import '../../providers.dart';

/// Waits for the verified bundle, then routes to onboarding or home.
///
/// The failure state is the important one: if the checksum does not match, the app says so
/// and refuses to continue. It never falls back to an empty database to look healthy.
class SplashPage extends ConsumerStatefulWidget {
  const SplashPage({super.key});

  @override
  ConsumerState<SplashPage> createState() => _SplashPageState();
}

class _SplashPageState extends ConsumerState<SplashPage> {
  bool _navigated = false;

  void _continueAfterOpen(DatabaseSummary summary) {
    if (_navigated) {
      return;
    }
    _navigated = true;
    final bool onboarded = ref.read(settingsProvider).onboardingComplete;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      context.go(onboarded ? AppRoutes.home : AppRoutes.onboarding);
    });
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = AppStrings.of(context);
    final AsyncValue<DatabaseSummary> library = ref.watch(librarySummaryProvider);

    library.whenData(_continueAfterOpen);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: library.when(
              loading: () => _LoadingState(strings: strings),
              error: (Object error, StackTrace stack) => _FailureState(
                strings: strings,
                failure: error,
                onRetry: () {
                  _navigated = false;
                  ref.invalidate(librarySummaryProvider);
                },
              ),
              data: (DatabaseSummary summary) => _LoadingState(strings: strings),
            ),
          ),
        ),
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: 76,
          height: 76,
          decoration: BoxDecoration(
            color: theme.colorScheme.primary.withOpacity(0.12),
            borderRadius: BorderRadius.circular(22),
          ),
          child: Icon(Icons.monitor_heart_outlined, size: 40, color: theme.colorScheme.primary),
        ),
        const SizedBox(height: 22),
        Text(
          strings.appName,
          style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 6),
        Text(
          strings.appTagline,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 30),
        const SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(strokeWidth: 2.4),
        ),
        const SizedBox(height: 14),
        Text(
          strings.splashVerifying,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }
}

class _FailureState extends StatelessWidget {
  const _FailureState({
    required this.strings,
    required this.failure,
    required this.onRetry,
  });

  final AppStrings strings;
  final Object failure;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String detail = switch (failure) {
      AppFailure(:final String? detail) => detail ?? failure.toString(),
      _ => '$failure',
    };
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Icon(Icons.gpp_bad_outlined, size: 52, color: AppPalette.danger),
        const SizedBox(height: 18),
        Text(
          strings.splashFailedTitle,
          textAlign: TextAlign.center,
          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.5),
            borderRadius: BorderRadius.circular(12),
          ),
          child: SelectableText(
            detail,
            style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
          ),
        ),
        const SizedBox(height: 24),
        FilledButton(onPressed: onRetry, child: Text(strings.actionRetry)),
      ],
    );
  }
}
