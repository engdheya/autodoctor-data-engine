/// The only place in the application that contains SQL against the reference bundle.
///
/// Every statement here is documented in `docs/APP_DB_CONTRACT.md`. Queries are written
/// against the client views and the indexed tables; `v_dtc_search` is never used for lists
/// because it scans the whole code table (measured: 11.52 ms versus 0.08 ms by index).
library;

import 'package:sqflite/sqflite.dart';

import '../../domain/entities/database_summary.dart';

class ReferenceDataSource {
  const ReferenceDataSource(this._db);

  final Database _db;

  Future<DatabaseSummary> summary() async {
    final List<Map<String, Object?>> rows =
        await _db.rawQuery('SELECT version, schema_version, source_set FROM db_versions');
    final Map<String, Object?> row = rows.isEmpty ? const <String, Object?>{} : rows.first;
    return DatabaseSummary(
      version: '${row['version'] ?? ''}',
      schemaVersion: int.tryParse('${row['schema_version']}') ?? 0,
      sourceSet: '${row['source_set'] ?? ''}',
      fileBytes: 0,
      codeCount: await _count('SELECT COUNT(*) FROM dtc_codes'),
      quoteCount: await _count('SELECT COUNT(*) FROM source_quotes'),
      approvedProcedures: await _count('SELECT COUNT(*) FROM dtc_tests'),
    );
  }

  Future<int> _count(String sql) async {
    final List<Map<String, Object?>> rows = await _db.rawQuery(sql);
    final Object? value = rows.isEmpty ? null : rows.first.values.first;
    return value is int ? value : int.tryParse('$value') ?? 0;
  }
}
