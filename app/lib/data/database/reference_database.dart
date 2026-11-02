/// Opens the delivered diagnostic bundle: copy once, verify, then read-only for ever.
///
/// The reference file is never written to. Anything the user saves lives in
/// [UserDatabase], a separate file with its own version.
library;

import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../../core/constants/app_info.dart';
import '../../core/errors/app_failure.dart';
import '../../domain/entities/database_summary.dart';
import '../datasources/reference_data_source.dart';
import 'database_hasher.dart';
import 'db_manifest.dart';

class ReferenceDatabase {
  ReferenceDatabase({
    required this.assetBundle,
    required this.directory,
    this.hasher = const DatabaseHasher(),
    this.manifestAssetPath = 'assets/db/db_manifest.json',
  });

  final AssetBundle assetBundle;

  /// Where the copied bundle lives on the device (injected so tests use a temp dir).
  final String directory;
  final DatabaseHasher hasher;
  final String manifestAssetPath;

  DbManifest? _manifest;
  Database? _database;

  DbManifest get manifest {
    final DbManifest? value = _manifest;
    if (value == null) {
      throw const AppFailure(FailureKind.databaseMissing, detail: 'manifest not loaded');
    }
    return value;
  }

  Database get database {
    final Database? value = _database;
    if (value == null) {
      throw const AppFailure(FailureKind.databaseMissing, detail: 'database not opened');
    }
    return value;
  }

  String get databasePath => p.join(directory, manifest.fileName);

  Future<DbManifest> loadManifest() async {
    final String raw = await assetBundle.loadString(manifestAssetPath);
    final DbManifest manifest = DbManifest.fromJsonString(raw);
    _manifest = manifest;
    return manifest;
  }

  /// Copies the asset on first launch, then verifies the file against the manifest.
  ///
  /// Re-verifying on every launch is deliberate: the copy is 65 MB and a half-written
  /// file from an interrupted first run would otherwise open as a valid but empty database.
  Future<File> ensureBundle() async {
    final DbManifest manifest = _manifest ?? await loadManifest();
    final File target = File(databasePath);
    if (!await target.exists() || await target.length() != manifest.bytes) {
      await _copyFromAsset(manifest, target);
    }
    final String actual = await hasher.sha256OfFile(target);
    if (actual != manifest.sha256) {
      throw AppFailure(
        FailureKind.checksumMismatch,
        detail: 'expected ${manifest.sha256}, found $actual',
      );
    }
    return target;
  }

  Future<void> _copyFromAsset(DbManifest manifest, File target) async {
    try {
      await Directory(directory).create(recursive: true);
      final ByteData data = await assetBundle.load('assets/db/${manifest.fileName}');
      final List<int> bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      final File tmp = File('${target.path}.part');
      await tmp.writeAsBytes(bytes, flush: true);
      await tmp.rename(target.path);
    } on Object catch (error) {
      throw AppFailure(FailureKind.databaseCopyFailed, detail: '$error');
    }
  }

  Future<DatabaseSummary> open() async {
    final DbManifest manifest = _manifest ?? await loadManifest();
    await ensureBundle();
    final Database db;
    try {
      db = await databaseFactory.openDatabase(
        databasePath,
        options: OpenDatabaseOptions(readOnly: true),
      );
    } on Object catch (error) {
      throw AppFailure(FailureKind.openFailed, detail: '$error');
    }
    _database = db;
    final DatabaseSummary info = await _verifyContract(db, manifest);
    return info;
  }

  Future<DatabaseSummary> _verifyContract(Database db, DbManifest manifest) async {
    final ReferenceDataSource source = ReferenceDataSource(db);
    final DatabaseSummary counts = await source.summary();

    if (counts.schemaVersion < AppInfo.expectedSchemaVersion) {
      throw AppFailure(
        FailureKind.schemaUnsupported,
        detail: 'bundle schema ${counts.schemaVersion} is older than '
            '${AppInfo.expectedSchemaVersion}',
      );
    }
    final Set<String> present = <String>{
      for (final Map<String, Object?> item
          in await db.rawQuery("SELECT name FROM sqlite_master WHERE type = 'view'"))
        '${item['name']}',
    };
    final List<String> missing =
        manifest.requiredViews.where((String name) => !present.contains(name)).toList();
    if (missing.isNotEmpty) {
      throw AppFailure(FailureKind.viewsMissing, detail: missing.join(', '));
    }

    return DatabaseSummary(
      version: counts.version,
      schemaVersion: counts.schemaVersion,
      sourceSet: counts.sourceSet,
      fileBytes: manifest.bytes,
      codeCount: counts.codeCount,
      quoteCount: counts.quoteCount,
      approvedProcedures: counts.approvedProcedures,
    );
  }

  Future<void> close() async {
    await _database?.close();
    _database = null;
  }
}
