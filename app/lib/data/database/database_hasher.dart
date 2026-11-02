/// SHA-256 over a file, read in chunks so a 65 MB bundle never lands in memory.
library;

import 'dart:io';

import 'package:convert/convert.dart';
import 'package:crypto/crypto.dart';

class DatabaseHasher {
  const DatabaseHasher();

  Future<String> sha256OfFile(File file) async {
    final output = AccumulatorSink<Digest>();
    final input = sha256.startChunkedConversion(output);
    await for (final List<int> chunk in file.openRead()) {
      input.add(chunk);
    }
    input.close();
    final Digest digest = output.events.single;
    return digest.toString();
  }
}
