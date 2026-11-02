import 'dart:convert';

import 'package:autodoctor_app/core/errors/app_failure.dart';
import 'package:autodoctor_app/data/database/db_manifest.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, Object?> _valid() => <String, Object?>{
      'version': '0.9.1',
      'schema_version': 4,
      'file_name': 'autodoctor-app-0.9.1-public.sqlite',
      'sha256': 'ABCDEF',
      'bytes': 65884160,
      'required_views': <String>['v_dtc_search'],
      'generated_at': '2026-11-02T19:00:00Z',
    };

void main() {
  test('parses the staged manifest', () {
    final DbManifest manifest = DbManifest.fromJsonString(jsonEncode(_valid()));
    expect(manifest.version, '0.9.1');
    expect(manifest.schemaVersion, 4);
    expect(manifest.bytes, 65884160);
    expect(manifest.sha256, 'abcdef', reason: 'the digest is normalised to lower case');
  });

  test('a manifest without required views is refused', () {
    final Map<String, Object?> json = _valid()..remove('required_views');
    expect(
      () => DbManifest.fromJson(json),
      throwsA(isA<AppFailure>().having(
        (AppFailure failure) => failure.kind,
        'kind',
        FailureKind.schemaUnsupported,
      )),
    );
  });

  test('a non-numeric byte count is refused instead of defaulting to zero', () {
    final Map<String, Object?> json = _valid()..['bytes'] = 'a lot';
    expect(() => DbManifest.fromJson(json), throwsA(isA<AppFailure>()));
  });
}
