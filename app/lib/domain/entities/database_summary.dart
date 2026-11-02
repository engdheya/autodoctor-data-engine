/// What the app knows about the bundle it opened. Every field is read from the file.
class DatabaseSummary {
  const DatabaseSummary({
    required this.version,
    required this.schemaVersion,
    required this.sourceSet,
    required this.fileBytes,
    required this.codeCount,
    required this.quoteCount,
    required this.approvedProcedures,
  });

  final String version;
  final int schemaVersion;
  final String sourceSet;
  final int fileBytes;
  final int codeCount;
  final int quoteCount;

  /// Zero in every bundle built so far: no technician has approved a procedure yet.
  final int approvedProcedures;

  bool get hasApprovedProcedures => approvedProcedures > 0;
}
