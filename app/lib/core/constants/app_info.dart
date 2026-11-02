/// Static facts about this build. Nothing here may be derived at runtime from a guess.
class AppInfo {
  const AppInfo._();

  static const String name = 'AutoDoctor AI';
  static const String version = '0.1.0';
  static const String buildNumber = '1';
  static const String versionLabel = '$version+$buildNumber';

  /// Bumped whenever a new diagnostic bundle is staged into `assets/db/`.
  static const String expectedDatabaseVersion = '0.9.1';
  static const int expectedSchemaVersion = 4;

  /// Container names the client may query. A bundle that lacks one of them is refused,
  /// because a missing view means every screen built on it would fail at runtime.
  static const List<String> requiredViews = <String>[
    'v_dtc_search',
    'v_dtc_lookup',
    'v_dtc_summary',
    'v_dtc_causes',
    'v_dtc_symptoms',
    'v_dtc_repairs',
    'v_dtc_tests',
    'v_dtc_related',
    'v_dtc_provenance',
    'v_dtc_conflicts',
    'v_manufacturers',
    'v_pids',
    'v_vehicles',
    'v_dtc_source_quotes',
    'v_dtc_priority',
    'v_translation_drafts',
  ];
}
