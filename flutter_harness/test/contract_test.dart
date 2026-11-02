// Host-side contract test. Run with:
//   cd flutter_harness && flutter test --dart-define=DB=/abs/path/autodoctor-app-<v>-public.sqlite
//
// The same assertions run on a device through integration_test/contract_device_test.dart.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../lib/contract.dart';

const dbPath = String.fromEnvironment('DB', defaultValue: '');

void main() {
  sqfliteFfiInit();

  late Database db;
  late DbContract contract;

  setUpAll(() async {
    if (dbPath.isEmpty) {
      fail('pass --dart-define=DB=/absolute/path/to/autodoctor-app-<version>-public.sqlite');
    }
    expect(File(dbPath).existsSync(), isTrue, reason: 'bundle not found at $dbPath');
    db = await databaseFactoryFfi.openDatabase(
      dbPath,
      options: OpenDatabaseOptions(readOnly: true),
    );
    contract = DbContract(db);
  });

  tearDownAll(() async => db.close());

  test('integrity and view contract', () async {
    expect(await contract.integrityCheck(), 'ok');
    final views = await contract.views();
    expect(views.length, 13, reason: 'the client contract has 13 views');
  });

  test('P0301 is a diagnosis-ready generic card', () async {
    final card = await contract.generic('p 0301');
    expect(card, isNotNull);
    expect(card!.code, 'P0301');
    expect(card.isDiagnosisReady, isTrue);
  });

  test('causes, symptoms and repairs come from the database', () async {
    final card = await contract.generic('P0301');
    final rows = await db.query('v_dtc_search', where: 'code = ?', whereArgs: ['P0301']);
    final id = rows.first['dtc_code_id'] as int;
    expect(await contract.causes(id), isNotEmpty);
    expect(await contract.symptoms(id), isNotEmpty);
    expect(await contract.repairs(id), isNotEmpty);
    expect(card!.causes, greaterThan(0));
  });

  test('provenance carries a licence and a commit', () async {
    final rows = await db.query('v_dtc_search',
        where: "code = 'P0301' AND context_type = 'generic'");
    final provenance = await contract.provenance(rows.first['dtc_code_id'] as int);
    expect(provenance, isNotEmpty);
    for (final entry in provenance) {
      expect(entry.licence, isNotNull);
      expect(entry.commit, isNotNull);
    }
  });

  test('unsupported dimensions are empty, not invented', () async {
    expect(await contract.vehicleCount(), 0);
    expect(await contract.arabicCount(), 0);
  });
}
