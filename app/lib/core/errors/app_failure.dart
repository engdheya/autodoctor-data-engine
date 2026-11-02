/// Every failure the UI can show carries a machine code and a key, never a stack trace.
enum FailureKind {
  databaseMissing,
  databaseCopyFailed,
  checksumMismatch,
  schemaUnsupported,
  viewsMissing,
  openFailed,
  userDatabaseFailed,
}

class AppFailure implements Exception {
  const AppFailure(this.kind, {this.detail});

  final FailureKind kind;

  /// Technical detail for the diagnostics screen. Never shown as the primary message:
  /// the user gets a sentence and, where possible, an action.
  final String? detail;

  @override
  String toString() => 'AppFailure(${kind.name})${detail == null ? '' : ': $detail'}';
}
