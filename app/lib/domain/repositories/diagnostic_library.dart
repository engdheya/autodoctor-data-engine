import '../entities/database_summary.dart';

/// Opening the diagnostic library is a domain capability, not a database detail.
abstract class DiagnosticLibrary {
  /// Verifies and opens the delivered bundle; throws [AppFailure] when it cannot.
  Future<DatabaseSummary> open();

  Future<void> close();
}
