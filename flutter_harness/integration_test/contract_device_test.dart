// On-device run (Android emulator or USB device):
//   cd flutter_harness
//   flutter test integration_test/contract_device_test.dart \
//       --dart-define=DB=/data/user/0/<pkg>/files/autodoctor-app-<v>-public.sqlite
//
// Copy the bundle to the device first (adb push or bundling it as an asset).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart';

import '../lib/contract.dart';

const dbPath = String.fromEnvironment('DB');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('the bundle opens and answers the contract on device', (tester) async {
    expect(File(dbPath).existsSync(), isTrue);
    final db = await openDatabase(dbPath, readOnly: true);
    final contract = DbContract(db);

    expect(await contract.integrityCheck(), 'ok');
    final card = await contract.generic('P0301');
    expect(card, isNotNull);
    expect(card!.code, 'P0301');
    final views = await contract.views();
    expect(views.length, 13);
    await db.close();
  });
}
