/// The manifest staged next to the diagnostic bundle by `tool/stage_reference_db.py`.
///
/// It is generated from the artifact itself, so the checksum here describes the file that
/// shipped: a swapped or truncated bundle fails verification instead of opening quietly.
library;

import 'dart:convert';

import '../../core/errors/app_failure.dart';

class DbManifest {
  const DbManifest({
    required this.version,
    required this.schemaVersion,
    required this.fileName,
    required this.sha256,
    required this.bytes,
    required this.requiredViews,
    required this.generatedAt,
  });

  final String version;
  final int schemaVersion;
  final String fileName;
  final String sha256;
  final int bytes;
  final List<String> requiredViews;
  final String generatedAt;

  static DbManifest fromJsonString(String source) {
    final Object? decoded = jsonDecode(source);
    if (decoded is! Map<String, Object?>) {
      throw const AppFailure(
        FailureKind.schemaUnsupported,
        detail: 'db_manifest.json is not a JSON object',
      );
    }
    return DbManifest.fromJson(decoded);
  }

  static DbManifest fromJson(Map<String, Object?> json) {
    String string(String key) {
      final Object? value = json[key];
      if (value is! String || value.isEmpty) {
        throw AppFailure(
          FailureKind.schemaUnsupported,
          detail: 'db_manifest.json is missing "$key"',
        );
      }
      return value;
    }

    int integer(String key) {
      final Object? value = json[key];
      if (value is int) {
        return value;
      }
      if (value is String) {
        final int? parsed = int.tryParse(value);
        if (parsed != null) {
          return parsed;
        }
      }
      throw AppFailure(
        FailureKind.schemaUnsupported,
        detail: 'db_manifest.json has a non-numeric "$key"',
      );
    }

    final Object? views = json['required_views'];
    if (views is! List || views.isEmpty) {
      throw const AppFailure(
        FailureKind.schemaUnsupported,
        detail: 'db_manifest.json has no required_views',
      );
    }

    return DbManifest(
      version: string('version'),
      schemaVersion: integer('schema_version'),
      fileName: string('file_name'),
      sha256: string('sha256').toLowerCase(),
      bytes: integer('bytes'),
      requiredViews: views.map((Object? value) => '$value').toList(growable: false),
      generatedAt: json['generated_at'] as String? ?? '',
    );
  }
}
