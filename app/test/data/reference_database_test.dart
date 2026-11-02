/// Opens the real delivered bundle through the real code path.
///
/// The bundle is 65 MB and is never committed, so this test skips when it has not been
/// staged (`python3 tool/stage_reference_db.py`). When it is present, the test verifies the
/// checksum, the schema contract, the counts the app displays and the tamper detection.
library;

import 'dart:convert';
import 'dart:io';

import 'package:autodoctor_app/core/errors/app_failure.dart';
import 'package:autodoctor_app/data/database/db_manifest.dart';
import 'package:autodoctor_app/data/database/reference_database.dart';
import 'package:autodoctor_app/domain/entities/database_summary.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Serves assets from disk so the test exercises the shipping code, not a rewrite of it.
class DiskAssetBundle extends CachingAssetBundle {
  DiskAssetBundle(this.root);

  final Map<String, String> root;

  @override
  Future<ByteData> load(String key) async {
    final String? path = root[key];
    if (path == null) {
      throw FlutterError('asset not found: $key');
    }
    final File file = File(path);
    if (!file.existsSync()) {
      throw FlutterError('file not found: $path');
    }
    final Uint8List bytes = await file.readAsBytes();
    return ByteData.view(bytes.buffer);
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) =>
      File(root[key]!).readAsString();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  final File bundle = File('../data/exports/autodoctor-app-0.9.1-public.sqlite');
  final File manifestFile = File('assets/db/db_manifest.json');

  final bool staged = bundle.existsSync() && manifestFile.existsSync();

  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('autodoctor-db');
  });

  tearDown(() async {
    await tempDir.delete(recursive: true);
  });

  test('the staged manifest describes the staged bundle', () async {
    final DbManifest manifest =
        DbManifest.fromJsonString(await manifestFile.readAsString());
    expect(manifest.fileName, bundle.uri.pathSegments.last);
    expect(manifest.bytes, bundle.lengthSync());
    expect(manifest.schemaVersion, 4);
    expect(manifest.requiredViews, hasLength(16));
  }, skip: !staged);

  test('opens the bundle read-only and reports its real contents', () async {
    final ReferenceDatabase reference = ReferenceDatabase(
      assetBundle: DiskAssetBundle(<String, String>{
        'assets/db/db_manifest.json': manifestFile.path,
        'assets/db/${bundle.uri.pathSegments.last}': bundle.path,
      }),
      directory: tempDir.path,
    );
    addTearDown(reference.close);

    final DatabaseSummary summary = await reference.open();
    expect(summary.version, '0.9.1');
    expect(summary.schemaVersion, 4);
    expect(summary.codeCount, 19089);
    expect(summary.quoteCount, 6495);
    expect(summary.approvedProcedures, 0, reason: 'no technician has approved a procedure');

    // writing to the reference bundle must be impossible
    await expectLater(
      reference.database.execute('CREATE TABLE should_fail (id INTEGER)'),
      throwsA(anything),
    );
  }, skip: !staged);

  test('a corrupted copy is refused instead of opened', () async {
    final Map<String, Object?> json =
        jsonDecode(await manifestFile.readAsString()) as Map<String, Object?>;
    json['sha256'] = List<String>.filled(64, '0').join(); // deliberately wrong
    final File badManifest = File('${tempDir.path}/db_manifest.json');
    await badManifest.writeAsString(jsonEncode(json));

    final ReferenceDatabase reference = ReferenceDatabase(
      assetBundle: DiskAssetBundle(<String, String>{
        'assets/db/db_manifest.json': badManifest.path,
        'assets/db/${bundle.uri.pathSegments.last}': bundle.path,
      }),
      directory: tempDir.path,
    );
    addTearDown(reference.close);

    await expectLater(
      reference.open(),
      throwsA(isA<AppFailure>()
          .having((AppFailure f) => f.kind, 'kind', FailureKind.checksumMismatch)),
    );
  }, skip: !staged);
}
