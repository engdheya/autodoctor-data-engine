/// Architecture tests: they fail the build when the layering is violated.
///
/// Without these, "clean architecture" is a folder diagram. A screen that calls rawQuery,
/// or a domain entity that imports sqflite, breaks the design even if the app still runs.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

final RegExp _sql = RegExp(
  r'\b(SELECT\s+[\w*]|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE|PRAGMA)\b',
  caseSensitive: false,
);

/// Imports that reach into the data layer, from anywhere outside it.
final RegExp _dataImport = RegExp("import\\s+['\"][^'\"]*data/");

List<File> _dartFiles(String relative) {
  final Directory root = Directory(relative);
  if (!root.existsSync()) {
    return <File>[];
  }
  return root
      .listSync(recursive: true)
      .whereType<File>()
      .where((File file) => file.path.endsWith('.dart'))
      .toList(growable: false);
}

String _slash(File file) => p.split(file.path).join('/');

void main() {
  const String dataRoot = 'lib/data';

  test('SQL lives only in the data layer', () {
    final List<String> offenders = <String>[];
    for (final File file in _dartFiles('lib')) {
      if (!_sql.hasMatch(file.readAsStringSync())) {
        continue;
      }
      if (!_slash(file).startsWith(dataRoot)) {
        offenders.add(_slash(file));
      }
    }
    expect(offenders, isEmpty, reason: 'raw SQL outside $dataRoot: $offenders');
  });

  test('presentation, domain and core never import the data layer or sqflite', () {
    final List<String> offenders = <String>[];
    for (final String root in <String>['lib/features', 'lib/domain', 'lib/core']) {
      for (final File file in _dartFiles(root)) {
        final String source = file.readAsStringSync();
        if (source.contains('package:sqflite/') || _dataImport.hasMatch(source)) {
          offenders.add(_slash(file));
        }
      }
    }
    expect(offenders, isEmpty, reason: 'reaching into the database: $offenders');
  });

  test('no print calls: failures are surfaced as failures', () {
    final List<String> offenders = <String>[];
    for (final File file in _dartFiles('lib')) {
      final List<String> lines = file.readAsLinesSync();
      for (int index = 0; index < lines.length; index++) {
        if (RegExp(r'(^|[^.\w])print\(').hasMatch(lines[index])) {
          offenders.add('${_slash(file)}:${index + 1}');
        }
      }
    }
    expect(offenders, isEmpty, reason: 'print() found: $offenders');
  });

  test('feature widgets never build their own database connection', () {
    final List<String> offenders = <String>[];
    for (final File file in _dartFiles('lib/features')) {
      final String source = file.readAsStringSync();
      if (source.contains('openDatabase') || source.contains('rawQuery(')) {
        offenders.add(_slash(file));
      }
    }
    expect(offenders, isEmpty);
  });
}
