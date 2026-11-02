import '../entities/database_summary.dart';
import '../repositories/diagnostic_library.dart';

class OpenDiagnosticLibrary {
  const OpenDiagnosticLibrary(this._library);

  final DiagnosticLibrary _library;

  Future<DatabaseSummary> call() => _library.open();
}
