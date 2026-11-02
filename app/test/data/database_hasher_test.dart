import 'dart:convert';
import 'dart:io';

import 'package:autodoctor_app/data/database/database_hasher.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('hashes a file the same way sha256sum does', () async {
    final Directory dir = await Directory.systemTemp.createTemp('autodoctor-hash');
    addTearDown(() => dir.delete(recursive: true));
    final File file = File('${dir.path}/payload.bin');
    await file.writeAsBytes(utf8.encode('abc'));
    // sha256("abc"), the canonical test vector
    expect(
      await const DatabaseHasher().sha256OfFile(file),
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  test('a one-byte change changes the digest', () async {
    final Directory dir = await Directory.systemTemp.createTemp('autodoctor-hash2');
    addTearDown(() => dir.delete(recursive: true));
    final File first = File('${dir.path}/a.bin');
    final File second = File('${dir.path}/b.bin');
    await first.writeAsBytes(<int>[1, 2, 3]);
    await second.writeAsBytes(<int>[1, 2, 4]);
    const DatabaseHasher hasher = DatabaseHasher();
    expect(await hasher.sha256OfFile(first), isNot(await hasher.sha256OfFile(second)));
  });
}
