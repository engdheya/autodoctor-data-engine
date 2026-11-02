/// Dependency graph for the whole application.
///
/// Features never construct databases or read SQL: they read these providers, which are
/// wired to the data layer. Tests override the bundle and the directory.
library;

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite/sqflite.dart';

import 'core/settings/app_settings.dart';
import 'core/settings/preferences_provider.dart';
import 'core/settings/settings_controller.dart';
import 'data/database/reference_database.dart';
import 'data/repositories/diagnostic_library_repository.dart';
import 'domain/entities/database_summary.dart';
import 'domain/repositories/diagnostic_library.dart';
import 'domain/usecases/open_diagnostic_library.dart';

export 'core/settings/preferences_provider.dart' show sharedPreferencesProvider;

final NotifierProvider<SettingsController, AppSettings> settingsProvider =
    NotifierProvider<SettingsController, AppSettings>(SettingsController.new);

final Provider<AssetBundle> assetBundleProvider =
    Provider<AssetBundle>((Ref ref) => rootBundle);

/// sqflite decides where databases live; tests override it with a temp directory.
final FutureProvider<String> databaseDirectoryProvider = FutureProvider<String>(
  (Ref ref) => getDatabasesPath(),
);

final FutureProvider<DiagnosticLibrary> diagnosticLibraryProvider =
    FutureProvider<DiagnosticLibrary>((Ref ref) async {
  final String directory = await ref.watch(databaseDirectoryProvider.future);
  final ReferenceDatabase reference = ReferenceDatabase(
    assetBundle: ref.watch(assetBundleProvider),
    directory: directory,
  );
  ref.onDispose(reference.close);
  return DiagnosticLibraryRepository(reference);
});

/// The bundle, verified and opened. This is the first thing every screen waits for.
final FutureProvider<DatabaseSummary> librarySummaryProvider =
    FutureProvider<DatabaseSummary>((Ref ref) async {
  final DiagnosticLibrary library = await ref.watch(diagnosticLibraryProvider.future);
  return OpenDiagnosticLibrary(library)();
});
