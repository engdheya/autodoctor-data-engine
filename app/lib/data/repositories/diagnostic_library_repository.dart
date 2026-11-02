import '../../domain/entities/database_summary.dart';
import '../../domain/repositories/diagnostic_library.dart';
import '../database/reference_database.dart';

class DiagnosticLibraryRepository implements DiagnosticLibrary {
  DiagnosticLibraryRepository(this._reference);

  final ReferenceDatabase _reference;

  @override
  Future<DatabaseSummary> open() async {
    final DatabaseSummary opened = await _reference.open();
    // the manifest size is authoritative for "what shipped", the file's own db_versions
    // row is authoritative for "what opened"; the summary carries both.
    return DatabaseSummary(
      version: opened.version,
      schemaVersion: opened.schemaVersion,
      sourceSet: opened.sourceSet,
      fileBytes: _reference.manifest.bytes,
      codeCount: opened.codeCount,
      quoteCount: opened.quoteCount,
      approvedProcedures: opened.approvedProcedures,
    );
  }

  @override
  Future<void> close() => _reference.close();
}
